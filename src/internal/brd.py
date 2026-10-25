"""Render brd.md from a checklist bundle and client answers."""

from __future__ import annotations

from typing import Any

from internal.answers import (
    PROVIDED,
    answer_status,
    answer_value,
    client_name,
    index_answers,
)


def render_brd(bundle: dict, answers_payload: Any) -> str:
    answers = index_answers(answers_payload)
    sections: dict[str, str] = dict(bundle.get("brd_sections") or {})
    lines_by_section: dict[str, list[str]] = {key: [] for key in sections}
    gaps: list[str] = []

    for item in bundle["items"]:
        item_id = str(item["id"])
        answer = answers.get(item_id)
        status = answer_status(answer)
        if answer is None or status == "":
            label = _one_line(item.get("text") or "")
            prefix = "[priority] " if item.get("priority") else ""
            gaps.append(f"- {prefix}{label} ({item_id})")
            continue
        value = _one_line(answer_value(answer) or "")
        if status == "N/A":
            shown = f"N/A: {value}" if value else "N/A"
        elif status in PROVIDED:
            shown = value
        else:
            shown = value or status
        lines_by_section.setdefault(str(item.get("section", "")), []).append(
            f"- {shown} ({item_id})"
        )

    parts = ["# Business requirements", ""]
    name = client_name(answers_payload)
    if name:
        parts.append(f"Client: {_one_line(name)}")
        parts.append("")
    for key, title in sections.items():
        body = lines_by_section.get(key) or []
        if not body:
            continue
        parts.extend(_section(str(title), body))
    for key, body in lines_by_section.items():
        if key in sections or not body:
            continue
        parts.extend(_section(key, body))
    if gaps:
        parts.extend(_section("Open gaps", gaps))
    return "\n".join(parts).rstrip() + "\n"


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"## {title}", "", *lines, ""]


def _one_line(value: object) -> str:
    return " ".join(str(value).split())
