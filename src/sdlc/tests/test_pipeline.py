"""Autopilot: six stage agents, each run from scratch, carry work from spec to sent update.

Run with: uv run pytest src/sdlc -q
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from internal.run import main as internal_main
from sdlc import engine, gates, pipeline
from sdlc.agents.stages import AGENTS, DebugAgent, DevAgent, SpecAgent, TestAgent, fix_untraced_numbers
from sdlc.store import Workspace

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def ws(tmp_path: Path, monkeypatch) -> Workspace:
    out = tmp_path / "out"
    assert internal_main(["--answers", str(ROOT / "contracts" / "answers.sample.json"), "--out", str(out), "--no-polish"]) == 0
    monkeypatch.setenv("SDLC_AUTOPILOT", "1")
    return Workspace(out)


def run_until_quiet(ws: Workspace, *, isolation: str = "thread", max_ticks: int = 30) -> list[dict]:
    runs: list[dict] = []
    for _ in range(max_ticks):
        batch = pipeline.tick(ws, isolation=isolation)
        runs += batch
        if not batch:
            break
    return runs


def ticket(state: dict, ticket_id: str) -> dict:
    return next(t for t in state["tickets"] if t["id"] == ticket_id)


def test_agents_are_refused_while_autopilot_is_off(ws, monkeypatch):
    monkeypatch.setenv("SDLC_AUTOPILOT", "0")
    engine.sync(ws)
    with pytest.raises(gates.GateError) as err:
        gates.approve_spec(ws, "SPEC-003", "Spec agent")
    assert err.value.status == 403 and "Autopilot is off" in err.value.message
    assert pipeline.tick(ws, isolation="thread") == []


def test_only_a_human_owner_switches_autopilot(ws, monkeypatch):
    monkeypatch.setenv("SDLC_AUTOPILOT", "0")
    engine.sync(ws)
    for actor in ("Jordan Lee", "Spec agent"):
        with pytest.raises(gates.GateError) as err:
            gates.set_autopilot(ws, actor, True)
        assert err.value.status == 403
    state = gates.set_autopilot(ws, "Avery Park", True)
    assert state["autopilot"] is True


def test_each_agent_sees_only_its_declared_inputs(ws):
    engine.sync(ws)
    ctx = SpecAgent.context(ws, "SPEC-003")
    assert set(ctx.inputs) == set(SpecAgent.reads) == {"specs", "bundle"}
    assert "tickets" not in ctx.inputs and "draft" not in ctx.inputs
    ctx = DevAgent.context(ws, "SPEC-003-T01")
    assert set(ctx.inputs) == {"tickets", "draft", "answers"}
    assert "specs" not in ctx.inputs
    assert all(set(cls.reads) <= set(("brd", "work_items", "bundle", "dependencies", "specs", "tickets", "status", "releases", "outbox", "draft", "answers")) for cls in AGENTS.values())


def test_autopilot_takes_a_spec_to_a_sent_client_update(ws):
    runs = run_until_quiet(ws)
    state = engine.sync(ws)
    by_agent = {name: [r for r in runs if r["agent"] == name] for name in ("Spec agent", "Dev agent", "Test agent", "Deploy agent", "Status agent")}
    assert all(by_agent.values()), {k: len(v) for k, v in by_agent.items()}
    approved = [s for s in state["specs"] if s["status"] == "approved"]
    assert approved and all(s["approval"]["by"] == "Spec agent" for s in approved)
    done = [t for t in state["tickets"] if t["stage"] == "done"]
    assert done, [(t["id"], t["stage"], t.get("waiting_on")) for t in state["tickets"]]
    for t in done:
        assert t["assignee"] == "Dev agent"
        assert t["review"]["reviewer"] == "Test agent" and t["review"]["reviewer"] != t["assignee"]
        assert t["release"]["approved_by"] == "Deploy agent"
    assert state["releases"] and state["outbox"]
    assert state["outbox"][-1]["by"] == "Status agent"
    assert all(r["ok"] for r in runs if r["action"] not in ("skip",)), [r for r in runs if not r["ok"]]
    # Nothing waits on a person except tickets blocked on the client.
    stuck = [t for t in state["tickets"] if t["stage"] not in ("done",) and not t["blocked_on_client"] and not t.get("waiting_on")]
    assert stuck == [], [(t["id"], t["stage"], t.get("assignee"), t.get("review")) for t in stuck]


def test_debug_agent_fixes_a_draft_the_test_agent_rejects(ws):
    engine.sync(ws)
    gates.approve_spec(ws, "SPEC-003", "Spec agent")
    gates.accept_ticket(ws, "SPEC-003-T01", "Dev agent")
    draft = ws.read_draft("SPEC-003-T01")
    gates.save_draft(ws, "SPEC-003-T01", "Dev agent", draft + "\n## Summary\n\nAverage margin is 61% across 240 SKUs.\n")
    gates.submit_for_review(ws, "SPEC-003-T01", "Dev agent")
    first = pipeline.tick(ws, isolation="thread")
    actions = [(r["agent"], r["action"]) for r in first]
    assert ("Test agent", "changes_requested") in actions, actions
    assert ("Debug agent", "fixed") in actions, actions
    state = engine.sync(ws)
    t = ticket(state, "SPEC-003-T01")
    assert t["autopilot_rounds"] == 1
    assert "≈61" in ws.read_draft("SPEC-003-T01") and "≈240" in ws.read_draft("SPEC-003-T01")
    run_until_quiet(ws)
    t = ticket(engine.sync(ws), "SPEC-003-T01")
    assert t["review"]["decision"] == "approved" and t["review"]["reviewer"] == "Test agent"


def test_debug_agent_hands_unfixable_work_to_a_person(ws):
    engine.sync(ws)
    gates.approve_spec(ws, "SPEC-003", "Spec agent")
    gates.accept_ticket(ws, "SPEC-003-T01", "Dev agent")
    gates.submit_for_review(ws, "SPEC-003-T01", "Dev agent")
    gates.review_ticket(ws, "SPEC-003-T01", "Test agent", "changes_requested", "Rewrite the method section for the client.")
    runs = pipeline.tick(ws, isolation="thread")
    assert any(r["agent"] == "Debug agent" and r["action"] == "needs_human" for r in runs), runs
    t = ticket(engine.sync(ws), "SPEC-003-T01")
    assert t["needs_human"] and t["stage"] == "build"


def test_fix_untraced_numbers_only_touches_checked_sections():
    draft = "# T\n\n## What the client told us\n\n> 61% was mentioned\n\n## Working draft\n\nAverage margin is 61% across 240 SKUs.\n\n## Steps\n\n1. 61 steps\n"
    fixed, n = fix_untraced_numbers(draft, "AC1: 2 number(s) don't trace to any client answer: 61, 240. Mark derived figures with ≈ or fix them.")
    assert n == 2
    assert "is ≈61% across ≈240 SKUs" in fixed
    assert "> 61% was mentioned" in fixed and "1. 61 steps" in fixed


def test_process_isolation_runs_each_agent_in_its_own_process(ws):
    engine.sync(ws)
    runs = pipeline.tick(ws, isolation="process", max_runs=1)
    assert runs, "autopilot ran nothing"
    run = runs[0]
    assert run["agent"] == "Spec agent" and run["ok"], run
    assert all(r["pid"] and r["pid"] != os.getpid() for r in runs if r["ok"]), runs
    assert len({r["pid"] for r in runs if r["ok"]}) == len([r for r in runs if r["ok"]]), "each run must be its own process"
    state = engine.sync(ws)
    assert any(s["status"] == "approved" and s["approval"]["by"] == "Spec agent" for s in state["specs"])
    assert (ws.state_dir / "runs.jsonl").is_file()


def test_runs_are_logged_and_shown(ws):
    runs = pipeline.tick(ws, isolation="thread", max_runs=2)
    state = engine.sync(ws)
    assert len(state["runs"]) == len(runs) >= 2
    view = pipeline.agents_view(state)
    assert [a["key"] for a in view] == ["spec", "dev", "test", "debug", "deploy", "status"]
    assert view[0]["runs"] == 2 and view[0]["last"]["action"] == "approved"
    kinds = {e["kind"] for e in state["events"]}
    assert "agent_approved" in kinds


def test_test_agent_approves_clean_work_and_names_human_criteria(ws):
    engine.sync(ws)
    gates.approve_spec(ws, "SPEC-003", "Spec agent")
    gates.accept_ticket(ws, "SPEC-003-T01", "Dev agent")
    gates.submit_for_review(ws, "SPEC-003-T01", "Dev agent")
    state = engine.sync(ws)
    assert TestAgent.find_work(state) == ["SPEC-003-T01"]
    outcome = TestAgent().run(TestAgent.context(ws, "SPEC-003-T01"), ws)
    assert outcome.action == "approved" and "spot-check" in outcome.detail
    assert DebugAgent.find_work(engine.sync(ws)) == []
