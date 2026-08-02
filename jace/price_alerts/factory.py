from __future__ import annotations

from .config import admin_ids, enabled, poll_seconds
from .provider import DexScreenerPriceProvider
from .service import PriceAlertService


def build_price_alert_service(database, trigger_publisher=None):
    if not enabled():
        return None
    return PriceAlertService(
        database,
        DexScreenerPriceProvider(),
        admin_ids=admin_ids(),
        trigger_publisher=trigger_publisher,
        poll_seconds=poll_seconds(),
    )
