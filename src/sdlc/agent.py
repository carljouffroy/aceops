"""What the SDLC agent writes: build drafts, review pre-checks, release notes, status.

Everything here is rules first and works with no model. Client answers are
quoted as data. Derived numbers are prefixed with "≈" so the traceability
pre-check can tell them apart from numbers the client gave us.
"""

from __future__ import annotations

import re
from datetime import date

from sdlc.config import DELIVERY_ROLES

SENTENCE = re.compile(r"\.(?=\s|$)|\n|;")
LIST_SPLIT = re.compile(r",(?!\d)")
LIST_ITEM = re.compile(r"([A-Za-z][A-Za-z &/'-]*?)\s+((?:EUR\s*)?\d+(?:\.\d+)?\s*%?)")
FIRST_NUMBER = re.compile(r"(?<![\w/.-])(?:EUR\s*)?\d")
NUMBER = re.compile(r"(?<![\w≈.#/-])(\d+(?:[.,]\d+)?)(?![\w])")
ACCOUNT_ID = re.compile(r"\b(?:G-[A-Z0-9]{6,}|\d{3}-\d{3}-\d{4})\b")

WORKING = "## Working draft"

ROLE_STEPS = {
    "Data Analyst": [
        "Load the source the client named and record its period and row count.",
        "Build the table in the working draft from the client's figures only.",
        "Mark every derived figure and write down each assumption.",
        "Reconcile totals with the client's own source before review.",
    ],
    "Marketing Specialist": [
        "Read the profit model and the client's exclusions first.",
        "Write the recommendation against break-even, not revenue.",
        "List anything that needs the client's confirmation before launch.",
        "Do not change the live account until release is approved.",
    ],
    "Developer": [
        "Name every account, property and feed you checked.",
        "Record what you saw, not what should be there.",
        "Put any fix in a sandbox branch with a test; never edit the client's live store.",
        "Flag risks with the data they affect.",
    ],
}


def facts(text: str | None) -> list[tuple[str, str]]:
    """Split a client answer into (label, value) pairs."""
    out: list[tuple[str, str]] = []
    for sentence in SENTENCE.split(text or ""):
        line = sentence.strip(" -\t")
        if not line:
            continue
        head, sep, tail = line.partition(":")
        body = tail if sep and not head.lower().startswith("http") else line
        parts = [p.strip() for p in LIST_SPLIT.split(body) if p.strip()]
        if len(parts) > 1 and all(LIST_ITEM.fullmatch(p) for p in parts):
            for part in parts:
                match = LIST_ITEM.fullmatch(part)
                out.append((match.group(1).strip(), match.group(2).strip()))
            continue
        match = FIRST_NUMBER.search(line)
        if match and match.start() > 0:
            out.append((line[: match.start()].strip(" :,"), line[match.start():].strip()))
        else:
            out.append((line, ""))
    return out


def _float(value: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group()) if match else None


def percent_pairs(text: str | None) -> dict[str, float]:
    return {label.lower(): v / 100 for label, value in facts(text) if "%" in value and (v := _float(value))}


def number_pairs(text: str | None) -> dict[str, float]:
    return {label.lower(): v for label, value in facts(text) if value and "%" not in value and (v := _float(value)) is not None}


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell.replace("|", "/") for cell in row) + " |" for row in rows]
    return lines


def _fmt(value: float) -> str:
    return f"≈{value:.2f}"


