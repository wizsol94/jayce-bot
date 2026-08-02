from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .commands import CommandError, parse_command, parse_target, validate_address
from .models import PriceAlert
from .provider import PriceProviderError
from .repository import PriceAlertRepository, utc_now

logger = logging.getLogger("jace.price_alerts")


class PriceAlertService:
    def __init__(self, database, provider, admin_ids=(), trigger_publisher=None, poll_seconds=5):
        self.repository = PriceAlertRepository(database)
        self.provider = provider
        self.admin_ids = {str(value) for value in admin_ids if str(value).strip()}
        self.trigger_publisher = trigger_publisher or (lambda alert: None)
        self.poll_seconds = max(5, int(poll_seconds))
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()
        try:
            stale = self.repository.reset_stale_claims()
            if stale:
                logger.info("[price alert] released %s stale delivery claim(s) after restart", stale)
        except Exception:
            logger.exception("[price alert] could not reset stale delivery claims")

    def is_authorized(self, user_id) -> bool:
        return str(user_id) in self.admin_ids

    def start(self):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        logger.info("[price alert] module started")
        self.thread = threading.Thread(target=self._loop, name="jace-price-alerts", daemon=True)
        self.thread.start()

    def stop(self, timeout=2):
        """Stop the worker. Safe if never started, already stopped, or repeated.

        The join is bounded so shutdown is clean but can never hang the host
        application waiting on a poll interval.
        """
        self.stop_event.set()
        self.running = False
        thread = self.thread
        self.thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("[price alert] worker did not stop within %ss", timeout)
                return
        logger.info("[price alert] worker stopped")

    def handle_command(self, text, *, user_id, chat_id, update_id=None):
        if not self.is_authorized(user_id):
            return "Permission denied."
        command = parse_command(text)
        if command.name == "alert":
            if len(command.args) != 2:
                raise CommandError("Usage: /alert CONTRACT_ADDRESS TARGET_PRICE")
            address = validate_address(command.args[0])
            target = parse_target(command.args[1])
            quote = self.provider.get_quote(address)
            if not self.repository.claim_update(chat_id, update_id):
                return "This Telegram update was already processed."
            alert = self.repository.create(user_id=user_id, source_chat_id=chat_id, destination_chat_id=chat_id, quote=quote, target=target, command_text=text, update_id=update_id)
            logger.info("[price alert] alert created id=%s symbol=%s", alert.id, alert.token_symbol)
            return self.format_created(alert)
        if command.name == "alerts":
            return self.format_active(self.repository.active(chat_id))
        if command.name == "delete":
            if len(command.args) != 1 or not command.args[0].isdigit():
                raise CommandError("Usage: /deletealert ALERT_ID")
            alert_id = int(command.args[0])
            # ADMIN MODEL: every ID in JACE_PRICE_ALERT_ADMIN_IDS is a GLOBAL
            # admin. Any configured admin may delete any alert in their chat,
            # regardless of who created it. Per-creator ownership is deliberately
            # NOT enforced. Alerts belonging to a different chat are reported as
            # not found, so an ID cannot be used to reach across chats.
            alert = self.repository.get(alert_id) if self._exists(alert_id) else None
            if alert is None or alert.destination_chat_id != str(chat_id):
                return f"Alert number {alert_id} was not found."
            deleted = self.repository.mark_deleted(alert_id)
            logger.info("[price alert] alert deleted id=%s", alert_id)
            return f"Alert number {alert_id} deleted successfully." if deleted else f"Alert number {alert_id} was not found."
        if command.name == "clear":
            self.repository.request_clear_confirmation(user_id, chat_id)
            return "Clear all active alerts. This cannot be undone."
        if command.name == "history":
            return self.format_history(self.repository.history(chat_id))
        raise CommandError("Unknown alert command.")

    def handle_clear_callback(self, action, *, user_id, chat_id):
        if not self.is_authorized(user_id):
            return "Permission denied."
        if action == "cancel":
            self.repository.consume_clear_confirmation(user_id, chat_id)
            return "Clear alerts canceled."
        if action == "confirm":
            if not self.repository.consume_clear_confirmation(user_id, chat_id):
                return "Clear alerts confirmation expired."
            count = self.repository.clear_active(chat_id)
            logger.info("[price alert] all alerts cleared count=%s", count)
            return f"{count} active alert{'s' if count != 1 else ''} cleared."
        return "Unknown confirmation action."

    def check_once(self):
        active = self.repository.active()
        grouped = defaultdict(list)
        for alert in active:
            grouped[alert.contract_address].append(alert)
        try:
            quotes = self.provider.get_quotes(list(grouped))
        except PriceProviderError as exc:
            logger.warning("[price alert] temporary price API error: %s", exc)
            return
        for address, alerts in grouped.items():
            quote = quotes.get(address)
            if not quote:
                logger.debug(
                    "[price alert] no quote this cycle address=%s alerts_left_active=%s",
                    address, len(alerts),
                )
                continue
            if not self._usable_price(quote.price):
                logger.warning(
                    "[price alert] unusable price ignored address=%s value=%r",
                    address, quote.price,
                )
                continue
            checked_at = utc_now()
            for alert in alerts:
                try:
                    previous = alert.last_checked_price or alert.current_price
                    current = quote.price
                    if quote.pair_address != alert.pair_address:
                        logger.info("[price alert] pair re-resolved alert_id=%s old=%s new=%s", alert.id, alert.pair_address, quote.pair_address)
                    if self._crossed(alert.direction, previous, current, alert.target_price):
                        self._deliver(alert, current, checked_at, quote.pair_address)
                    else:
                        self.repository.update_check(alert.id, previous, current, checked_at, pair_address=quote.pair_address)
                except Exception:
                    logger.exception("[price alert] alert evaluation failed id=%s", alert.id)
        return len(active)

    def _deliver(self, alert, current, checked_at, pair_address):
        """Claim -> publish -> finalise. Never consumes an undelivered alert.

        A Telegram failure releases the claim so the alert stays active and is
        retried on the next cycle. Only a confirmed send marks it triggered.
        """
        if not self.repository.claim_for_trigger(alert.id, current, checked_at, pair_address=pair_address):
            logger.debug("[price alert] alert already claimed id=%s", alert.id)
            return False
        claimed = self.repository.get(alert.id)
        try:
            message_id = self.trigger_publisher(claimed)
        except Exception as exc:
            logger.exception("[price alert] trigger publish failed id=%s", alert.id)
            self.repository.release_claim(alert.id, reason=f"publish failed: {type(exc).__name__}")
            return False
        if not self.repository.mark_delivered(alert.id, utc_now(), message_id):
            logger.error("[price alert] could not finalise delivered alert id=%s", alert.id)
            return False
        logger.info("[price alert] alert triggered and delivered id=%s", alert.id)
        return True

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.check_once()
            except Exception:
                logger.exception("[price alert] worker cycle failed")
            self.stop_event.wait(self.poll_seconds)

    def is_admin(self, user_id):
        return self.is_authorized(user_id)

    def _exists(self, alert_id):
        try:
            self.repository.get(alert_id)
            return True
        except KeyError:
            return False

    @staticmethod
    def _crossed(direction, previous, current, target):
        if previous is None or current is None:
            return False
        if direction == "up":
            return previous < target <= current
        return previous > target >= current

    @staticmethod
    def _usable_price(value):
        """Null, zero, negative, NaN and malformed prices must never trigger."""
        if value is None:
            return False
        try:
            price = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return False
        return price.is_finite() and price > 0

    @staticmethod
    def _price(value):
        return format(value, "f")

    def format_created(self, alert):
        return f"Alert number {alert.id} created\nToken: {alert.token_name} ({alert.token_symbol})\nContract: {alert.contract_address}\nCurrent price: {self._price(alert.current_price)}\nTarget price: {self._price(alert.target_price)}\nDirection: {alert.direction}\nStatus: active\nCreated: {alert.created_at}"

    # Telegram rejects messages over 4096 characters. A hard cap keeps /alerts
    # well inside that limit regardless of how many alerts exist. Version 1 uses
    # a simple cap rather than pagination; the remainder stays reachable via
    # /alerts after deleting some, and every alert is still monitored.
    ACTIVE_LIST_LIMIT = 20
    HISTORY_LIMIT = 20

    def format_active(self, alerts):
        if not alerts:
            return "No active alerts."
        shown = alerts[:self.ACTIVE_LIST_LIMIT]
        lines = [f"Active alerts: {len(alerts)}"]
        if len(alerts) > len(shown):
            lines.append(f"Showing first {len(shown)} active alerts.")
        for alert in shown:
            lines.append(f"#{alert.id} {alert.token_symbol} current {self._price(alert.last_checked_price or alert.current_price)} target {self._price(alert.target_price)} direction {alert.direction} status active")
        return "\n".join(lines)

    def format_history(self, alerts):
        if not alerts:
            return "No triggered or deleted alerts found."
        shown = alerts[:self.HISTORY_LIMIT]
        lines = [f"#{alert.id} {alert.token_symbol} {alert.status} target {self._price(alert.target_price)}" for alert in shown]
        return "\n".join(lines)
