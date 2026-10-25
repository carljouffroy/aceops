"""Rules that turn dispatched work items into specs and tickets.

One spec per BRD section that has at least one task work item; spec ids follow
bundle.brd_sections order (SPEC-001 = first section). One ticket per task work
item. Prerequisites come from contracts/sdlc/item_dependencies.json: a task
prerequisite becomes depends_on, a gap prerequisite blocks on the client.
Client text is copied as data and never chooses ids, roles or stages.
"""

from __future__ import annotations

import re
from collections import Counter

from sdlc.config import DELIVERY_ROLES

BASE_FIELDS = (
    "title",
    "role",
    "source_item_id",
    "kind",
    "priority",
    "blocked_on_client",
    "due",
    "client_answer",
    "answered_by",
    "client_ai_name",
    "ts",
    "history",
)

# Per-section deliverable framing. Keys are bundle section codes.
SECTION_TEMPLATES: dict[str, dict] = {
    "P": {
        "goal": "Commercial terms are settled so work can start and be billed.",
        "out_of_scope": ["Renegotiating the assessment fee"],
        "criteria": [("Payment confirmation and accepted terms are both on file.", "agent_check")],
    },
    "A": {
        "goal": "ACE has working access to every ad, feed, analytics and store account it needs, verified rather than assumed.",
        "out_of_scope": ["Changing account ownership", "Creating new ad accounts"],
        "criteria": [
            ("Every account ID the client listed is recorded with its access level.", "agent_check"),
            ("Someone logged in and confirmed read access to each account.", "human_review"),
        ],
    },
    "R": {
        "goal": "A profit model per product and category, so campaign targets are set against break-even ROAS instead of revenue.",
        "out_of_scope": ["Changing live campaign budgets", "Forecasting next year's margin"],
        "criteria": [
            ("Break-even ROAS per category matches the client's stated values within 0.1, or the difference is explained.", "human_review"),
            ("No recommendation pushes a product or category the client excluded.", "human_review"),
        ],
    },
    "O": {
        "goal": "Objectives, profit targets, baseline and key dates are written into the BRD as numbers with units and periods.",
        "out_of_scope": ["Setting targets the client hasn't agreed"],
        "criteria": [
            ("The profit definition and reference period match what the client agreed.", "human_review"),
            ("The client confirms the objectives and the calendar of key dates.", "client_confirmation"),
        ],
    },
    "F": {
        "goal": "A checked map of how product, cost and conversion data move between the store, feed tool, Merchant Center and GA4, with risks flagged.",
        "out_of_scope": ["Rebuilding the feed", "Changing the store's product data"],
        "criteria": [
            ("The data-flow map lists every source -> destination -> data -> frequency the client named.", "human_review"),
            ("The conversion value definition is checked against the agreed profit definition.", "human_review"),
        ],
    },
    "D": {
        "goal": "Every export the analysis needs is loaded, checked and its limits recorded.",
        "out_of_scope": ["Cleaning the client's source systems"],
        "criteria": [("Data quality issues are listed with their impact on the analysis.", "human_review")],
    },
    "C": {
        "goal": "Competitors, personas, customer value and budget split are in the BRD so campaigns target the right buyers.",
        "out_of_scope": ["New market research beyond the client's answers"],
        "criteria": [("LTV and return rate are applied in the profit model.", "human_review")],
    },
    "ST": {
        "goal": "Stock-outs and supplier lead times set how fast campaigns can scale.",
        "out_of_scope": ["Changing the client's purchasing plan"],
        "criteria": [("Scaling limits respect supplier lead times.", "human_review")],
    },
}

TRACE_CRITERION = ("Every number in the deliverable traces to a client answer or is marked as derived.", "agent_check")
ROLE_CRITERIA = {
    "Marketing Specialist": ("Recommendations respect the client's exclusions and break-even ROAS, with no claim the client hasn't confirmed.", "human_review"),
    "Data Analyst": ("Totals reconcile with the client's own source within 1%, or the gap is explained.", "human_review"),
    "Developer": ("Findings name the account, property or feed checked; any code change lives in a sandbox branch with a test.", "human_review"),
}
# Specs whose work touches the ad account, feed or store need the client's sign-off at release.
SIGNOFF_ROLES = {"Marketing Specialist", "Developer"}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "client"