def working_block(ticket: dict, answers: dict[str, str | None]) -> list[str]:
    """The task-specific part of the draft."""
    item = ticket["source_item_id"]
    answer = answers.get(item)
    if item == "R2" and (margins := percent_pairs(answer)):
        ranked = sorted(margins.items(), key=lambda kv: kv[1], reverse=True)
        rows = [[f"#{n}", label.title(), f"{m * 100:g}%", _fmt(1 / m)] for n, (label, m) in enumerate(ranked, 1)]
        return [
            "Categories ranked by contribution margin. Break-even ROAS here is the margin-only floor (inverse of margin), before order costs.",
            "",
            *_table(["Rank", "Category", "Contribution margin", "Margin-only break-even ROAS"], rows),
        ]
    if item == "R3" and (stated := number_pairs(answer)):
        margins = percent_pairs(answers.get("R2"))
        rows = []
        for label, value in stated.items():
            margin = margins.get(label)
            if margin:
                floor = 1 / margin
                gap = value - floor
                flag = "above floor (order costs)" if gap >= 0 else "BELOW margin floor: check"
                rows.append([label.title(), f"{value:g}", _fmt(floor), _fmt(gap), flag])
            else:
                rows.append([label.title(), f"{value:g}", "no margin given", "", "needs R2"])
        return [
            "The client's break-even ROAS per category against the floor implied by margin alone. Stated values should sit above the floor because shipping, returns and fees come on top.",
            "",
            *_table(["Category", "Client break-even ROAS", "Margin-only floor", "Difference", "Check"], rows),
            "",
            "Target rule: never bid a category below its client break-even ROAS.",
        ]
    if item == "R5" and answer:
        rules = [label + (f" {value}" if value else "") for label, value in facts(answer)]
        return ["Exclusion rules to apply to every campaign:", "", *[f"- {rule}" for rule in rules]]
    if item in ("A1", "A3") and answer:
        ids = ACCOUNT_ID.findall(answer)
        rows = [[account, "listed by client", "to verify (read access)"] for account in ids] or [["(none parsed)", "", ""]]
        return ["Access log. Each account must be opened and checked before review.", "", *_table(["Account", "Source", "Access"], rows)]
    if item == "F1" and answer:
        rows, notes = [], []
        for line in SENTENCE.split(answer):
            line = line.strip()
            head, sep, tail = line.partition(":")
            hops = [h.strip() for h in re.split(r"\s+to\s+|->", head) if h.strip()]
            if sep and len(hops) >= 2:
                parts = [p.strip() for p in tail.split(",") if p.strip()]
                frequency = parts[-1] if len(parts) > 1 else ""
                data = ", ".join(parts[:-1]) if len(parts) > 1 else (parts[0] if parts else "")
                via = " via " + ", ".join(hops[1:-1]) if len(hops) > 2 else ""
                rows.append([hops[0], hops[-1] + via, data, frequency])
            elif line:
                notes.append(line)
        if rows:
            lines = ["Data-flow map as the client described it:", "", *_table(["Source", "Destination", "Data", "Frequency"], rows)]
            return lines + (["", "Also noted:", "", *[f"- {n}" for n in notes]] if notes else [])
    pairs = facts(answer)
    if not pairs:
        return ["No client answer yet. This ticket stays blocked until the client replies."]
    with_values = [[label, value] for label, value in pairs if value]
    lines = []
    if with_values:
        lines += ["Figures the client gave:", "", *_table(["What", "Value"], with_values), ""]
    notes = [label for label, value in pairs if not value]
    if notes:
        lines += ["Statements to use:", "", *[f"- {note}" for note in notes]]
    return lines


def draft_artifact(ticket: dict, bundle_item: dict | None, answers: dict[str, str | None], spec: dict | None) -> str:
    item = ticket["source_item_id"]
    answer = answers.get(item)
    lines = [
        f"# {ticket['title']}",
        "",
        f"{ticket['id']} · {ticket['role']} · checklist item {item} · {spec['title'] if spec else ticket['spec_id']}",
        "",
        "## Why this matters",
        "",
        str((bundle_item or {}).get("why") or "Part of the agreed scope."),
        "",
        "## What the client told us",
        "",
    ]
    if answer:
        lines += [f"> {part}" for part in str(answer).splitlines() if part.strip()]
        lines += ["", f"Answered by {ticket.get('answered_by') or 'client'} · {ticket.get('ts') or 'time not recorded'}"]
    else:
        lines += ["> No answer yet."]
    lines += ["", WORKING, "", *working_block(ticket, answers), "", "## Steps", ""]
    lines += [f"{n}. {step}" for n, step in enumerate(ROLE_STEPS.get(ticket["role"], []), 1)]
    lines += ["", "## Acceptance criteria", ""]
    lines += [f"- [ ] {c['id']}: {c['text']}" for c in ticket["acceptance_criteria"]]
    lines += ["", "_Drafted on this machine by the ACE Ops SDLC agent. Nothing here was sent anywhere._", ""]
    return "\n".join(lines)


