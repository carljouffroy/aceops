"""The console API without a server: the same gates and engine, called from JavaScript.

Used by the GitHub Pages build (docs/app), where CPython runs in the browser via
Pyodide. Files live in the page's in-memory filesystem; nothing leaves the tab.
`handle(method, path, body)` answers exactly like src/sdlc/api.py, as a JSON string.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import unquote, urlsplit

os.environ.setdefault("SDLC_ISOLATION", "thread")  # no subprocesses in a browser tab

from sdlc import analysis, engine, gates, pipeline  # noqa: E402
from sdlc.config import AGENT_NAMES, DEFAULT_TEAM, OWNER_ROLE, SOURCES  # noqa: E402
from sdlc.store import Workspace  # noqa: E402

_SOURCE = {"name": "sample"}


def setup() -> str:
    """Generate the Northline sample with the team's own BRD + dispatch, then sync once."""
    from sdlc.sample import ensure_sample

    ensure_sample()
    engine.sync(_ws())
    return "ready"


def _ws() -> Workspace:
    return Workspace.for_source(_SOURCE["name"])


def view(state: dict) -> dict:
    ws = _ws()
    work = ws.work_items()
    progress = ws.progress() or {}
    bundle = ws.bundle()
    return {
        "source": _SOURCE["name"],
        "sources": {name: (path / "work_items.json").is_file() for name, path in SOURCES.items()},
        "client_name": ws.client_name(),
        "team": list(DEFAULT_TEAM),
        "owner_role": OWNER_ROLE,
        "sections": bundle.get("brd_sections", {}),
        "intake": {
            "answered": progress.get("answered", 0),
            "total": progress.get("total", len(bundle.get("items", []))),
            "priority_gate_done": bool((progress.get("priority_gate") or {}).get("done")),
            "work_items": len(work),
            "gaps": sum(1 for row in work if row.get("kind") == "gap"),
            "brd": bool(ws.brd()),
        },
        "agent": {**state.get("agent", {}), "last_sync": engine.LAST_SYNC.get(str(ws.state_dir)), "mcp_url": "runs in this browser tab (no MCP server)"},
        "autopilot": bool(state.get("autopilot")),
        "isolation": "thread (browser)",
        "agent_names": list(AGENT_NAMES),
        "agents": pipeline.agents_view(state),
        "runs": state.get("runs", [])[-60:],
        "datasets": analysis.summaries(state),
        "version": state.get("version", 0),
        "specs": state["specs"],
        "tickets": state["tickets"],
        "releases": state["releases"],
        "status": state.get("status"),
        "outbox": state["outbox"],
        "events": state["events"][-120:],
    }


def _json(status: int, payload) -> str:
    return json.dumps({"status": status, "json": payload}, ensure_ascii=False)


def _text(status: int, text: str) -> str:
    return json.dumps({"status": status, "text": text}, ensure_ascii=False)


def _run(fn, *args) -> str:
    try:
        state = fn(_ws(), *args)
    except gates.GateError as exc:
        return _json(exc.status, {"detail": exc.message})
    return _json(200, view(state))


def tick() -> int:
    """One pass of the always-on loop; the page calls this every few seconds."""
    return len(pipeline.tick(_ws(), isolation="thread"))


def handle(method: str, path: str, body: str | None = None) -> str:
    method = (method or "GET").upper()
    route = unquote(urlsplit(path).path)
    data = {}
    if body:
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return _json(422, {"detail": "Body must be JSON."})
    actor = str(data.get("actor") or "")
    try:
        if method == "GET" and route == "/api/state":
            return _json(200, view(engine.sync(_ws())))
        if method == "GET" and route == "/api/brd":
            return _text(200, _ws().brd())
        m = re.fullmatch(r"/api/drafts/([A-Za-z0-9._-]+)", route)
        if method == "GET" and m:
            try:
                text = _ws().read_draft(m.group(1))
            except KeyError:
                return _json(404, {"detail": "Unknown ticket"})
            return _text(200, text) if text is not None else _json(404, {"detail": "No draft yet"})
        if method == "POST" and route == "/api/source":
            source = data.get("source")
            if source not in SOURCES:
                return _json(422, {"detail": "source is live or sample"})
            _SOURCE["name"] = source
            return _json(200, view(engine.sync(_ws())))
        if method == "POST" and route == "/api/agent/run":
            ws = _ws()
            pipeline.tick(ws, isolation="thread")
            return _json(200, view(engine.sync(ws)))
        if method == "POST" and route == "/api/reset":
            ws = _ws()
            ws.reset()
            return _json(200, view(engine.sync(ws)))
        m = re.fullmatch(r"/api/specs/(SPEC-\d{3})/(approve|reject)", route)
        if method == "POST" and m:
            if m.group(2) == "approve":
                return _run(gates.approve_spec, m.group(1), actor, data.get("note"))
            return _run(gates.reject_spec, m.group(1), actor, data.get("reason", ""))
        m = re.fullmatch(r"/api/tickets/(SPEC-\d{3}-T\d{2})/(accept|submit|review|draft)", route)
        if m:
            tid, action = m.groups()
            if action == "accept" and method == "POST":
                return _run(gates.accept_ticket, tid, actor)
            if action == "draft" and method == "PUT":
                return _run(gates.save_draft, tid, actor, str(data.get("text", "")))
            if action == "submit" and method == "POST":
                return _run(gates.submit_for_review, tid, actor, data.get("kind") or "file", data.get("ref"))
            if action == "review" and method == "POST":
                return _run(gates.review_ticket, tid, actor, str(data.get("decision", "")), data.get("notes"))
        if method == "POST" and route == "/api/releases":
            return _run(gates.release_spec, str(data.get("spec_id", "")), actor, data.get("client_signoff"), data.get("notes"))
        if method == "PUT" and route == "/api/status/draft":
            return _run(gates.edit_client_update, actor, str(data.get("text", "")))
        if method == "POST" and route == "/api/status/send":
            return _run(gates.send_client_update, actor)
        m = re.fullmatch(r"/api/datasets/([A-Za-z0-9._-]+)/spec", route)
        if method == "POST" and m:
            return _run(gates.draft_analysis_spec, m.group(1), actor)
        if method == "POST" and route == "/api/autopilot":
            return _run(gates.set_autopilot, actor, bool(data.get("on")))
        return _json(404, {"detail": f"No route {method} {route}"})
    except Exception as exc:  # surfaced in the console toast instead of killing the tab
        return _json(500, {"detail": f"{type(exc).__name__}: {exc}"})
