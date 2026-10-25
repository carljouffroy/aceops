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
            gaps.append(f"- {prefix}{label} {_provenance(None, item_id)}")
            continue
        value = _one_line(answer_value(answer) or "")
        if status == "N/A":
            shown = f"N/A: {value}" if value else "N/A"
        elif status in PROVIDED:
            shown = value
        else:
            shown = value or status
        block = [f"- {shown} {_provenance(answer, item_id)}"]
        block.extend(_history_lines(answer, item_id))
        lines_by_section.setdefault(str(item.get("section", "")), []).extend(block)

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


def _provenance(answer: dict | None, item_id: str) -> str:
    who = _who(answer)
    stamp = _one_line(answer.get("ts")) if answer and answer.get("ts") else "-"
    return f"({item_id}) answered_by={who} ts={stamp}"


def _history_lines(answer: dict, item_id: str) -> list[str]:
    lines = []
    for old in answer.get("history") or []:
        if not isinstance(old, dict):
            continue
        value = _one_line(old.get("value") or "")
        lines.append(f"  - previous: {value} {_provenance(old, item_id)}")
    return lines


def _who(answer: dict | None) -> str:
    if not answer:
        return "-"
    who = _one_line(answer.get("answered_by") or "")
    name = _one_line(answer.get("client_ai_name") or "")
    if who and name:
        return f"{who} name={name}"
    return who or name or "-"


def _one_line(value: object) -> str:
    return " ".join(str(value).split())