def _numbers(text: str) -> set[float]:
    found = set()
    for raw in NUMBER.findall(text):
        try:
            found.add(round(float(raw.replace(",", "")), 4))
        except ValueError:
            continue
    return found


def checked_text(draft: str) -> str:
    """The working draft and any model summary: the parts the trace check reads."""
    keep, on = [], False
    for line in draft.splitlines():
        if line.startswith("## "):
            on = line.startswith(WORKING) or line.startswith("## Summary")
            continue
        if on and not line.startswith("|---"):
            keep.append(line)
    return "\n".join(keep)


def precheck(ticket: dict, draft: str | None, answers: dict[str, str | None]) -> list[dict]:
    """Agent results per criterion. Never approves; human criteria stay needs_human."""
    client_numbers = set()
    for text in answers.values():
        client_numbers |= _numbers(text or "")
    results = []
    for criterion in ticket["acceptance_criteria"]:
        result, note = "needs_human", "A reviewer must confirm this."
        how = criterion["verified_by"]
        if how == "client_confirmation":
            note = "Needs the client's confirmation; record it at release."
        elif how == "agent_check":
            if not ticket.get("evidence"):
                result, note = "not_met", "No evidence attached."
            elif not draft:
                result, note = "not_met", "No working draft to check."
            else:
                used = _numbers(checked_text(draft))
                missing = sorted(used - client_numbers)
                if missing:
                    shown = ", ".join(f"{n:g}" for n in missing[:6])
                    result, note = "not_met", f"{len(missing)} number(s) don't trace to any client answer: {shown}. Mark derived figures with ≈ or fix them."
                else:
                    result, note = "met", f"All {len(used)} figure(s) in the working draft trace to client answers."
        if criterion["text"].startswith("Break-even ROAS") and ticket["source_item_id"] == "R3":
            note = _breakeven_note(answers) or note
        results.append({**criterion, "result": result, "note": note})
    return results


def _breakeven_note(answers: dict[str, str | None]) -> str | None:
    stated, margins = number_pairs(answers.get("R3")), percent_pairs(answers.get("R2"))
    pairs = [(k, v, 1 / margins[k]) for k, v in stated.items() if margins.get(k)]
    if not pairs:
        return None
    below = [k for k, v, floor in pairs if v < floor]
    gaps = ", ".join(f"{k} {v:g} vs ≈{floor:.2f}" for k, v, floor in pairs)
    if below:
        return f"Client break-even is below the margin-only floor for {', '.join(below)}: these orders lose money. {gaps}."
    return f"Client values sit above the margin-only floor for every category ({gaps}); consistent with order costs (R4). Reviewer confirms."


def release_notes(release_id: str, spec: dict, tickets: list[dict], signoff: str | None, approver: str) -> dict:
    lines = [f"# {release_id} · {spec['id']} {spec['title']}", "", f"Approved by {approver}."]
    if signoff:
        lines.append(f"Client sign-off: {signoff}.")
    lines += ["", "## Shipped", ""]
    for t in tickets:
        reviewer = (t.get("review") or {}).get("reviewer") or "—"
        met = sum(c.get("result") == "met" for c in t["acceptance_criteria"])
        lines.append(f"- {t['id']} {t['title']} ({t['role']}, built by {t.get('assignee')}, reviewed by {reviewer}; {met}/{len(t['acceptance_criteria'])} agent checks met)")
    pending = [i["source_item_id"] for i in spec.get("inputs_needed_from_client", [])]
    if pending:
        lines += ["", "## Still waiting on the client", "", *[f"- {i}" for i in pending]]
    summary = (
        f"{spec['title']}: {len(tickets)} deliverable(s) are finished and reviewed: "
        + "; ".join(t["title"] for t in tickets)
        + "."
    )
    return {"notes": "\n".join(lines) + "\n", "client_summary": summary}


