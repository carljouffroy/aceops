"""One open checklist item per client. Answer text does not change control flow."""

from __future__ import annotations

from typing import Any, Literal

from intake.bundle import Bundle
from intake.store import Database

Status = Literal["DONE", "PROVIDED", "N/A"]
STATUSES = ("DONE", "PROVIDED", "N/A")


class IntakeError(Exception):
    pass


def progress(bundle: Bundle, answered: set[str]) -> dict[str, int]:
    total = len(bundle.items)
    done = sum(1 for item in bundle.items if item.id in answered)
    return {"total": total, "answered": done, "remaining": total - done}


def get_next_item(db: Database, bundle: Bundle, client_id: str) -> dict[str, Any]:
    answered = db.answered_ids(client_id)
    counts = progress(bundle, answered)
    for item in bundle.items:
        if item.id in answered:
            continue
        return {
            "done": False,
            "id": item.id,
            "text": item.text,
            "why": item.why,
            "type": item.type,
            "data_spec": item.data_spec,
            "progress": counts,
        }
    return {"done": True, "progress": counts}


def get_progress(db: Database, bundle: Bundle, client_id: str) -> dict[str, int]:
    return progress(bundle, db.answered_ids(client_id))


def submit_answer(
    db: Database,
    bundle: Bundle,
    client_id: str,
    item_id: str,
    status: str,
    value: str,
    reason_if_na: str | None = None,
    client_ai_name: str | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise IntakeError("status must be DONE, PROVIDED, or N/A.")
    if not isinstance(value, str):
        raise IntakeError("value must be text.")
    if bundle.by_id(item_id) is None:
        raise IntakeError("Unknown item.")
    if status == "N/A":
        if reason_if_na is None or not reason_if_na.strip():
            raise IntakeError("reason_if_na is required when status is N/A.")
        reason: str | None = reason_if_na
    else:
        reason = None
    already = item_id in db.answered_ids(client_id)
    if not already:
        current = get_next_item(db, bundle, client_id)
        if current.get("done") or item_id != current["id"]:
            raise IntakeError("That item is not the open item.")
    db.insert_answer(
        client_id,
        item_id,
        status,
        value,
        reason,
        answered_by="client_ai",
        client_ai_name=client_ai_name,
        source="mcp",
    )
    return {"ok": True, "item_id": item_id, "status": status, "answered_by": "client_ai"}
