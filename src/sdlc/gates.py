"""The five human gates, plus build-stage edits. The agent has no path to these.

G1 approve or reject a spec (project owner)
G2 accept a ticket (someone in the ticket's role)
    build: edit the draft and submit evidence (the assignee)
G3 review (same role, not the builder)
G4 release (project owner; client sign-off when the spec touches client systems)
G5 send the client update (project owner)

Each function checks who is acting, changes state, then runs the agent sync so
its follow-on work (tickets, drafts, pre-checks, status) happens at once.
"""

from __future__ import annotations

from sdlc import agent, engine
from sdlc.config import DEFAULT_TEAM, OWNER_ROLE
from sdlc.store import Workspace, emit, now_iso

EVIDENCE_KINDS = ("link", "file", "pr", "note")


class GateError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def person(name: str, team=DEFAULT_TEAM) -> dict:
    for member in team:
        if member["name"] == name:
            return member
    raise GateError(403, f"{name or 'Someone'} isn't on the team.")


def _owner(name: str) -> dict:
    actor = person(name)
    if actor["role"] != OWNER_ROLE:
        raise GateError(403, f"Only the project owner can do this. {actor['name']} is a {actor['role']}.")
    return actor


def _spec(state: dict, spec_id: str) -> dict:
    spec = next((s for s in state["specs"] if s["id"] == spec_id), None)
    if spec is None:
        raise GateError(404, f"No spec {spec_id}.")
    return spec


def _ticket(state: dict, ticket_id: str) -> dict:
    ticket = next((t for t in state["tickets"] if t["id"] == ticket_id), None)
    if ticket is None:
        raise GateError(404, f"No ticket {ticket_id}.")
    return ticket


def _finish(ws: Workspace, state: dict) -> dict:
    ws.save(state)
    return engine.sync(ws)


def approve_spec(ws: Workspace, spec_id: str, actor: str, note: str | None = None) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = _owner(actor)
        spec = _spec(state, spec_id)
        if spec["status"] != "draft":
            raise GateError(409, f"{spec_id} is {spec['status']}, not a draft.")
        spec["status"] = "approved"
        spec["approval"] = {"by": who["name"], "at": now_iso(), "note": (note or "").strip() or None}
        emit(state, who["name"], "spec_approved", spec_id, f"Approved {spec_id} {spec['title']} (G1).")
        return _finish(ws, state)


def reject_spec(ws: Workspace, spec_id: str, actor: str, reason: str) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = _owner(actor)
        spec = _spec(state, spec_id)
        if spec["status"] != "draft":
            raise GateError(409, f"{spec_id} is {spec['status']}, not a draft.")
        reason = (reason or "").strip()
        if not reason:
            raise GateError(422, "Say why you're rejecting it, so the agent can revise the spec.")
        spec["status"] = "rejected"
        spec["rejection"] = {"by": who["name"], "at": now_iso(), "reason": reason}
        emit(state, who["name"], "spec_rejected", spec_id, f"Rejected {spec_id}: {reason}")
        return _finish(ws, state)


def accept_ticket(ws: Workspace, ticket_id: str, actor: str) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = person(actor)
        ticket = _ticket(state, ticket_id)
        if who["role"] != ticket["role"]:
            raise GateError(403, f"{ticket_id} is {ticket['role']} work. {who['name']} is a {who['role']}.")
        if ticket["stage"] != "tickets" or ticket.get("assignee"):
            raise GateError(409, f"{ticket_id} is already accepted by {ticket.get('assignee')}.")
        ticket["assignee"] = who["name"]
        emit(state, who["name"], "ticket_accepted", ticket_id, f"Accepted {ticket_id} {ticket['title']} (G2).")
        return _finish(ws, state)


def save_draft(ws: Workspace, ticket_id: str, actor: str, text: str) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = person(actor)
        ticket = _ticket(state, ticket_id)
        if ticket["stage"] != "build":
            raise GateError(409, f"{ticket_id} is in {ticket['stage']}; drafts can only change in build.")
        if who["name"] != ticket.get("assignee"):
            raise GateError(403, f"Only {ticket.get('assignee')} can edit this draft.")
        if not text.strip():
            raise GateError(422, "The draft can't be empty.")
        ws.write_draft(ticket_id, text if text.endswith("\n") else text + "\n")
        ticket["provenance"] = {**ticket["provenance"], "generated_by": "human", "model": None, "generated_at": now_iso()}
        emit(state, who["name"], "draft_edited", ticket_id, f"Edited the {ticket_id} draft.")
        return _finish(ws, state)


def submit_for_review(ws: Workspace, ticket_id: str, actor: str, kind: str = "file", ref: str | None = None) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = person(actor)
        ticket = _ticket(state, ticket_id)
        if ticket["stage"] != "build":
            raise GateError(409, f"{ticket_id} is in {ticket['stage']}, not build.")
        if who["name"] != ticket.get("assignee"):
            raise GateError(403, f"Only {ticket.get('assignee')} can submit {ticket_id}.")
        if kind not in EVIDENCE_KINDS:
            raise GateError(422, f"Evidence kind must be one of {', '.join(EVIDENCE_KINDS)}.")
        ref = (ref or "").strip() or ticket.get("agent_draft") or ""
        if not ref:
            raise GateError(422, "Attach evidence: a link, file, PR or note.")
        ticket["evidence"].append({"kind": kind, "ref": ref, "added_by": who["name"], "at": now_iso()})
        ticket["stage"] = "review"
        ticket["review"] = None
        ticket["acceptance_criteria"] = [{**c, "result": None, "note": None} for c in ticket["acceptance_criteria"]]
        emit(state, who["name"], "submitted", ticket_id, f"Submitted {ticket_id} for review with {kind} evidence.")
        return _finish(ws, state)


