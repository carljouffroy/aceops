"""Dispatch work items from checklist rows.

DONE or PROVIDED uses task_if_answered and the item role.
A row with no task_if_answered is closed and produces no work item.
A missing answer or N/A uses task_if_gap and the same role.
Answer text is copied onto the work item and does not choose the route.
"""

from __future__ import annotations

from typing import Any

from internal.answers import PROVIDED, answer_status, answer_value, index_answers


def build_work_items(bundle: dict, answers_payload: Any) -> list[dict]:
    answers = index_answers(answers_payload)
    work: list[dict] = []
    for item in bundle["items"]:
        answer = answers.get(str(item["id"]))
        status = answer_status(answer)
        if status in PROVIDED:
            title = item.get("task_if_answered")
            if not title:
                continue
            kind = "task"
            state = "To do"
            blocked = False
        else:
            title = item.get("task_if_gap") or item.get("text") or item["id"]
            kind = "gap"
            state = "Blocked"
            blocked = True
        work.append(
            {
                "id": f"WI-{item['id']}",
                "title": str(title),
                "role": item["role"],
                "source_item_id": item["id"],
                "kind": kind,
                "priority": bool(item.get("priority", False)),
                "status": state,
                "blocked_on_client": blocked,
                "due": None,
                "client_answer": answer_value(answer),
            }
        )
    return work