def spec_id_for(section: str, bundle: dict) -> str:
    order = list(bundle.get("brd_sections", {}))
    index = order.index(section) + 1 if section in order else len(order) + 1
    return f"SPEC-{index:03d}"


def items_by_id(bundle: dict) -> dict[str, dict]:
    return {str(item["id"]): item for item in bundle.get("items", [])}


def work_by_item(work_items: list[dict]) -> dict[str, dict]:
    return {str(row.get("source_item_id")): row for row in work_items if row.get("source_item_id")}


def section_of(item_id: str, bundle_items: dict[str, dict]) -> str | None:
    item = bundle_items.get(item_id)
    return str(item.get("section")) if item else None


def lead_role(rows: list[dict]) -> str:
    counts = Counter(row.get("role") for row in rows if row.get("role") in DELIVERY_ROLES)
    if not counts:
        return DELIVERY_ROLES[0]
    best = max(counts.values())
    return next(role for role in DELIVERY_ROLES if counts.get(role) == best)


def criteria_for(section: str, roles: list[str]) -> list[dict]:
    template = SECTION_TEMPLATES.get(section, {})
    rows = [TRACE_CRITERION, *template.get("criteria", [])]
    for role in DELIVERY_ROLES:
        if role in roles:
            rows.append(ROLE_CRITERIA[role])
    return [{"id": f"AC{n}", "text": text, "verified_by": how} for n, (text, how) in enumerate(rows, 1)]


def derive_specs(bundle: dict, work_items: list[dict], deps: dict[str, list[str]], client: str, now: str) -> list[dict]:
    """Fresh draft specs, one per section with at least one task work item."""
    bundle_items = items_by_id(bundle)
    by_item = work_by_item(work_items)
    sections = bundle.get("brd_sections", {})
    specs = []
    for section, title in sections.items():
        rows = [by_item[i] for i in bundle_items if section_of(i, bundle_items) == section and i in by_item]
        tasks = [row for row in rows if row.get("kind") == "task"]
        if not tasks:
            continue
        roles = sorted({row["role"] for row in tasks}, key=DELIVERY_ROLES.index)
        gap_ids = [row["source_item_id"] for row in rows if row.get("kind") == "gap"]
        prereq_gaps, prereq_specs = [], []
        for row in rows:
            for prereq in deps.get(row["source_item_id"], []):
                other = by_item.get(prereq)
                if other is None:
                    continue
                if other.get("kind") == "gap":
                    prereq_gaps.append(prereq)
                other_section = section_of(prereq, bundle_items)
                if other_section and other_section != section:
                    prereq_specs.append(spec_id_for(other_section, bundle))
        needed = list(dict.fromkeys([*prereq_gaps, *gap_ids]))
        template = SECTION_TEMPLATES.get(section, {})
        risks = []
        if needed:
            risks.append(f"Waits on {len(needed)} client answer(s): {', '.join(needed)}.")
        if any(row.get("priority") for row in rows):
            risks.append("Includes priority checklist items; slips here delay every later section.")
        specs.append(
            {
                "id": spec_id_for(section, bundle),
                "version": 1,
                "client": slug(client),
                "title": str(title),
                "role": lead_role(tasks),
                "stage": "spec",
                "status": "draft",
                "brd_sections": [section],
                "goal": template.get("goal", f"Deliver the {title.lower()} work agreed in the BRD."),
                "scope": [row["title"] for row in tasks],
                "out_of_scope": list(template.get("out_of_scope", [])),
                "acceptance_criteria": criteria_for(section, roles),
                "inputs_needed_from_client": [
                    {"source_item_id": i, "question": str(bundle_items.get(i, {}).get("text") or i)} for i in needed
                ],
                "source_item_ids": [row["source_item_id"] for row in rows],
                "source_work_item_ids": [row["id"] for row in rows],
                "depends_on": sorted(set(prereq_specs)),
                "risks": risks,
                "client_signoff_required": bool(SIGNOFF_ROLES & set(roles)),
                "approval": None,
                "rejection": None,
                "provenance": {
                    "generated_by": "rules",
                    "model": None,
                    "generated_at": now,
                    "inputs": ["data/out/brd.md", "data/out/work_items.json", "contracts/bundle.json", "contracts/sdlc/item_dependencies.json"],
                },
            }
        )
    return specs


