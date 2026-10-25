"""Load checklist answers. Values stay data: they are never evaluated."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROVIDED = frozenset({"DONE", "PROVIDED"})


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def index_answers(payload: Any) -> dict[str, dict]:
    rows = payload["answers"] if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("answers must be a list")
    indexed: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = _field(row, "id", "ID")
        if item_id is None or item_id == "":
            continue
        indexed[str(item_id)] = row
    return indexed


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
