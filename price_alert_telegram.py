"""Price Alert integration for Jayce's Telegram bot (bot.py).

Self-contained on purpose: bot.py changes by two lines only.

    from price_alert_telegram import register_price_alerts
    register_price_alerts(application)     # inside main(), before run_polling

Public commands (exactly five):
    /alert CONTRACT_ADDRESS TARGET_PRICE
    /alerts
    /deletealert ALERT_ID
    /clearalerts
    /alerthistory

Design notes
------------
* Uses the Application's own event loop. The monitoring worker is a background
  thread, so publishing crosses back via asyncio.run_coroutine_threadsafe().
* Messages are sent as PLAIN TEXT. Token names come from a third-party API and
  may contain <, > or & which would break HTML parsing. Existing Jayce messages
  keep their own parse modes and are unaffected. The single exception is the
  "Copy CA" reply, which uses an HTML <code> block for tap-to-copy.
* The worker starts only after the publisher and handlers are wired.
* Disabled by default via JACE_PRICE_ALERTS_ENABLED.

Environment
-----------
    JACE_PRICE_ALERTS_ENABLED      false | true
    JACE_PRICE_ALERT_ADMIN_IDS     comma separated Telegram user IDs
                                   (falls back to OWNER_USER_ID)
    JACE_PRICE_ALERT_DB_PATH       default /opt/jayce/data/jayce_alerts.db
    JACE_PRICE_ALERT_POLL_SECONDS  default 5, minimum 5
    TELEGRAM_CHAT_ID               destination for triggered alerts
"""

from __future__ import annotations

import asyncio
import html
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler

logger = logging.getLogger("jayce.price_alerts")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "jayce_alerts.db")
MIGRATIONS_DIR = os.path.join(BASE_DIR, "migrations")

SEND_TIMEOUT = int(os.getenv("JACE_PRICE_ALERT_SEND_TIMEOUT", "30"))

_service = None
_adapter = None
_loop = None
_chat_id = None


def _enabled() -> bool:
    return os.getenv("JACE_PRICE_ALERTS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _admin_ids() -> tuple:
    raw = os.getenv("JACE_PRICE_ALERT_ADMIN_IDS", "").strip()
    if not raw:
        raw = os.getenv("OWNER_USER_ID", "").strip()
    return tuple(value.strip() for value in raw.split(",") if value.strip())


def _poll_seconds() -> int:
    try:
        return max(5, int(os.getenv("JACE_PRICE_ALERT_POLL_SECONDS", "5")))
    except ValueError:
        return 5


def _dm_enabled() -> bool:
    return os.getenv("JACE_PRICE_ALERT_DM_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def _dm_user_id():
    """Override first, then OWNER_USER_ID, else None."""
    for name in ("JACE_PRICE_ALERT_DM_USER_ID", "OWNER_USER_ID"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return None


def _markup(buttons):
    if not buttons:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=data)] for label, data in buttons]
    )


def _in_general_chat(chat_id) -> bool:
    """Mirror Jayce's existing chat restriction. DMs stay excluded."""
    return _chat_id is not None and str(chat_id) == str(_chat_id)


async def _send(bot, text, buttons=None):
    message = await bot.send_message(
        chat_id=_chat_id,
        text=text,
        reply_markup=_markup(buttons),
        disable_web_page_preview=True,
    )
    return message.message_id


