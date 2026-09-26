"""SQLite dedup so one Gmail message id is notified once per account."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


class DedupStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                account TEXT NOT NULL,
                message_id TEXT NOT NULL,
                classification TEXT NOT NULL,
                notified_at TEXT NOT NULL,
                PRIMARY KEY (account, message_id)
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> DedupStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def already_notified(self, account: str, message_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM notifications WHERE account = ? AND message_id = ?",
                (account, message_id),
            ).fetchone()
        return row is not None

    def mark_notified(self, account: str, message_id: str, classification: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO notifications (account, message_id, classification, notified_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account, message_id) DO NOTHING
                """,
                (
                    account,
                    message_id,
                    classification,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._conn.commit()
