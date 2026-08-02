from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .models import PriceAlert, PriceQuote


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PriceAlertRepository:
    def __init__(self, database):
        self.database = database

    def create(self, *, user_id, source_chat_id, destination_chat_id, quote: PriceQuote, target: Decimal, command_text, update_id=None) -> PriceAlert:
        created = utc_now()
        direction = "up" if quote.price < target else "down"
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO price_alerts
                (creator_user_id,source_chat_id,destination_chat_id,contract_address,token_name,token_symbol,pair_address,price_source,current_price,target_price,direction,previous_checked_price,last_checked_price,created_at,status,created_command_text,source_update_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(user_id), str(source_chat_id), str(destination_chat_id), quote.address, quote.name, quote.symbol, quote.pair_address, quote.source, str(quote.price), str(target), direction, str(quote.price), str(quote.price), created, "active", command_text, str(update_id) if update_id is not None else None),
            )
            alert_id = cursor.lastrowid
        return self.get(alert_id)

    def get(self, alert_id: int) -> PriceAlert:
        rows = self.database.query("SELECT * FROM price_alerts WHERE id=?", (alert_id,))
        if not rows:
            raise KeyError(alert_id)
        return self._from_row(rows[0])

    def active(self, destination_chat_id=None) -> list[PriceAlert]:
        sql = "SELECT * FROM price_alerts WHERE status='active'"
        params = ()
        if destination_chat_id is not None:
            sql += " AND destination_chat_id=?"
            params = (str(destination_chat_id),)
        return [self._from_row(row) for row in self.database.query(sql + " ORDER BY id", params)]

    def history(self, destination_chat_id=None, limit=20) -> list[PriceAlert]:
        sql = "SELECT * FROM price_alerts WHERE status IN ('triggered','deleted','error')"
        params = []
        if destination_chat_id is not None:
            sql += " AND destination_chat_id=?"
            params.append(str(destination_chat_id))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [self._from_row(row) for row in self.database.query(sql, tuple(params))]

    def mark_deleted(self, alert_id: int) -> bool:
        with self.database.connect() as connection:
            cursor = connection.execute("UPDATE price_alerts SET status='deleted' WHERE id=? AND status='active'", (alert_id,))
        return cursor.rowcount == 1

    def clear_active(self, destination_chat_id) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute("UPDATE price_alerts SET status='deleted' WHERE destination_chat_id=? AND status='active'", (str(destination_chat_id),))
        return cursor.rowcount

    def update_check(self, alert_id: int, previous: Decimal, current: Decimal, checked_at: str, error_status=None, pair_address=None) -> None:
        with self.database.connect() as connection:
            if pair_address:
                connection.execute("UPDATE price_alerts SET previous_checked_price=?,last_checked_price=?,last_successful_check_at=?,error_status=?,pair_address=? WHERE id=? AND status='active'", (str(previous), str(current), checked_at, error_status, pair_address, alert_id))
            else:
                connection.execute("UPDATE price_alerts SET previous_checked_price=?,last_checked_price=?,last_successful_check_at=?,error_status=? WHERE id=? AND status='active'", (str(previous), str(current), checked_at, error_status, alert_id))

    def claim_for_trigger(self, alert_id: int, current: Decimal, checked_at: str, pair_address=None) -> bool:
        """Atomically claim an active alert for delivery.

        Records the crossing price so the outbound message shows the real
        trigger price, but does NOT mark the alert triggered. Returns False if
        the alert is not active or is already claimed by another worker.
        """
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE price_alerts SET previous_checked_price=last_checked_price,"
                "last_checked_price=?,last_successful_check_at=?,trigger_claimed_at=?,"
                "error_status=NULL" + (",pair_address=?" if pair_address else "") +
                " WHERE id=? AND status='active' AND trigger_claimed_at IS NULL",
                ((str(current), checked_at, checked_at, pair_address, alert_id)
                 if pair_address else (str(current), checked_at, checked_at, alert_id)),
            )
        return cursor.rowcount == 1

    def mark_delivered(self, alert_id: int, delivered_at: str, message_id=None) -> bool:
        """Finalise a claimed alert only after Telegram delivery succeeded."""
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE price_alerts SET status='triggered',triggered_at=?,trigger_message_id=? "
                "WHERE id=? AND status='active' AND trigger_claimed_at IS NOT NULL",
                (delivered_at, str(message_id) if message_id is not None else None, alert_id),
            )
        return cursor.rowcount == 1

    def release_claim(self, alert_id: int, reason=None) -> None:
        """Return a claimed-but-undelivered alert to the active pool for retry.

        The claim advanced last_checked_price to the crossing price. That must be
        rewound, otherwise the next cycle compares the crossing price against
        itself, sees no crossing, and the alert silently never retries.
        """
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE price_alerts SET trigger_claimed_at=NULL,"
                "last_checked_price=COALESCE(previous_checked_price,last_checked_price),"
                "error_status=? WHERE id=? AND status='active'",
                (reason, alert_id),
            )

    def reset_stale_claims(self) -> int:
        """Clear claims that survived a restart; those were never delivered.

        Also rewinds the checked price, for the same reason as release_claim.
        """
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE price_alerts SET trigger_claimed_at=NULL,"
                "last_checked_price=COALESCE(previous_checked_price,last_checked_price) "
                "WHERE status='active' AND trigger_claimed_at IS NOT NULL"
            )
        return cursor.rowcount

    def set_error(self, alert_id: int, message: str) -> None:
        with self.database.connect() as connection:
            connection.execute("UPDATE price_alerts SET error_status=? WHERE id=? AND status='active'", (message, alert_id))

    def claim_update(self, chat_id, update_id) -> bool:
        if update_id is None:
            return True
        try:
            with self.database.connect() as connection:
                connection.execute("INSERT INTO price_alert_update_claims(source_chat_id,source_update_id,claimed_at) VALUES(?,?,?)", (str(chat_id), str(update_id), utc_now()))
            return True
        except Exception:
            return False

    def update_pair(self, alert_id: int, pair_address: str) -> None:
        with self.database.connect() as connection:
            connection.execute("UPDATE price_alerts SET pair_address=? WHERE id=? AND status='active'", (pair_address, alert_id))

    def request_clear_confirmation(self, user_id, chat_id, ttl_seconds=60):
        created = datetime.now(timezone.utc)
        expires = created + timedelta(seconds=ttl_seconds)
        with self.database.connect() as connection:
            connection.execute("INSERT INTO price_alert_clear_confirmations(requester_user_id,chat_id,expires_at,created_at) VALUES(?,?,?,?) ON CONFLICT(requester_user_id,chat_id) DO UPDATE SET expires_at=excluded.expires_at,created_at=excluded.created_at", (str(user_id), str(chat_id), expires.isoformat(), created.isoformat()))

    def consume_clear_confirmation(self, user_id, chat_id) -> bool:
        rows = self.database.query("SELECT expires_at FROM price_alert_clear_confirmations WHERE requester_user_id=? AND chat_id=?", (str(user_id), str(chat_id)))
        with self.database.connect() as connection:
            connection.execute("DELETE FROM price_alert_clear_confirmations WHERE requester_user_id=? AND chat_id=?", (str(user_id), str(chat_id)))
        if not rows:
            return False
        try:
            return datetime.fromisoformat(rows[0]["expires_at"]) > datetime.now(timezone.utc)
        except ValueError:
            return False

    @staticmethod
    def _from_row(row) -> PriceAlert:
        decimal = lambda value: Decimal(value) if value is not None else None
        return PriceAlert(
            id=row["id"], creator_user_id=row["creator_user_id"], source_chat_id=row["source_chat_id"], destination_chat_id=row["destination_chat_id"], contract_address=row["contract_address"], token_name=row["token_name"], token_symbol=row["token_symbol"], pair_address=row["pair_address"], price_source=row["price_source"], current_price=decimal(row["current_price"]), target_price=decimal(row["target_price"]), direction=row["direction"], previous_checked_price=decimal(row["previous_checked_price"]), last_checked_price=decimal(row["last_checked_price"]), created_at=row["created_at"], last_successful_check_at=row["last_successful_check_at"], triggered_at=row["triggered_at"], status=row["status"], error_status=row["error_status"], trigger_message_id=row["trigger_message_id"], created_command_text=row["created_command_text"],
        )
