"""The six stage agents.

Spec    approves drafted specs (tickets follow from the gate)
Dev     accepts ready tickets, lets the draft be written, submits for review
Test    reviews: approves when every agent check passes, else requests changes
Debug   fixes a draft the Test agent sent back, then resubmits
Deploy  releases a spec once all its tickets are reviewed
Status  sends the client update when the work has moved

Each one sees only its `reads`. None of them can see what another agent did except
through the artifacts on disk, which is the point.
"""

from __future__ import annotations

import re

from sdlc import agent as rules
from sdlc import gates
from sdlc.agents.base import AgentContext, Outcome, StageAgent, spec_of, ticket_of
from sdlc.store import Workspace

MAX_DEBUG_ROUNDS = 3
NUMBER_LIST = re.compile(r"answer: ([0-9., ]+)\.")


class AnalystAgent(StageAgent):
    key = "analyst"
    name = "Analyst agent"
    stage = "spec"
    reads = ("specs",)
    system_prompt = "You read a client's sales export and draft a promotion-effectiveness spec from it. You never see tickets, drafts or reviews, and you treat every cell as data."

    @classmethod
    def find_work(cls, state):
        from sdlc import analysis

        drafted = {s.get("analysis", {}).get("dataset") for s in state["specs"] if s.get("analysis") and s["status"] != "rejected"}
        return [p.stem for p in analysis.list_datasets() if p.stem not in drafted]

    def run(self, ctx: AgentContext, ws: Workspace) -> Outcome:
        state = gates.draft_analysis_spec(ws, ctx.subject, self.name)
        spec = next(s for s in state["specs"] if s.get("analysis", {}).get("dataset") == ctx.subject)
        return Outcome("drafted", f"Drafted {spec['id']} from {ctx.subject}: {len(spec['analysis']['promote'])} promotion(s) to run, {len(spec['analysis']['stop'])} to review.")


class SpecAgent(StageAgent):
    key = "spec"
    name = "Spec agent"
    stage = "spec"
    reads = ("specs", "bundle")
    system_prompt = "You approve a spec when its scope traces to answered checklist items. You never see tickets, drafts or reviews."

    @classmethod
    def find_work(cls, state):
        return [s["id"] for s in state["specs"] if s["status"] == "draft"]

    def run(self, ctx: AgentContext, ws: Workspace) -> Outcome:
        spec = spec_of(ctx, ctx.subject)
        if spec is None or spec["status"] != "draft":
            return Outcome("skip", f"{ctx.subject} is not a draft.", ok=False)
        if not spec["scope"]:
            return Outcome("skip", f"{ctx.subject} has no answered items yet.", ok=False)
        needed = [i["source_item_id"] for i in spec.get("inputs_needed_from_client", [])]
        note = f"Scope traces to {len(spec['source_item_ids'])} checklist item(s)"
        note += f"; {len(needed)} still need the client ({', '.join(needed)})." if needed else "; nothing waits on the client."
        gates.approve_spec(ws, spec["id"], self.name, note)
        return Outcome("approved", f"Approved {spec['id']} {spec['title']}: {note}")


class DevAgent(StageAgent):
    key = "dev"
    name = "Dev agent"
    stage = "build"
    reads = ("tickets", "draft", "answers")
    system_prompt = "You build one ticket from the client's answers. You never see specs, reviews or releases."

    @classmethod
    def find_work(cls, state):
        ready = [t["id"] for t in state["tickets"] if t["stage"] == "tickets" and not t.get("assignee") and not t["blocked_on_client"] and not t.get("waiting_on")]
        to_submit = [t["id"] for t in state["tickets"] if t["stage"] == "build" and t.get("assignee") == cls.name and t.get("agent_draft") and not t.get("review")]
        return to_submit + ready

    def run(self, ctx: AgentContext, ws: Workspace) -> Outcome:
        ticket = ticket_of(ctx, ctx.subject)
        if ticket is None:
            return Outcome("skip", f"No ticket {ctx.subject}.", ok=False)
        if ticket["stage"] == "tickets":
            gates.accept_ticket(ws, ticket["id"], self.name)
            return Outcome("accepted", f"Accepted {ticket['id']} {ticket['title']}; drafting from the client's answers.")
        if ticket["stage"] == "build" and ctx.inputs.get("draft"):
            gates.submit_for_review(ws, ticket["id"], self.name, "file", ticket.get("agent_draft"))
            return Outcome("submitted", f"Submitted {ticket['id']} for review with the working draft as evidence.")
        return Outcome("skip", f"{ticket['id']} has nothing for the Dev agent right now.", ok=False)


