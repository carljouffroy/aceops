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
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

ANSWERS_SCHEMA = """
CREATE TABLE answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    status TEXT NOT NULL,
    value TEXT NOT NULL,
    reason_if_na TEXT,
    answered_by TEXT NOT NULL CHECK (answered_by IN ('client', 'client_ai')),
    client_ai_name TEXT,
    source TEXT NOT NULL DEFAULT 'mcp',
    created_at TEXT NOT NULL
);
CREATE INDEX idx_answers_client_item_id ON answers (client_id, item_id, id);
"""

ANSWERED_BY = ("client", "client_ai")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _answer_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "item_id": row["item_id"],
        "status": row["status"],
        "value": row["value"],
        "reason_if_na": row["reason_if_na"],
        "answered_by": row["answered_by"],
        "client_ai_name": row["client_ai_name"],
        "source": row["source"],
        "ts": row["created_at"],
    }


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.transaction() as conn:
            conn.executescript(SCHEMA)
            self._migrate_answers(conn)

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

    def _migrate_answers(self, conn: sqlite3.Connection) -> None:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(answers)").fetchall()]
        if not columns:
            conn.executescript(ANSWERS_SCHEMA)
            return
        if "id" in columns and "answered_by" in columns:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_answers_client_item_id ON answers (client_id, item_id, id)"
            )
            return
        conn.execute("ALTER TABLE answers RENAME TO answers_legacy")
        conn.executescript(ANSWERS_SCHEMA)
        conn.execute(
            """
            INSERT INTO answers (
                client_id, item_id, status, value, reason_if_na,
                answered_by, client_ai_name, source, created_at
            )
            SELECT client_id, item_id, status, value, reason_if_na,
                   'client_ai', NULL, 'mcp', created_at
            FROM answers_legacy
            """
        )
        conn.execute("DROP TABLE answers_legacy")

    def answered_ids(self, client_id: str) -> set[str]:
        with self.transaction() as conn:
            rows = conn.execute(
                "SELECT DISTINCT item_id FROM answers WHERE client_id = ?",
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
        answered_by: str = "client_ai",
        client_ai_name: str | None = None,
        source: str = "mcp",
    ) -> int:
        """Append one row. The value is stored unchanged and is never executed."""
        if answered_by not in ANSWERED_BY:
            raise ValueError("answered_by must be client or client_ai")
        created = _now()
        name = client_ai_name.strip() if isinstance(client_ai_name, str) and client_ai_name.strip() else None
        payload = json.dumps(
            {
                "item_id": item_id,
                "status": status,
                "value": value,
                "reason_if_na": reason_if_na,
                "answered_by": answered_by,
                "client_ai_name": name,
                "source": source,
            },
            ensure_ascii=False,
        )
        with self.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO answers (
                    client_id, item_id, status, value, reason_if_na,
                    answered_by, client_ai_name, source, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (client_id, item_id, status, value, reason_if_na, answered_by, name, source, created),
            )
            conn.execute(
                "INSERT INTO events (client_id, kind, payload, created_at) VALUES (?, ?, ?, ?)",
                (client_id, "answer_submitted", payload, created),
            )
            return int(cursor.lastrowid)

    def answers_for(self, client_id: str) -> list[dict[str, Any]]:
        """Latest row for each item this client has answered."""
        with self.transaction() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.item_id, a.status, a.value, a.reason_if_na,
                       a.answered_by, a.client_ai_name, a.source, a.created_at
                FROM answers a
                INNER JOIN (
                    SELECT item_id, MAX(id) AS id
                    FROM answers
                    WHERE client_id = ?
                    GROUP BY item_id
                ) latest ON a.id = latest.id
                WHERE a.client_id = ?
                ORDER BY a.id
                """,
                (client_id, client_id),
            ).fetchall()
        return [_answer_row(row) for row in rows]

    def answer_history(self, client_id: str) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, item_id, status, value, reason_if_na,
                       answered_by, client_ai_name, source, created_at
                FROM answers
                WHERE client_id = ?
                ORDER BY id
                """,
                (client_id,),
            ).fetchall()
        return [_answer_row(row) for row in rows]

    def events_for(self, client_id: str, since: int | None = None) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            if since is None:
                rows = conn.execute(
                    """
                    SELECT id, kind, payload, created_at
                    FROM events
                    WHERE client_id = ?
                    ORDER BY id
                    """,
                    (client_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, kind, payload, created_at
                    FROM events
                    WHERE client_id = ? AND id > ?
                    ORDER BY id
                    """,
                    (client_id, since),
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
