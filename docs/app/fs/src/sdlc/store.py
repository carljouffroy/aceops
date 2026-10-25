"""Read pipeline outputs and keep SDLC state under <source>/sdlc/.

Inputs (read only): bundle.json, item_dependencies.json, work_items.json,
overrides.json, brd.md, progress.json. State: one state.json plus the contract
views specs.json, tickets.json and status.json, and drafts/<ticket>.md.
Every file is replaced atomically.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from sdlc.config import BUNDLE_PATH, DELIVERY_ROLES, DEPENDENCIES_PATH, ROOT, SOURCES, autopilot_default

MAX_EVENTS = 400
TICKET_ID = re.compile(r"SPEC-[0-9]{3}-T[0-9]{2}")

_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _lock_for(path: Path) -> threading.RLock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path.resolve(), threading.RLock())


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return default


def write_json(path: Path, payload) -> None:
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def empty_state() -> dict:
    return {
        "version": 0,
        "specs": [],
        "tickets": [],
        "releases": [],
        "status": None,
        "outbox": [],
        "events": [],
        "last_sync": None,
        "agent": {"mode": "rules", "model": None, "error": None},
        "autopilot": autopilot_default(),
        "runs": [],
    }


class Workspace:
    """One data source (live or sample) and its SDLC state."""

    def __init__(self, input_dir: Path, *, bundle_path: Path = BUNDLE_PATH, deps_path: Path = DEPENDENCIES_PATH):
        self.input_dir = Path(input_dir)
        self.state_dir = self.input_dir / "sdlc"
        self.drafts_dir = self.state_dir / "drafts"
        self.bundle_path = bundle_path
        self.deps_path = deps_path
        self.lock = _lock_for(self.state_dir)

    @classmethod
    def for_source(cls, source: str) -> "Workspace":
        if source not in SOURCES:
            raise KeyError(source)
        return cls(SOURCES[source])

    # inputs

    def bundle(self) -> dict:
        return read_json(self.bundle_path, {"items": [], "brd_sections": {}, "roles": []})

    def dependencies(self) -> dict[str, list[str]]:
        return read_json(self.deps_path, {}).get("depends_on", {})

    def work_items(self) -> list[dict]:
        """Dispatched work items; a malformed row is skipped rather than stopping the loop."""
        rows = read_json(self.input_dir / "work_items.json", [])
        return [
            row
            for row in (rows if isinstance(rows, list) else [])
            if isinstance(row, dict)
            and isinstance(row.get("id"), str)
            and isinstance(row.get("source_item_id"), str)
            and row.get("role") in DELIVERY_ROLES
            and row.get("kind") in ("task", "gap")
        ]

    def overrides(self) -> dict[str, str]:
        payload = read_json(self.input_dir / "overrides.json", {})
        statuses = payload.get("statuses") if isinstance(payload, dict) else None
        return statuses if isinstance(statuses, dict) else {}

    def brd(self) -> str:
        try:
            return (self.input_dir / "brd.md").read_text(encoding="utf-8")
        except OSError:
            return ""

    def progress(self) -> dict | None:
        payload = read_json(self.input_dir / "progress.json", None)
        return payload if isinstance(payload, dict) else None

    def client_name(self) -> str:
        for line in self.brd().splitlines():
            if line.startswith("Client:"):
                name = line.split(":", 1)[1].strip()
                if name:
                    return name
        for row in self.work_items():
            if row.get("client_ai_name"):
                return str(row["client_ai_name"])
        return "Client"

    def inputs_signature(self) -> tuple:
        sig = []
        for name in ("work_items.json", "brd.md", "progress.json", "overrides.json"):
            path = self.input_dir / name
            try:
                stat = path.stat()
                sig.append((name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                sig.append((name, 0, 0))
        return tuple(sig)

    # state

    def load(self) -> dict:
        state = read_json(self.state_dir / "state.json", None)
        if not isinstance(state, dict):
            return empty_state()
        base = empty_state()
        base.update(state)
        return base

    def save(self, state: dict) -> dict:
        state["version"] = int(state.get("version", 0)) + 1
        state["events"] = state.get("events", [])[-MAX_EVENTS:]
        write_json(self.state_dir / "state.json", state)
        write_json(self.state_dir / "specs.json", state["specs"])
        write_json(self.state_dir / "tickets.json", state["tickets"])
        if state.get("status"):
            write_json(self.state_dir / "status.json", state["status"])
        write_json(self.state_dir / "releases.json", state["releases"])
        write_json(self.state_dir / "outbox.json", state["outbox"])
        return state

    def reset(self) -> None:
        with self.lock:
            for name in ("state.json", "specs.json", "tickets.json", "status.json", "releases.json", "outbox.json"):
                (self.state_dir / name).unlink(missing_ok=True)
            if self.drafts_dir.is_dir():
                for path in self.drafts_dir.glob("*.md"):
                    path.unlink(missing_ok=True)

    def draft_path(self, ticket_id: str) -> Path:
        if not TICKET_ID.fullmatch(ticket_id):
            raise KeyError(ticket_id)
        return self.drafts_dir / f"{ticket_id}.md"

    def read_draft(self, ticket_id: str) -> str | None:
        try:
            return self.draft_path(ticket_id).read_text(encoding="utf-8")
        except OSError:
            return None

    def write_draft(self, ticket_id: str, text: str) -> str:
        path = self.draft_path(ticket_id)
        write_text(path, text)
        try:
            return str(path.resolve().relative_to(ROOT))
        except ValueError:
            return str(path)


def emit(state: dict, actor: str, kind: str, subject: str, message: str) -> dict:
    events = state.setdefault("events", [])
    event = {
        "id": (events[-1]["id"] + 1) if events else 1,
        "at": now_iso(),
        "actor": actor,
        "kind": kind,
        "subject": subject,
        "message": message,
    }
    events.append(event)
    return event