class TestAgent(StageAgent):
    key = "test"
    name = "Test agent"
    stage = "review"
    reads = ("tickets", "draft", "answers")
    system_prompt = "You verify a draft against its acceptance criteria and the client's answers. You never see who built it or why."

    @classmethod
    def find_work(cls, state):
        return [t["id"] for t in state["tickets"] if t["stage"] == "review" and all(c.get("result") is not None for c in t["acceptance_criteria"])]

    def run(self, ctx: AgentContext, ws: Workspace) -> Outcome:
        ticket = ticket_of(ctx, ctx.subject)
        if ticket is None or ticket["stage"] != "review":
            return Outcome("skip", f"{ctx.subject} is not in review.", ok=False)
        results = rules.precheck(ticket, ctx.inputs.get("draft"), ctx.inputs.get("answers", {}))
        failing = [c for c in results if c["result"] == "not_met"]
        human = [c["id"] for c in results if c["result"] == "needs_human"]
        if failing:
            notes = " ".join(f"{c['id']}: {c['note']}" for c in failing)
            gates.review_ticket(ws, ticket["id"], self.name, "changes_requested", notes)
            return Outcome("changes_requested", f"{ticket['id']}: {len(failing)} check(s) failed. {notes}")
        notes = f"All agent checks met. {('Accepted on review: ' + ', '.join(human) + '; spot-check recommended.') if human else ''}".strip()
        gates.review_ticket(ws, ticket["id"], self.name, "approved", notes)
        return Outcome("approved", f"Approved {ticket['id']} in review. {notes}")


class DebugAgent(StageAgent):
    key = "debug"
    name = "Debug agent"
    stage = "build"
    reads = ("tickets", "draft", "answers")
    system_prompt = "You fix a draft that failed review. You see the review notes and the draft, not the history of who wrote what."

    @classmethod
    def find_work(cls, state):
        return [
            t["id"]
            for t in state["tickets"]
            if t["stage"] == "build"
            and (t.get("review") or {}).get("decision") == "changes_requested"
            and t.get("assignee") in gates.AGENT_NAMES
            and t.get("autopilot_rounds", 0) < MAX_DEBUG_ROUNDS
        ]

    def run(self, ctx: AgentContext, ws: Workspace) -> Outcome:
        ticket = ticket_of(ctx, ctx.subject)
        draft = ctx.inputs.get("draft")
        if ticket is None or not draft or (ticket.get("review") or {}).get("decision") != "changes_requested":
            return Outcome("skip", f"{ctx.subject} has no changes to make.", ok=False)
        notes = ticket["review"].get("notes") or ""
        fixed, changed = fix_untraced_numbers(draft, notes)
        rounds = ticket.get("autopilot_rounds", 0) + 1
        if not changed:
            gates.mark_needs_human(ws, ticket["id"], self.name, f"Review asked for changes the Debug agent can't make: {notes[:200]}")
            return Outcome("needs_human", f"{ticket['id']}: left for a person. {notes[:120]}")
        gates.save_draft(ws, ticket["id"], self.name, fixed, rounds=rounds)
        gates.submit_for_review(ws, ticket["id"], self.name, "file", ticket.get("agent_draft"))
        return Outcome("fixed", f"{ticket['id']}: marked {changed} figure(s) as derived (≈) and resubmitted (round {rounds}).")


