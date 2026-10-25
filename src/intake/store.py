"""SQLite storage. Client text is stored as data and never interpreted."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS answers (
    client_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    status TEXT NOT NULL,
    value TEXT NOT NULL,
    reason_if_na TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (client_id, item_id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.transaction() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def create_client(self) -> tuple[str, str]:
        client_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        created = _now()
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO clients (id, token_hash, created_at) VALUES (?, ?, ?)",
                (client_id, hash_token(token), created),
            )
            conn.execute(
                "INSERT INTO events (client_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
                (
                    client_id,
                    "client_created",
                    json.dumps({"client_id": client_id}),
                    created,
                ),
            )
        return client_id, token

    def client_id_for_token(self, token: str) -> str | None:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM clients WHERE token_hash = ?",
                (hash_token(token),),
            ).fetchone()
        if row is None:
            return None
        return str(row["id"])

    def client_exists(self, client_id: str) -> bool:
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM clients WHERE id = ?",
                (client_id,),
            ).fetchone()
        return row is not None

    def token_is_stored_raw(self, token: str) -> bool:
        with self.transaction() as conn:
            rows = conn.execute("SELECT token_hash FROM clients").fetchall()
        return any(row["token_hash"] == token for row in rows)

    def answered_ids(self, client_id: str) -> set[str]:
        with self.transaction() as conn:
            rows = conn.execute(
                "SELECT item_id FROM answers WHERE client_id = ?",
                (client_id,),
            ).fetchall()
        return {str(row["item_id"]) for row in rows}

    def insert_answer(
        self,
        client_id: str,
        item_id: str,
        status: str,
        value: str,
        reason_if_na: str | None,
    ) -> None:
        """Persist value unchanged. The text is not parsed or executed."""
        created = _now()
        payload = json.dumps(
            {
                "item_id": item_id,
                "status": status,
                "value": value,
                "reason_if_na": reason_if_na,
            },
            ensure_ascii=False,
        )
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO answers (client_id, item_id, status, value, reason_if_na, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (client_id, item_id, status, value, reason_if_na, created),
            )
            conn.execute(
                "INSERT INTO events (client_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
                (client_id, "answer_submitted", payload, created),
            )

    def answers_for(self, client_id: str) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute(
                """
                SELECT item_id, status, value, reason_if_na, created_at
                FROM answers
                WHERE client_id = ?
                ORDER BY created_at, item_id
                """,
                (client_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def events_for(self, client_id: str) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, kind, payload, created_at
                FROM events
                WHERE client_id = ?
                ORDER BY id
                """,
                (client_id,),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            events.append(
                {
                    "id": row["id"],
                    "kind": row["kind"],
                    "payload": json.loads(row["payload"]),
                    "created_at": row["created_at"],
                }
            )
        return events
