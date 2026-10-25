"""Load checklist answers. Values stay data: they are never evaluated."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROVIDED = frozenset({"DONE", "PROVIDED"})


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def checklist_id(row: dict) -> str | None:
    """Checklist item id.

    The admin API uses item_id. Its id field is the answer row id.
    Offline files use id for the checklist item.
    """
    if "item_id" in row and row["item_id"] not in (None, ""):
        return str(row["item_id"])
    item_id = _field(row, "id", "ID")
    if item_id is None or item_id == "":
        return None
    return str(item_id)


def index_answers(payload: Any) -> dict[str, dict]:
    """Latest answer per checklist item. Older rows are kept on history."""
    rows = payload["answers"] if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("answers must be a list")
    ordered = [
        (index, row)
        for index, row in enumerate(rows)
        if isinstance(row, dict) and checklist_id(row)
    ]
    ordered.sort(key=lambda pair: _sequence(pair[1], pair[0]))
    indexed: dict[str, dict] = {}
    for _, row in ordered:
        current = normalize_answer(row)
        item_id = current["id"]
        previous = indexed.get(item_id)
        if previous is None:
            indexed[item_id] = current
            continue
        if _snapshot(previous) == _snapshot(current):
            if len(current["history"]) > len(previous["history"]):
                indexed[item_id] = current
            continue
        current["history"] = [
            *previous["history"],
            _archive(previous),
            *current["history"],
        ]
        indexed[item_id] = current
    return indexed


def normalize_answer(row: dict) -> dict:
    item_id = checklist_id(row) or ""
    history = []
    raw_history = row.get("history")
    if isinstance(raw_history, list):
        for old in raw_history:
            if isinstance(old, dict):
                history.append(_archive(old, item_id))
    return {
        "id": item_id,
        "status": answer_status(row),
        "value": _stored_value(row),
        "answered_by": _text_or_none(row, "answered_by"),
        "client_ai_name": _text_or_none(row, "client_ai_name"),
        "ts": answer_ts(row),
        "history": history,
    }


def client_name(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    name = payload.get("client_name")
    if name is None or name == "":
        return None
    return str(name)


def answer_status(answer: dict | None) -> str:
    if not answer:
        return ""
    status = _field(answer, "status", "STATUS")
    if status is None:
        return ""
    return str(status).strip().upper()


def answer_value(answer: dict | None) -> str | None:
    if not answer:
        return None
    value = _field(answer, "value")
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def answer_ts(answer: dict | None) -> str | None:
    if not answer:
        return None
    return _text_or_none(answer, "ts", "created_at")


def _stored_value(row: dict) -> str | None:
    value = answer_value(row)
    if value is not None and value.strip():
        return value
    reason = _field(row, "reason_if_na")
    if reason is None or reason == "":
        return value
    return reason if isinstance(reason, str) else str(reason)


def _text_or_none(row: dict, *names: str) -> str | None:
    value = _field(row, *names)
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = text.strip()
    return text or None


def _sequence(row: dict, index: int) -> tuple[str, int, int]:
    ts = answer_ts(row) or ""
    seq = index
    if "item_id" in row:
        try:
            seq = int(row.get("id"))
        except (TypeError, ValueError):
            seq = index
    return (ts, seq, index)


def _snapshot(answer: dict) -> tuple:
    return (
        answer.get("status"),
        answer.get("value"),
        answer.get("answered_by"),
        answer.get("client_ai_name"),
        answer.get("ts"),
    )


def _archive(answer: dict, item_id: str | None = None) -> dict:
    source = item_id or answer.get("source_item_id") or answer.get("id") or ""
    return {
        "value": answer.get("value"),
        "status": answer.get("status") or "",
        "answered_by": answer.get("answered_by"),
        "client_ai_name": answer.get("client_ai_name"),
        "ts": answer.get("ts"),
        "source_item_id": str(source),
    }


def _field(row: dict, *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    folded = {str(key).lower(): value for key, value in row.items()}
    for name in names:
        key = name.lower()
        if key in folded:
            return folded[key]
    return None
