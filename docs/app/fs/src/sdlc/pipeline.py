"""Autopilot orchestrator: hands each piece of ready work to its stage agent.

A tick runs the stages in order (spec, dev, test, debug, deploy, status). For every
subject an agent reports ready, the agent runs once, in its own process by default,
and the run is logged with the agent's name, its subject, its declared inputs and
its outcome. People can switch autopilot off at any time; the gates then refuse
agent identities and the console buttons are the only way forward.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from sdlc import engine
from sdlc.agents.base import StageAgent
from sdlc.agents.stages import AGENTS, ORDER
from sdlc.config import ROOT
from sdlc.gates import GateError
from sdlc.store import Workspace, emit, now_iso

MAX_RUNS_PER_AGENT = 8  # per agent per tick, so a busy early stage never starves a later one
MAX_LOG = 200
RUN_TIMEOUT_S = 90


def isolation_mode() -> str:
    mode = os.environ.get("SDLC_ISOLATION", "process").strip().lower()
    return mode if mode in ("process", "thread") else "process"


def autopilot_on(state: dict) -> bool:
    return bool(state.get("autopilot"))


def tick(ws: Workspace, *, isolation: str | None = None, max_runs: int = MAX_RUNS_PER_AGENT) -> list[dict]:
    """One pass over all stages in order. Each agent runs at most `max_runs` times. Returns the run records."""
    isolation = isolation or isolation_mode()
    runs: list[dict] = []
    state = engine.sync(ws)
    if not autopilot_on(state):
        return runs
    for key in ORDER:
        cls = AGENTS[key]
        for subject in cls.find_work(state)[:max_runs]:
            # Hold the lock for one run only, so the console keeps answering between runs
            # and nobody else writes state while the agent's process does.
            with ws.lock:
                if not autopilot_on(ws.load()):
                    return runs
                record = run_agent(cls, ws, subject, isolation)
            runs.append(record)
            state = engine.sync(ws)
            _log(ws, state, record)
    return runs


def run_agent(cls: type[StageAgent], ws: Workspace, subject: str, isolation: str) -> dict:
    started = time.monotonic()
    record = {
        "id": f"RUN-{int(time.time() * 1000)}",
        "agent": cls.name,
        "key": cls.key,
        "stage": cls.stage,
        "subject": subject,
        "at": now_iso(),
        "isolation": isolation,
        "reads": list(cls.reads),
    }
    if isolation == "process":
        payload = _run_in_process(cls.key, ws, subject)
    else:
        payload = _run_in_thread(cls, ws, subject)
    record.update({k: payload.get(k) for k in ("ok", "action", "detail", "pid")})
    record["ms"] = int((time.monotonic() - started) * 1000)
    return record


def _run_in_thread(cls: type[StageAgent], ws: Workspace, subject: str) -> dict:
    try:
        ctx = cls.context(ws, subject)
        outcome = cls().run(ctx, ws)
        return {**outcome.as_dict(), "pid": os.getpid()}
    except GateError as exc:
        return {"ok": False, "action": "refused", "detail": f"{exc.status}: {exc.message}", "pid": os.getpid()}
    except Exception as exc:
        return {"ok": False, "action": "error", "detail": f"{type(exc).__name__}: {exc}", "pid": os.getpid()}


def _run_in_process(key: str, ws: Workspace, subject: str) -> dict:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src") + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "sdlc.agents", key, str(ws.input_dir), subject],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_S,
            env=env,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "action": "error", "detail": f"{key} agent timed out after {RUN_TIMEOUT_S}s", "pid": None}
    line = (proc.stdout or "").strip().splitlines()
    try:
        payload = json.loads(line[-1]) if line else {}
    except json.JSONDecodeError:
        payload = {}
    if not payload:
        err = (proc.stderr or "").strip().splitlines()
        return {"ok": False, "action": "error", "detail": (err[-1] if err else f"{key} agent produced no outcome"), "pid": None}
    return payload


def _log(ws: Workspace, state: dict, record: dict) -> None:
    with ws.lock:
        state = ws.load()
        state.setdefault("runs", []).append(record)
        state["runs"] = state["runs"][-MAX_LOG:]
        verb = record.get("action") or "ran"
        emit(state, record["agent"], f"agent_{verb}", record["subject"], record.get("detail") or verb)
        ws.save(state)
    try:
        path = ws.state_dir / "runs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def agents_view(state: dict) -> list[dict]:
    """What the console shows: each agent, its stage, inputs and last run."""
    runs = state.get("runs", [])
    out = []
    for key in ORDER:
        cls = AGENTS[key]
        mine = [r for r in runs if r.get("key") == key]
        last = mine[-1] if mine else None
        out.append(
            {
                "key": key,
                "name": cls.name,
                "stage": cls.stage,
                "reads": list(cls.reads),
                "system_prompt": cls.system_prompt,
                "runs": len(mine),
                "last": last,
                "pending": len(cls.find_work(state)),
            }
        )
    return out
