"""SDLC console and admin API on loopback. The page shell holds no client text.

Write routes require the X-ACE-Console header, which a cross-site form can't
send, and every gate re-checks who is acting (see gates.py).
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from sdlc import analysis, engine, gates, pipeline
from sdlc.config import AGENT_NAMES, DEFAULT_TEAM, OWNER_ROLE, SOURCES, mcp_port
from sdlc.store import Workspace

WEB = Path(__file__).with_name("web")
NO_STORE = {"Cache-Control": "no-store"}


def page() -> str:
    """The console page with its theme inlined. Read per request so a theme edit shows on reload."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    return html.replace("/*__THEME__*/", (WEB / "theme.css").read_text(encoding="utf-8"), 1)
CONSOLE_HEADER = "x-ace-console"
CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]", "testserver")


class Actor(BaseModel):
    actor: str = Field(min_length=1, max_length=80)


class Note(Actor):
    note: str | None = Field(default=None, max_length=2000)


class Reason(Actor):
    reason: str = Field(default="", max_length=2000)


class DraftText(Actor):
    text: str = Field(max_length=60000)


class Evidence(Actor):
    kind: Literal["link", "file", "pr", "note"] = "file"
    ref: str | None = Field(default=None, max_length=2000)


class Review(Actor):
    decision: Literal["approved", "changes_requested"]
    notes: str | None = Field(default=None, max_length=4000)


class Release(Actor):
    spec_id: str = Field(pattern=r"^SPEC-[0-9]{3}$")
    client_signoff: str | None = Field(default=None, max_length=400)
    notes: str | None = Field(default=None, max_length=4000)


class Source(BaseModel):
    source: Literal["live", "sample"]


class Autopilot(Actor):
    on: bool


class Console:
    """Which data source the console is showing."""

    def __init__(self, source: str = "live"):
        self.source = source
        self._lock = threading.Lock()

    def workspace(self) -> Workspace:
        return Workspace.for_source(self.source)

    def switch(self, source: str) -> None:
        with self._lock:
            self.source = source


def view(console: Console, state: dict) -> dict:
    ws = console.workspace()
    work = ws.work_items()
    progress = ws.progress() or {}
    bundle = ws.bundle()
    return {
        "source": console.source,
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
        "agent": {**state.get("agent", {}), "last_sync": engine.LAST_SYNC.get(str(ws.state_dir)), "mcp_url": f"http://127.0.0.1:{mcp_port()}/mcp"},
        "autopilot": bool(state.get("autopilot")),
        "isolation": pipeline.isolation_mode(),
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


def create_app(console: Console | None = None) -> FastAPI:
    console = console or Console()
    app = FastAPI(title="ACE Ops SDLC console", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.console = console

    @app.middleware("http")
    async def guard_requests(request: Request, call_next):
        # Loopback only: a DNS-rebound or spoofed Host gets nothing, and the page can't be framed.
        host = (request.headers.get("host") or "").rsplit(":", 1)[0] if not (request.headers.get("host") or "").startswith("[") else (request.headers.get("host") or "").split("]")[0] + "]"
        if host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "The console answers only on this machine."}, status_code=421)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get(CONSOLE_HEADER) != "1":
            return JSONResponse({"detail": "Write requests must come from the ACE Ops console."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path == "/":
            response.headers["Content-Security-Policy"] = CSP
        return response

    def run(fn, *args, **kwargs) -> dict:
        try:
            state = fn(console.workspace(), *args, **kwargs)
        except gates.GateError as exc:
            raise HTTPException(status_code=exc.status, detail=exc.message) from None
        return view(console, state)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(page(), headers=NO_STORE)

    @app.get("/api/state")
    def state() -> dict:
        return view(console, engine.sync(console.workspace()))

    @app.get("/api/brd", response_class=PlainTextResponse)
    def brd() -> PlainTextResponse:
        return PlainTextResponse(console.workspace().brd(), headers=NO_STORE)

    @app.get("/api/drafts/{ticket_id}", response_class=PlainTextResponse)
    def draft(ticket_id: str) -> PlainTextResponse:
        try:
            text = console.workspace().read_draft(ticket_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown ticket") from None
        if text is None:
            raise HTTPException(status_code=404, detail="No draft yet")
        return PlainTextResponse(text, headers=NO_STORE)

    @app.post("/api/source")
    def source(body: Source) -> dict:
        console.switch(body.source)
        return view(console, engine.sync(console.workspace()))

    @app.post("/api/agent/run")
    def agent_run() -> dict:
        ws = console.workspace()
        pipeline.tick(ws)
        return view(console, engine.sync(ws))

    @app.post("/api/datasets/{name}/spec")
    def dataset_spec(name: str, body: Actor) -> dict:
        return run(gates.draft_analysis_spec, name, body.actor)

    @app.post("/api/autopilot")
    def autopilot(body: Autopilot) -> dict:
        # Only flips the flag; the always-on loop runs the agents within a few seconds.
        return run(gates.set_autopilot, body.actor, body.on)

    @app.post("/api/reset")
    def reset() -> dict:
        ws = console.workspace()
        ws.reset()
        return view(console, engine.sync(ws))

    @app.post("/api/specs/{spec_id}/approve")
    def approve(spec_id: str, body: Note) -> dict:
        return run(gates.approve_spec, spec_id, body.actor, body.note)

    @app.post("/api/specs/{spec_id}/reject")
    def reject(spec_id: str, body: Reason) -> dict:
        return run(gates.reject_spec, spec_id, body.actor, body.reason)

    @app.post("/api/tickets/{ticket_id}/accept")
    def accept(ticket_id: str, body: Actor) -> dict:
        return run(gates.accept_ticket, ticket_id, body.actor)

    @app.put("/api/tickets/{ticket_id}/draft")
    def save(ticket_id: str, body: DraftText) -> dict:
        return run(gates.save_draft, ticket_id, body.actor, body.text)

    @app.post("/api/tickets/{ticket_id}/submit")
    def submit(ticket_id: str, body: Evidence) -> dict:
        return run(gates.submit_for_review, ticket_id, body.actor, body.kind, body.ref)

    @app.post("/api/tickets/{ticket_id}/review")
    def review(ticket_id: str, body: Review) -> dict:
        return run(gates.review_ticket, ticket_id, body.actor, body.decision, body.notes)

    @app.post("/api/releases")
    def release(body: Release) -> dict:
        return run(gates.release_spec, body.spec_id, body.actor, body.client_signoff, body.notes)

    @app.put("/api/status/draft")
    def edit_update(body: DraftText) -> dict:
        return run(gates.edit_client_update, body.actor, body.text)

    @app.post("/api/status/send")
    def send_update(body: Actor) -> dict:
        return run(gates.send_client_update, body.actor)

    return app