STAGES = ("tickets", "build", "review", "release", "done")


def build_status(client: str, client_slug: str, specs: list[dict], tickets: list[dict], now: str, today: date | None = None) -> dict:
    today = today or date.today()
    counts = {stage: sum(t["stage"] == stage for t in tickets) for stage in STAGES}
    by_role = {
        role: {
            "open": sum(t["role"] == role and t["status"] != "Done" for t in tickets),
            "blocked": sum(t["role"] == role and t["blocked_on_client"] for t in tickets),
            "done": sum(t["role"] == role and t["status"] == "Done" for t in tickets),
        }
        for role in DELIVERY_ROLES
    }
    blocked = [{"id": s["id"], "reason": "awaiting_approval", "detail": "Draft spec waiting for the project owner (G1)."} for s in specs if s["status"] == "draft"]
    for t in tickets:
        if t["stage"] == "done":
            continue
        if t["blocked_on_client"]:
            blocked.append({"id": t["id"], "reason": "blocked_on_client", "detail": "; ".join(w["reason"] for w in t.get("waiting_on", [])) or "Waiting on the client."})
        elif t.get("waiting_on"):
            blocked.append({"id": t["id"], "reason": "depends_on", "detail": "; ".join(w["reason"] for w in t["waiting_on"])})
    overdue = [t["id"] for t in tickets if t.get("due") and t["stage"] != "done" and str(t["due"])[:10] < today.isoformat()]
    gaps: dict[str, dict] = {}
    for spec in specs:
        for need in spec.get("inputs_needed_from_client", []):
            entry = gaps.setdefault(need["source_item_id"], {"source_item_id": need["source_item_id"], "question": need["question"], "blocks": []})
            entry["blocks"].append(spec["id"])
    open_gaps = list(gaps.values())
    return {
        "client": client_slug,
        "generated_at": now,
        "counts_by_stage": counts,
        "counts_by_role": by_role,
        "specs": [
            {
                "id": s["id"],
                "title": s["title"],
                "status": s["status"],
                "tickets_done": sum(t["spec_id"] == s["id"] and t["stage"] == "done" for t in tickets),
                "tickets_total": sum(t["spec_id"] == s["id"] for t in tickets),
            }
            for s in specs
        ],
        "blocked": blocked,
        "overdue": overdue,
        "open_gaps": open_gaps,
        "client_update": {"draft": client_update_text(client, specs, tickets, open_gaps), "approval": None},
        "provenance": {"generated_by": "rules", "model": None, "generated_at": now, "inputs": ["data/out/sdlc/specs.json", "data/out/sdlc/tickets.json"]},
    }


def client_update_text(client: str, specs: list[dict], tickets: list[dict], open_gaps: list[dict]) -> str:
    done = [t for t in tickets if t["stage"] == "done"]
    moving = [t for t in tickets if t["stage"] in ("build", "review", "release")]
    approved = [s for s in specs if s["status"] == "approved"]
    lines = [f"Hello {client} team,", "", "Here is where your onboarding with ACE stands."]
    lines += ["", f"Scope agreed: {len(approved)} of {len(specs)} workstreams approved" + (f" ({', '.join(s['title'] for s in approved)})." if approved else ".")]
    if done:
        lines += ["", "Finished and reviewed:", *[f"- {t['title']}" for t in done]]
    if moving:
        lines += ["", "In progress:", *[f"- {t['title']}" for t in moving]]
    if open_gaps:
        lines += ["", "What we need from you:", *[f"{n}. {g['question']} ({g['source_item_id']})" for n, g in enumerate(open_gaps, 1)]]
        lines += ["", "Your assistant can answer these directly through the ACE intake connection."]
    else:
        lines += ["", "Nothing is waiting on you right now."]
    lines += ["", "ACE Ops"]
    return "\n".join(lines)