def ticket_criteria(spec: dict, role: str) -> list[dict]:
    """Shared criteria plus the one for this ticket's role."""
    own = ROLE_CRITERIA.get(role, (None,))[0]
    others = {text for r, (text, _) in ROLE_CRITERIA.items() if r != role}
    return [
        {**criterion, "result": None, "note": None}
        for criterion in spec["acceptance_criteria"]
        if criterion["text"] not in others or criterion["text"] == own
    ]


def split_spec(spec: dict, bundle: dict, work_items: list[dict], now: str, start: int = 1, only_items: set[str] | None = None) -> list[dict]:
    """Tickets for an approved spec, one per task work item in its section."""
    bundle_items = items_by_id(bundle)
    by_item = work_by_item(work_items)
    tickets = []
    number = start
    for item_id in spec["source_item_ids"]:
        row = by_item.get(item_id)
        if row is None or row.get("kind") != "task":
            continue
        if only_items is not None and item_id not in only_items:
            continue
        ticket = {"id": f"{spec['id']}-T{number:02d}"}
        ticket.update({field: row.get(field) for field in BASE_FIELDS})
        ticket["title"] = ticket["title"] or str(bundle_items.get(item_id, {}).get("task_if_answered") or item_id)
        ticket["history"] = list(row.get("history") or [])
        ticket.update(
            {
                "status": "To do",
                "spec_id": spec["id"],
                "spec_version": spec["version"],
                "source_work_item_id": row["id"],
                "stage": "tickets",
                "assignee": None,
                "acceptance_criteria": ticket_criteria(spec, row["role"]),
                "depends_on": [],
                "waiting_on": [],
                "evidence": [],
                "agent_draft": None,
                "review": None,
                "release": None,
                "provenance": {
                    "generated_by": "rules",
                    "model": None,
                    "generated_at": now,
                    "inputs": ["data/out/sdlc/specs.json", "contracts/sdlc/item_dependencies.json"],
                },
            }
        )
        tickets.append(ticket)
        number += 1
    return tickets


def resolve_waits(ticket: dict, tickets: list[dict], specs: list[dict], work_items: list[dict], deps: dict[str, list[str]], bundle: dict) -> None:
    """Fill depends_on, waiting_on and blocked_on_client from prerequisites."""
    by_item = work_by_item(work_items)
    by_source = {t["source_item_id"]: t for t in tickets}
    spec_status = {s["id"]: s["status"] for s in specs}
    bundle_items = items_by_id(bundle)
    depends_on, waiting = [], []
    blocked = bool(by_item.get(ticket["source_item_id"], {}).get("blocked_on_client"))
    for prereq in deps.get(ticket["source_item_id"], []):
        row = by_item.get(prereq)
        if row is None:
            continue
        if row.get("kind") == "gap":
            blocked = True
            waiting.append({"item": prereq, "reason": f"Client hasn't answered {prereq} yet"})
            continue
        other = by_source.get(prereq)
        if other is None:
            section = section_of(prereq, bundle_items)
            other_spec = spec_id_for(section, bundle) if section else "?"
            state = spec_status.get(other_spec, "not drafted")
            waiting.append({"item": prereq, "reason": f"{other_spec} is {state}; its {prereq} ticket doesn't exist yet"})
            continue
        depends_on.append(other["id"])
        if (other.get("review") or {}).get("decision") != "approved":
            waiting.append({"item": prereq, "reason": f"{other['id']} hasn't passed review"})
    ticket["depends_on"] = sorted(set(depends_on))
    ticket["waiting_on"] = waiting
    ticket["blocked_on_client"] = blocked
