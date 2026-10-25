"""Checklist progress for the live output directory."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from internal.answers import PROVIDED, answer_status, index_answers
from internal.dispatch import build_work_items


def build_progress(bundle: dict, answers_payload: Any, *, now: str | None = None) -> dict:
    answers = index_answers(answers_payload)
    items = bundle["items"]
    total = len(items)
    answered = 0
    priority_ids: list[str] = []
    gate_open = True
    for item in items:
        status = answer_status(answers.get(str(item["id"])))
        if status:
            answered += 1
        if not item.get("priority"):
            continue
        priority_ids.append(str(item["id"]))
        if status not in PROVIDED:
            gate_open = False
    if not priority_ids:
        gate_open = True

    roles = [str(role) for role in bundle.get("roles") or []]
    for item in items:
        role = str(item["role"])
        if role not in roles:
            roles.append(role)
    by_role = {role: {"open": 0, "blocked": 0} for role in roles}
    for row in build_work_items(bundle, answers_payload):
        bucket = by_role.setdefault(str(row["role"]), {"open": 0, "blocked": 0})
        if row["status"] != "Done":
            bucket["open"] += 1
        if row["blocked_on_client"]:
            bucket["blocked"] += 1

    return {
        "total": total,
        "answered": answered,
        "remaining": total - answered,
        "priority_gate": {"ids": priority_ids, "done": gate_open},
        "by_role": by_role,
        "updated_at": now or datetime.now(timezone.utc).isoformat(),
    }
