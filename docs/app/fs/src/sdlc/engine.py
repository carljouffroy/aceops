"""The agent's sync: read the pipeline, update specs and tickets, move work that is ready.

sync() is safe to run every few seconds and after every human action. It never
approves anything: approvals only come from gates.py. Model calls happen in a
background thread so a slow model never blocks people using the console.
"""

from __future__ import annotations

import copy
import json
import threading
from datetime import date

from sdlc import agent, derive
from sdlc.config import LocalOnlyError, model_settings
from sdlc.llm import summarize
from sdlc.store import Workspace, emit, now_iso

AGENT = "SDLC agent"
STAGE_STATUS = {"tickets": "To do", "build": "In progress", "review": "In progress", "release": "In progress", "done": "Done"}
LAST_SYNC: dict[str, str] = {}
_POLISHING: set[str] = set()


def _strip(value, keys=("generated_at",)):
    if isinstance(value, dict):
        return {k: _strip(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [_strip(v, keys) for v in value]
    return value


def _same(a, b) -> bool:
    return json.dumps(_strip(a), sort_keys=True) == json.dumps(_strip(b), sort_keys=True)


def answers_by_item(work_items: list[dict]) -> dict[str, str | None]:
    return {str(row.get("source_item_id")): row.get("client_answer") for row in work_items}


def agent_info() -> dict:
    try:
        settings = model_settings()
    except LocalOnlyError as exc:
        return {"mode": "rules", "model": None, "error": str(exc), "base_url": None}
    if settings is None:
        return {"mode": "rules", "model": None, "error": None, "base_url": None}
    return {"mode": "local_llm", "model": settings.model, "error": None, "base_url": settings.base_url}


def sync(ws: Workspace, *, today: date | None = None) -> dict:
    with ws.lock:
        state = ws.load()
        before = copy.deepcopy(state)
        bundle, work, deps = ws.bundle(), ws.work_items(), ws.dependencies()
        client = ws.client_name()
        now = now_iso()
        answers = answers_by_item(work)

        _merge_specs(state, derive.derive_specs(bundle, work, deps, client, now))
        _split_approved(state, bundle, work, now)
        _refresh_tickets(state, work, deps, bundle)
        _advance(ws, state, bundle, answers)
        _rebuild_status(state, client, now, today)
        state["agent"] = agent_info()

        LAST_SYNC[str(ws.state_dir)] = now
        if not _same(_cmp(state), _cmp(before)):
            ws.save(state)
        polish = [
            t["id"]
            for t in state["tickets"]
            if t["stage"] == "build"
            and t.get("agent_draft")
            and t["provenance"]["generated_by"] == "rules"
            and "model:unavailable" not in t["provenance"].get("inputs", [])
        ]
    if polish and state["agent"]["mode"] == "local_llm":
        for ticket_id in polish:
            _polish_later(ws, ticket_id)
    return state


def _cmp(state: dict) -> dict:
    return {k: v for k, v in state.items() if k not in ("version", "last_sync")}


def _merge_specs(state: dict, fresh: list[dict]) -> None:
    specs = {s["id"]: s for s in state["specs"]}
    for new in fresh:
        old = specs.get(new["id"])
        if old is None:
            specs[new["id"]] = new
            emit(state, AGENT, "spec_drafted", new["id"], f"Drafted {new['id']} {new['title']} from {len(new['scope'])} task(s).")
        elif old["status"] == "draft":
            merged = {**new, "version": old["version"], "risks": _keep_history(old, new)}
            if not _same(_content(merged), _content(old)):
                specs[new["id"]] = merged
                emit(state, AGENT, "spec_updated", new["id"], f"Updated draft {new['id']} after new client answers.")
        elif old["status"] == "rejected":
            reason = (old.get("rejection") or {}).get("reason", "")
            by = (old.get("rejection") or {}).get("by", "")
            history = [*_keep_history(old, new), f"v{old['version']} rejected by {by}: {reason}"]
            specs[new["id"]] = {**new, "version": old["version"] + 1, "risks": history, "rejection": old.get("rejection")}
            emit(state, AGENT, "spec_revised", new["id"], f"Re-drafted {new['id']} as v{old['version'] + 1} after rejection: {reason}")
        elif old["status"] == "approved":
            answered = {i["source_item_id"] for i in old.get("inputs_needed_from_client", [])} - {
                i["source_item_id"] for i in new.get("inputs_needed_from_client", [])
            }
            if answered:
                old["inputs_needed_from_client"] = [i for i in old["inputs_needed_from_client"] if i["source_item_id"] not in answered]
                emit(state, AGENT, "client_answered", old["id"], f"Client answered {', '.join(sorted(answered))} for approved {old['id']}.")
    state["specs"] = sorted(specs.values(), key=lambda s: s["id"])


def _content(spec: dict) -> dict:
    return {k: spec.get(k) for k in ("scope", "inputs_needed_from_client", "source_item_ids", "acceptance_criteria", "depends_on", "role")}


def _keep_history(old: dict, new: dict) -> list[str]:
    rejected = [r for r in old.get("risks", []) if " rejected by " in r]
    return [*new.get("risks", []), *[r for r in rejected if r not in new.get("risks", [])]]


def _split_approved(state: dict, bundle: dict, work: list[dict], now: str) -> None:
    from sdlc import analysis  # data-driven specs; imported here to keep engine importable on its own

    for spec in state["specs"]:
        if spec["status"] != "approved":
            continue
        have = [t for t in state["tickets"] if t["spec_id"] == spec["id"]]
        if spec.get("analysis"):
            if not have:
                new = analysis.split_spec(spec, now)
                state["tickets"].extend(new)
                if new:
                    emit(state, AGENT, "spec_split", spec["id"], f"Split {spec['id']} into {len(new)} ticket(s) from the client's data: {', '.join(t['id'] for t in new)}.")
            continue
        if not have:
            new = derive.split_spec(spec, bundle, work, now)
            state["tickets"].extend(new)
            if new:
                emit(state, AGENT, "spec_split", spec["id"], f"Split {spec['id']} into {len(new)} ticket(s): {', '.join(t['id'] for t in new)}.")
            continue
        covered = {t["source_item_id"] for t in have}
        by_item = derive.work_by_item(work)
        later = {i for i in spec["source_item_ids"] if i not in covered and by_item.get(i, {}).get("kind") == "task"}
        if later:
            new = derive.split_spec(spec, bundle, work, now, start=len(have) + 1, only_items=later)
            state["tickets"].extend(new)
            emit(state, AGENT, "tickets_added", spec["id"], f"Client answered {', '.join(sorted(later))}; added {', '.join(t['id'] for t in new)}.")


def _refresh_tickets(state: dict, work: list[dict], deps: dict, bundle: dict) -> None:
    by_item = derive.work_by_item(work)
    for t in state["tickets"]:
        row = by_item.get(t["source_item_id"])
        if row and t["stage"] != "done" and row.get("client_answer") != t.get("client_answer"):
            for field in ("client_answer", "answered_by", "client_ai_name", "ts", "history"):
                t[field] = row.get(field) if field != "history" else list(row.get("history") or [])
            if t["stage"] == "review":
                t["acceptance_criteria"] = [{**c, "result": None, "note": None} for c in t["acceptance_criteria"]]
                emit(state, AGENT, "answer_changed", t["id"], f"Client changed their answer to {t['source_item_id']}; re-checking {t['id']} against the new text.")
            elif t["stage"] == "release":
                t["stage"] = "review"
                t["review"] = None
                t["acceptance_criteria"] = [{**c, "result": None, "note": None} for c in t["acceptance_criteria"]]
                emit(state, AGENT, "answer_changed", t["id"], f"Client changed their answer to {t['source_item_id']} after review; {t['id']} is back in review.")
            else:
                emit(state, AGENT, "answer_changed", t["id"], f"Client changed their answer to {t['source_item_id']}; {t['id']} now uses the new text.")
        derive.resolve_waits(t, state["tickets"], state["specs"], work, deps, bundle)


def _advance(ws: Workspace, state: dict, bundle: dict, answers: dict) -> None:
    items = derive.items_by_id(bundle)
    specs = {s["id"]: s for s in state["specs"]}
    for t in state["tickets"]:
        ready = not t["blocked_on_client"] and not t.get("waiting_on")
        if t["stage"] == "tickets" and t.get("assignee") and ready:
            t["stage"] = "build"
            emit(state, AGENT, "build_started", t["id"], f"{t['id']} is ready; moved to build for {t['assignee']}.")
        if t["stage"] == "build" and not t.get("agent_draft"):
            if t.get("analysis"):
                from sdlc import analysis

                text = analysis.draft_ticket(t, specs.get(t["spec_id"]))
            else:
                text = agent.draft_artifact(t, items.get(t["source_item_id"]), answers, specs.get(t["spec_id"]))
            t["agent_draft"] = ws.write_draft(t["id"], text)
            emit(state, AGENT, "draft_written", t["id"], f"Wrote a working draft for {t['id']} {t['title']}.")
        if t["stage"] == "review" and any(c.get("result") is None for c in t["acceptance_criteria"]):
            t["acceptance_criteria"] = agent.precheck(t, ws.read_draft(t["id"]), answers)
            met = sum(c["result"] == "met" for c in t["acceptance_criteria"])
            bad = sum(c["result"] == "not_met" for c in t["acceptance_criteria"])
            emit(state, AGENT, "prechecked", t["id"], f"Pre-checked {t['id']}: {met} met, {bad} not met, {len(t['acceptance_criteria']) - met - bad} for the reviewer.")
        t["status"] = "Blocked" if t["blocked_on_client"] and t["stage"] != "done" else STAGE_STATUS[t["stage"]]


def _rebuild_status(state: dict, client: str, now: str, today: date | None) -> None:
    slug = derive.slug(client)
    status = agent.build_status(client, slug, state["specs"], state["tickets"], now, today)
    rules_text = status["client_update"]["draft"]
    override = state.get("client_update_override")
    if isinstance(override, str):  # written before the override carried its rules_text
        override = {"text": override, "rules_text": rules_text}
    last = state["outbox"][-1] if state.get("outbox") else None
    if override and override.get("rules_text") != rules_text:
        # The work moved on since the owner edited the text; a fresh draft replaces it.
        state.pop("client_update_override", None)
        emit(state, AGENT, "update_stale", "status", "The work changed; the edited client update was replaced by a fresh draft.")
        override = None
    if override:
        status["client_update"]["draft"] = override["text"]
    elif last and last.get("rules_text") == rules_text:
        # Nothing changed since the last send: show what was sent, as sent.
        status["client_update"]["draft"] = last["text"]
        status["client_update"]["approval"] = {"by": last["by"], "at": last["at"], "note": None}
    state["rules_update"] = rules_text
    old = state.get("status")
    if old and _same(status, old):
        return
    state["status"] = status


def _polish_later(ws: Workspace, ticket_id: str) -> None:
    key = f"{ws.state_dir}:{ticket_id}"
    if key in _POLISHING:
        return
    _POLISHING.add(key)

    def run() -> None:
        try:
            settings = model_settings()
            draft = ws.read_draft(ticket_id)
            if settings is None or not draft:
                return
            summary = summarize(draft, settings)
            with ws.lock:
                state = ws.load()
                ticket = next((t for t in state["tickets"] if t["id"] == ticket_id), None)
                if ticket is None or ticket["stage"] != "build" or ws.read_draft(ticket_id) != draft:
                    return
                if summary:
                    marker = "## Steps"
                    text = draft.replace(marker, f"## Summary (local model {settings.model})\n\n{summary}\n\n{marker}", 1)
                    ws.write_draft(ticket_id, text)
                    ticket["provenance"] = {**ticket["provenance"], "generated_by": "local_llm", "model": settings.model, "generated_at": now_iso()}
                    emit(state, AGENT, "draft_polished", ticket_id, f"Local model {settings.model} summarised the {ticket_id} draft.")
                else:
                    ticket["provenance"] = {**ticket["provenance"], "generated_by": "rules", "model": None}
                    emit(state, AGENT, "model_unavailable", ticket_id, "Local model didn't answer; kept the rules draft.")
                    ticket["provenance"]["inputs"] = [*ticket["provenance"].get("inputs", []), "model:unavailable"]
                ws.save(state)
        except LocalOnlyError:
            return
        finally:
            _POLISHING.discard(key)

    threading.Thread(target=run, name=f"sdlc-polish-{ticket_id}", daemon=True).start()
