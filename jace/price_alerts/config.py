from __future__ import annotations

import os


def enabled() -> bool:
    return os.getenv("JACE_PRICE_ALERTS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def admin_ids() -> tuple[str, ...]:
    return tuple(value.strip() for value in os.getenv("JACE_PRICE_ALERT_ADMIN_IDS", "").split(",") if value.strip())


def poll_seconds() -> int:
    try:
        return max(5, int(os.getenv("JACE_PRICE_ALERT_POLL_SECONDS", "5")))
    except ValueError:
        return 5