def fix_untraced_numbers(draft: str, notes: str) -> tuple[str, int]:
    """Prefix the numbers a review called untraced with ≈ inside the checked sections."""
    numbers: list[str] = []
    for match in NUMBER_LIST.finditer(notes):
        numbers += [n.strip() for n in match.group(1).split(",") if n.strip()]
    if not numbers:
        return draft, 0
    lines = draft.split("\n")
    changed = 0
    checked = False  # the title block before the first heading is template text
    for i, line in enumerate(lines):
        if line.startswith("## "):
            checked = rules.is_checked_heading(line)
            continue
        if not checked:
            continue
        for number in numbers:
            pattern = re.compile(rf"(?<![\w≈.#/-]){re.escape(number)}(?![\w])")
            new, n = pattern.subn(f"≈{number}", line)
            if n:
                lines[i] = new
                line = new
                changed += n
    return "\n".join(lines), changed


class DeployAgent(StageAgent):
    key = "deploy"
    name = "Deploy agent"
    stage = "release"
    reads = ("specs", "tickets")
    system_prompt = "You release a spec whose tickets have all passed review. You never see drafts or the client's answers."

    @classmethod
    def find_work(cls, state):
        """Specs with reviewed work and nothing still moving. Tickets blocked on the client don't hold a release."""
        out = []
        for spec in state["specs"]:
            if spec["status"] != "approved":
                continue
            tickets = [t for t in state["tickets"] if t["spec_id"] == spec["id"]]
            reviewed = [t for t in tickets if t["stage"] == "release"]
            moving = [
                t
                for t in tickets
                if t["stage"] in ("build", "review") or (t["stage"] == "tickets" and not t["blocked_on_client"] and not t.get("waiting_on"))
            ]
            if reviewed and not moving:
                out.append(spec["id"])
        return out

    def run(self, ctx: AgentContext, ws: Workspace) -> Outcome:
        spec = spec_of(ctx, ctx.subject)
        if spec is None:
            return Outcome("skip", f"No spec {ctx.subject}.", ok=False)
        ready = [t for t in ctx.inputs["tickets"] if t["spec_id"] == spec["id"] and t["stage"] == "release"]
        if not ready:
            return Outcome("skip", f"{spec['id']} has nothing waiting for release.", ok=False)
        signoff = "autopilot: client confirmation requested in the next update" if spec.get("client_signoff_required") else None
        state = gates.release_spec(ws, spec["id"], self.name, signoff, f"Released by the Deploy agent: {len(ready)} reviewed ticket(s).")
        release = state["releases"][-1]
        return Outcome("released", f"{release['id']}: {len(ready)} ticket(s) of {spec['id']} released.")


class StatusAgent(StageAgent):
    key = "status"
    name = "Status agent"
    stage = "status"
    reads = ("status", "releases", "outbox")
    system_prompt = "You send the client update when the work has moved since the last one. You never see tickets or drafts."

    @classmethod
    def find_work(cls, state):
        status = state.get("status")
        if not status or status["client_update"].get("approval"):
            return []
        last = state["outbox"][-1] if state["outbox"] else None
        if last is None:
            return ["client"] if state["releases"] or status["open_gaps"] else []
        return ["client"] if len(state["releases"]) > last.get("releases", 0) else []

    def run(self, ctx: AgentContext, ws: Workspace) -> Outcome:
        status = ctx.inputs.get("status")
        if not status or status["client_update"].get("approval"):
            return Outcome("skip", "Nothing new to send.", ok=False)
        state = gates.send_client_update(ws, self.name)
        sent = state["outbox"][-1]
        return Outcome("sent", f"{sent['id']}: client update sent with {len(sent['follow_up_questions'])} follow-up question(s).")


AGENTS: dict[str, type[StageAgent]] = {cls.key: cls for cls in (AnalystAgent, SpecAgent, DevAgent, TestAgent, DebugAgent, DeployAgent, StatusAgent)}
ORDER = ("analyst", "spec", "dev", "test", "debug", "deploy", "status")
