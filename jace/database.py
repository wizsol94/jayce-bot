"""Isolated SQLite access layer for the Price Alert module.

This module deliberately does NOT touch Jayce's main database (DB_PATH /
jayce_memory.db). Price Alerts own a separate file so that:

  * the background worker thread never contends for locks with the scanner
  * scanner memory/training data cannot be corrupted by this feature
  * rollback is "delete one file"

It exposes only the three methods the price_alerts package actually uses:
connect(), query() and migrate().
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB_PATH = "/app/jayce_alerts.db"


def price_alert_db_path() -> str:
    return os.getenv("JACE_PRICE_ALERT_DB_PATH", DEFAULT_DB_PATH)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin sqlite3 wrapper matching the interface price_alerts expects."""

    def __init__(self, path=None):
        self.path = str(path) if path is not None else price_alert_db_path()
        parent = Path(self.path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def query(self, sql, params=()):
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def migrate(self, directory):
        directory = Path(directory)
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row[0]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for migration in sorted(directory.glob("*.sql")):
                if migration.name in applied:
                    continue
                connection.executescript(migration.read_text())
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?)",
                    (migration.name, now()),
                )