async def _send_dm_copy(bot, text, buttons):
    """Best-effort duplicate to the owner's private chat.

    DELIBERATELY SWALLOWS ALL EXCEPTIONS. The General Chat message has already
    been delivered by the time this runs. If a DM failure were allowed to
    propagate, the service would treat the whole delivery as failed, release its
    delivery claim, and resend the General Chat alert on the next cycle — a
    duplicate-alert loop. The DM is a convenience; it must never affect the
    alert's delivery status.
    """
    if not _dm_enabled():
        return
    recipient = _dm_user_id()
    if not recipient:
        logger.warning(
            "[PRICE_ALERT] DM enabled but no recipient configured "
            "(set JACE_PRICE_ALERT_DM_USER_ID or OWNER_USER_ID) — skipping DM"
        )
        return
    try:
        await bot.send_message(
            chat_id=recipient,
            text=text,
            reply_markup=_markup(buttons),
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.error(
            "[PRICE_ALERT] DM copy failed (General Chat alert already delivered, "
            "not retrying): %s: %s", type(exc).__name__, exc
        )


async def _publish(bot, text, buttons):
    """General Chat is primary. The DM copy runs only after it succeeds."""
    message_id = await _send(bot, text, buttons)
    await _send_dm_copy(bot, text, buttons)
    return message_id


def _publisher(alert):
    """Called from the worker THREAD. Bridges into the Application's loop.

    Raises on failure so the service releases its delivery claim and retries
    rather than marking an undelivered alert as triggered.
    """
    if _loop is None or _adapter is None or _bot_ref is None:
        raise RuntimeError("Price Alert Telegram transport is not wired")
    outbound = _adapter.format_triggered(alert)
    future = asyncio.run_coroutine_threadsafe(
        _publish(_bot_ref, outbound.text, outbound.buttons), _loop
    )
    return future.result(timeout=SEND_TIMEOUT)


_bot_ref = None


async def _handle(update, context, raw_text):
    """Shared body for all five commands."""
    message = update.effective_message
    if message is None:
        return
    if not _in_general_chat(message.chat_id):
        logger.warning("[PRICE_ALERT] command from non-general chat ignored")
        return
    if _adapter is None:
        return
    try:
        user = update.effective_user
        outbound = _adapter.handle_message(
            raw_text.strip(),
            user_id=user.id if user else None,
            chat_id=message.chat_id,
            update_id=update.update_id,
        )
        await _send(context.bot, outbound.text, outbound.buttons)
    except Exception as exc:
        logger.error("[PRICE_ALERT] command failed: %s: %s", type(exc).__name__, exc)
        try:
            await _send(context.bot, "Price alert command failed. Please try again.")
        except Exception:
            logger.exception("[PRICE_ALERT] could not report command failure")


def _command(name):
    async def handler(update, context):
        message = update.effective_message
        # Rebuild the raw text: python-telegram-bot splits args for us, but the
        # base58 Solana contract address is CASE-SENSITIVE and must not be
        # lowercased or normalised anywhere along the way.
        raw = message.text if message and message.text else f"/{name}"
        await _handle(update, context, raw)

    handler.__name__ = f"price_alert_{name}_command"
    return handler


async def _callback(update, context):
    query = update.callback_query
    if query is None:
        return
    data = query.data or ""
    if not data.startswith("price_alert:"):
        return
    try:
        await query.answer()
    except Exception:
        logger.warning("[PRICE_ALERT] could not answer callback query")
    chat_id = query.message.chat_id if query.message else None
    if not _in_general_chat(chat_id):
        logger.warning("[PRICE_ALERT] callback from non-general chat ignored")
        return
    if _adapter is None:
        return
    try:
        user = query.from_user
        outbound = _adapter.handle_callback(
            data, user_id=user.id if user else None, chat_id=chat_id
        )
        if data.startswith("price_alert:copy:") and outbound.text.startswith("Contract address: "):
            address = outbound.text.split("Contract address: ", 1)[1]
            await context.bot.send_message(
                chat_id=_chat_id,
                text=f"<code>{html.escape(address)}</code>",
                parse_mode="HTML",
            )
        else:
            await _send(context.bot, outbound.text, outbound.buttons)
    except Exception as exc:
        logger.error("[PRICE_ALERT] callback failed: %s: %s", type(exc).__name__, exc)


def register_price_alerts(application) -> bool:
    """Register Price Alert handlers. Returns True if the feature is active.

    Safe to call when disabled or when the package is missing: logs and returns
    False without touching the Application.
    """
    global _service, _adapter, _chat_id

    if not _enabled():
        logger.info("[PRICE_ALERT] disabled (JACE_PRICE_ALERTS_ENABLED is not true)")
        return False

    try:
        from jace.database import Database
        from jace.price_alerts.provider import DexScreenerPriceProvider
        from jace.price_alerts.service import PriceAlertService
        from jace.price_alerts.telegram_adapter import TelegramPriceAlertAdapter
    except ImportError as exc:
        logger.error("[PRICE_ALERT] enabled but package import failed: %s", exc)
        return False

    _chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not _chat_id:
        logger.error("[PRICE_ALERT] TELEGRAM_CHAT_ID not set — not registering")
        return False

    admins = _admin_ids()
    if not admins:
        logger.warning("[PRICE_ALERT] no admin IDs configured — all commands will be denied")

    try:
        db_path = os.getenv("JACE_PRICE_ALERT_DB_PATH", DEFAULT_DB_PATH)
        database = Database(db_path)
        # Migration must run BEFORE construction: the service resets stale
        # delivery claims on init, which needs the price_alerts table.
        database.migrate(MIGRATIONS_DIR)
        _service = PriceAlertService(
            database,
            DexScreenerPriceProvider(),
            admin_ids=admins,
            trigger_publisher=_publisher,
            poll_seconds=_poll_seconds(),
        )
        _adapter = TelegramPriceAlertAdapter(_service)
    except Exception as exc:
        logger.error("[PRICE_ALERT] initialisation failed: %s: %s", type(exc).__name__, exc)
        _service = None
        _adapter = None
        return False

    for name in ("alert", "alerts", "deletealert", "clearalerts", "alerthistory"):
        application.add_handler(CommandHandler(name, _command(name)))
    application.add_handler(CallbackQueryHandler(_callback, pattern=r"^price_alert:"))

    previous_init = application.post_init
    previous_shutdown = application.post_shutdown

    async def _post_init(app):
        global _loop, _bot_ref
        if previous_init is not None:
            await previous_init(app)
        _loop = asyncio.get_running_loop()
        _bot_ref = app.bot
        _service.start()
        logger.info("[PRICE_ALERT] worker started (%s admin(s), poll %ss)",
                    len(admins), _poll_seconds())

    async def _post_shutdown(app):
        try:
            if _service is not None:
                _service.stop()
        except Exception as exc:
            logger.error("[PRICE_ALERT] shutdown failed: %s", exc)
        if previous_shutdown is not None:
            await previous_shutdown(app)

    application.post_init = _post_init
    application.post_shutdown = _post_shutdown

    logger.info("[PRICE_ALERT] handlers registered — worker starts at post_init")
    return True
