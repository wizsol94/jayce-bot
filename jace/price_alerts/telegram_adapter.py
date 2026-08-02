from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .commands import CommandError
from .provider import PriceProviderError


@dataclass(frozen=True)
class OutboundMessage:
    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)


class TelegramPriceAlertAdapter:
    """Dependency-free seam for the existing Telegram transport.

    The JACE checkout currently has no Telegram library or handler registry, so
    this adapter intentionally does not import or alter one. A bot handler can
    pass message text/user/chat/update IDs and send the returned message/buttons.
    """

    def __init__(self, service):
        self.service = service

    def handle_message(self, text, *, user_id, chat_id, update_id=None) -> OutboundMessage:
        try:
            result = self.service.handle_command(text, user_id=user_id, chat_id=chat_id, update_id=update_id)
        except (CommandError, PriceProviderError) as exc:
            return OutboundMessage(str(exc))
        buttons = []
        try:
            is_clear = text.strip().lower().split()[0].split("@", 1)[0] == "/clearalerts"
        except IndexError:
            is_clear = False
        if is_clear:
            buttons = [("Confirm delete all", "price_alert:clear:confirm"), ("Cancel", "price_alert:clear:cancel")]
        return OutboundMessage(result, buttons)

    def handle_callback(self, callback_data, *, user_id, chat_id) -> OutboundMessage:
        parts = callback_data.split(":")
        if len(parts) != 3 or parts[0] != "price_alert":
            return OutboundMessage("Unknown alert action.")
        if not self.service.is_authorized(user_id):
            return OutboundMessage("Permission denied.")
        if parts[1] == "clear":
            return OutboundMessage(self.service.handle_clear_callback(parts[2], user_id=user_id, chat_id=chat_id))
        try:
            alert = self.service.repository.get(int(parts[2]))
        except (ValueError, KeyError):
            return OutboundMessage("Alert was not found.")
        if parts[1] == "open":
            return OutboundMessage(f"Open Dex Screener: https://dexscreener.com/solana/{alert.pair_address}")
        if parts[1] == "copy":
            return OutboundMessage(f"Contract address: {alert.contract_address}")
        if parts[1] == "new":
            return OutboundMessage("Create a new alert with /alert CONTRACT_ADDRESS TARGET_PRICE")
        return OutboundMessage("Unknown alert action.")

    def format_triggered(self, alert) -> OutboundMessage:
        text = (
            "Price alert triggered\n"
            f"Alert ID: {alert.id}\n"
            f"Token: {alert.token_name} ({alert.token_symbol})\n"
            f"Contract: {alert.contract_address}\n"
            f"Direction: {alert.direction}\n"
            f"Created price: {self._plain(alert.current_price)}\n"
            f"Target price: {self._plain(alert.target_price)}\n"
            f"Trigger price: {self._plain(alert.last_checked_price)}\n"
            f"Created: {alert.created_at}\n"
            f"Time active: {self._elapsed(alert.created_at)}\n"
            "Status: target hit\n"
            f"Chart: https://dexscreener.com/solana/{alert.pair_address}"
        )
        buttons = [
            ("Open DexScreener", f"price_alert:open:{alert.id}"),
            ("Copy CA", f"price_alert:copy:{alert.id}"),
            ("Create new alert", "price_alert:new:0"),
        ]
        return OutboundMessage(text, buttons)

    @staticmethod
    def _plain(value):
        return "unknown" if value is None else format(value, "f")

    @staticmethod
    def _elapsed(created_at):
        try:
            created = datetime.fromisoformat(created_at)
        except (TypeError, ValueError):
            return "unknown"
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        seconds = int((datetime.now(timezone.utc) - created).total_seconds())
        if seconds < 0:
            return "unknown"
        days, seconds = divmod(seconds, 86400)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