def review_ticket(ws: Workspace, ticket_id: str, actor: str, decision: str, notes: str | None = None) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = person(actor)
        ticket = _ticket(state, ticket_id)
        if ticket["stage"] != "review":
            raise GateError(409, f"{ticket_id} is in {ticket['stage']}, not review.")
        if who["name"] == ticket.get("assignee"):
            raise GateError(409, "The reviewer must differ from the builder.")
        if who["role"] != ticket["role"]:
            raise GateError(403, f"A {ticket['role']} reviews {ticket_id}. {who['name']} is a {who['role']}.")
        if decision not in ("approved", "changes_requested"):
            raise GateError(422, "Decision is approved or changes_requested.")
        notes = (notes or "").strip() or None
        if decision == "changes_requested" and not notes:
            raise GateError(422, "Say what needs to change.")
        if decision == "approved" and any(c.get("result") == "not_met" for c in ticket["acceptance_criteria"]):
            raise GateError(409, "The agent pre-check found unmet criteria. Request changes, or have the builder fix the draft.")
        ticket["review"] = {"reviewer": who["name"], "decision": decision, "notes": notes, "at": now_iso()}
        if decision == "approved":
            ticket["stage"] = "release"
            emit(state, who["name"], "review_approved", ticket_id, f"Approved {ticket_id} in review (G3).")
        else:
            ticket["stage"] = "build"
            ticket["acceptance_criteria"] = [{**c, "result": None, "note": None} for c in ticket["acceptance_criteria"]]
            emit(state, who["name"], "changes_requested", ticket_id, f"Requested changes on {ticket_id}: {notes}")
        return _finish(ws, state)


def release_spec(ws: Workspace, spec_id: str, actor: str, client_signoff: str | None = None, notes: str | None = None) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = _owner(actor)
        spec = _spec(state, spec_id)
        ready = [t for t in state["tickets"] if t["spec_id"] == spec_id and t["stage"] == "release"]
        if not ready:
            raise GateError(409, f"No reviewed tickets of {spec_id} are waiting for release.")
        signoff = (client_signoff or "").strip() or None
        if spec.get("client_signoff_required") and not signoff:
            raise GateError(422, f"{spec_id} touches the client's ad account, feed or store. Record who signed off at the client.")
        release_id = f"REL-{len(state['releases']) + 1:03d}"
        at = now_iso()
        drafted = agent.release_notes(release_id, spec, ready, signoff, who["name"])
        for t in ready:
            t["stage"] = "done"
            t["status"] = "Done"
            t["release"] = {"release_id": release_id, "approved_by": who["name"], "client_signoff": signoff, "notes": (notes or "").strip() or None, "at": at}
        state["releases"].append(
            {
                "id": release_id,
                "spec_id": spec_id,
                "title": spec["title"],
                "tickets": [t["id"] for t in ready],
                "approved_by": who["name"],
                "client_signoff": signoff,
                "at": at,
                "notes": drafted["notes"] + (f"\n{notes.strip()}\n" if notes and notes.strip() else ""),
                "client_summary": drafted["client_summary"],
            }
        )
        emit(state, who["name"], "released", release_id, f"Released {release_id}: {len(ready)} ticket(s) of {spec_id} (G4).")
        return _finish(ws, state)


def edit_client_update(ws: Workspace, actor: str, text: str) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = _owner(actor)
        if not text.strip():
            raise GateError(422, "The update can't be empty.")
        state["client_update_override"] = text.strip()
        emit(state, who["name"], "update_edited", "status", "Edited the client update draft.")
        return _finish(ws, state)


def send_client_update(ws: Workspace, actor: str) -> dict:
    with ws.lock:
        state = engine.sync(ws)
        who = _owner(actor)
        status = state.get("status")
        if not status:
            raise GateError(409, "There's no status report yet.")
        if status["client_update"].get("approval"):
            raise GateError(409, "This update was already sent. It changes when the work does.")
        text = status["client_update"]["draft"]
        at = now_iso()
        state["outbox"].append(
            {
                "id": f"MSG-{len(state['outbox']) + 1:03d}",
                "at": at,
                "by": who["name"],
                "text": text,
                "follow_up_questions": [{"source_item_id": g["source_item_id"], "question": g["question"]} for g in status["open_gaps"]],
                "channel": "client outbox (local)",
                "rules_text": state.get("rules_update"),
            }
        )
        state.pop("client_update_override", None)
        emit(state, who["name"], "update_sent", "status", f"Sent the client update with {len(status['open_gaps'])} follow-up question(s) (G5).")
        return _finish(ws, state)
