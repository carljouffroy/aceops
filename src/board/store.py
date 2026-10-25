"""Read work items and progress. Status edits go to overrides.json only."""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

STATUSES = ("To do", "In progress", "Blocked", "Done")
ROLES = ("Marketing Specialist", "Data Analyst", "Developer")
ITEM_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")
_STATUS_RANK = {"In progress": 0, "Blocked": 1, "To do": 2, "Done": 3}
_SKIP_DOMAINS = {"example", "gmail", "googlemail", "outlook", "hotmail", "ace"}
_LOCK = threading.Lock()


class DataError(Exception):
    pass


def default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_board(root: Path) -> dict:
    out = root / "data" / "out"
    work_path = out / "work_items.json"
    sample_path = root / "contracts" / "work_items.sample.json"
    if work_path.is_file():
        items = _read_items(work_path)
        recorded = _read_progress(out / "progress.json")
        brd_name = _client_from_brd(out / "brd.md")
        source = "out"
    elif sample_path.is_file():
        items = _read_items(sample_path)
        recorded = None
        brd_name = None
        source = "sample"
    else:
        items = []
        recorded = None
        brd_name = None
        source = "empty"

    overrides = _read_overrides(out / "overrides.json")
    merged = [_with_status(item, overrides.get(item["id"])) for item in items]
    merged.sort(key=_sort_key)
    progress = recorded or _derive(merged)
    client_name = progress.get("client_name") or brd_name or _name_from_items(merged) or "Client"
    return {
        "client_name": client_name,
        "source": source,
        "progress": {
            "answered": progress["answered"],
            "total": progress["total"],
            "priority_gate_done": progress["priority_gate_done"],
        },
        "counts": _counts(merged),
        "items": merged,
    }


def set_status(root: Path, item_id: str, status: str) -> dict:
    if status not in STATUSES:
        raise ValueError(status)
    if not ITEM_ID.fullmatch(item_id):
        raise KeyError(item_id)
    path = root / "data" / "out" / "overrides.json"
    with _LOCK:
        current = load_board(root)
        if not any(item["id"] == item_id for item in current["items"]):
            raise KeyError(item_id)
        overrides = _read_overrides(path)
        overrides[item_id] = status
        _write_json(path, {"statuses": overrides})
        updated = load_board(root)
    return next(item for item in updated["items"] if item["id"] == item_id)


def _sort_key(item: dict) -> tuple:
    """Open items first, then priority, then status."""
    return (
        0 if item["status"] != "Done" else 1,
        0 if item["priority"] else 1,
        _STATUS_RANK.get(item["status"], 9),
        str(item.get("source_item_id") or ""),
        item["id"],
    )


def _counts(items: list[dict]) -> dict:
    roles = {role: 0 for role in ROLES}
    blocked = 0
    for item in items:
        role = str(item["role"])
        roles[role] = roles.get(role, 0) + 1
        if item["blocked_on_client"]:
            blocked += 1
    return {"all": len(items), "roles": roles, "blocked_on_client": blocked}


def _derive(items: list[dict]) -> dict:
    priority = [item for item in items if item["priority"]]
    gate = all(item.get("client_answer") for item in priority) if priority else True
    answered = sum(1 for item in items if item.get("client_answer"))
    return {
        "answered": answered,
        "total": len(items),
        "priority_gate_done": gate,
        "client_name": None,
    }


def _with_status(item: dict, status: str | None) -> dict:
    row = dict(item)
    if status in STATUSES:
        row["status"] = status
    return row


def _read_items(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise DataError("Work items could not be read") from exc
    if not isinstance(payload, list):
        raise DataError("Work items could not be read")
    items = []
    for row in payload:
        item = _normalize(row)
        if item is not None:
            items.append(item)
    return items


def _normalize(row: object) -> dict | None:
    if not isinstance(row, dict):
        return None
    item_id = row.get("id")
    if not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id):
        return None
    status = row.get("status")
    if status not in STATUSES:
        status = "To do"
    title = row.get("title")
    title_text = title.strip() if isinstance(title, str) else ""
    return {
        "id": item_id,
        "title": title_text or item_id,
        "role": _plain(row.get("role")) or "",
        "source_item_id": _plain(row.get("source_item_id")) or "",
        "kind": _plain(row.get("kind")) or "",
        "priority": bool(row.get("priority")),
        "status": status,
        "blocked_on_client": bool(row.get("blocked_on_client")),
        "due": _plain(row.get("due")),
        "client_answer": _answer(row.get("client_answer")),
        "answered_by": _plain(row.get("answered_by")),
        "client_ai_name": _plain(row.get("client_ai_name")),
        "ts": _plain(row.get("ts")),
    }


def _answer(value: object) -> str | None:
    if not isinstance(value, str) or value == "":
        return None
    return value


def _plain(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _read_progress(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(payload, dict):
        return None
    gate = payload.get("priority_gate")
    if not isinstance(gate, dict) or "done" not in gate:
        return None
    try:
        answered = int(payload["answered"])
        total = int(payload["total"])
    except (KeyError, TypeError, ValueError):
        return None
    if answered < 0 or total < 0:
        return None
    name = payload.get("client_name")
    return {
        "answered": answered,
        "total": total,
        "priority_gate_done": bool(gate.get("done")),
        "client_name": name.strip() if isinstance(name, str) and name.strip() else None,
    }


def _client_from_brd(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines[:40]:
        if line.startswith("Client:"):
            name = line.split(":", 1)[1].strip()
            return name or None
    return None


def _name_from_items(items: list[dict]) -> str | None:
    labels: list[str] = []
    for item in items:
        who = item.get("answered_by") or ""
        if "@" not in who:
            continue
        host = who.split("@", 1)[1].lower()
        label = host.split(".", 1)[0]
        if label and label not in _SKIP_DOMAINS:
            labels.append(label)
    if not labels:
        return None
    best = max(set(labels), key=labels.count)
    return best.replace("-", " ").replace("_", " ").title()


def _read_overrides(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}
    raw = payload.get("statuses") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}
    clean: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and ITEM_ID.fullmatch(key) and value in STATUSES:
            clean[key] = value
    return clean


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
