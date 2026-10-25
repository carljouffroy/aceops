"""End-to-end SDLC flow on the Northline sample: derive, gates, agent work, contracts.

Run with: uv run pytest src/sdlc -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from internal.run import main as internal_main
from sdlc import config, engine, gates
from sdlc.api import Console, create_app
from sdlc.store import Workspace

ROOT = Path(__file__).resolve().parents[3]
SDLC = ROOT / "contracts" / "sdlc"
OWNER, DA1, DA2, MS1, DEV1 = "Avery Park", "Jordan Lee", "Morgan Diaz", "Riley Chen", "Sam Ortiz"


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    out = tmp_path / "out"
    assert internal_main(["--answers", str(ROOT / "contracts" / "answers.sample.json"), "--out", str(out), "--no-polish"]) == 0
    return Workspace(out)


def ticket(state: dict, ticket_id: str) -> dict:
    return next(t for t in state["tickets"] if t["id"] == ticket_id)


def spec(state: dict, spec_id: str) -> dict:
    return next(s for s in state["specs"] if s["id"] == spec_id)


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SDLC / name).read_text()), format_checker=FormatChecker())


# derive


def test_sync_drafts_one_spec_per_answered_section(ws):
    state = engine.sync(ws)
    ids = [s["id"] for s in state["specs"]]
    assert ids == ["SPEC-002", "SPEC-003", "SPEC-004", "SPEC-005", "SPEC-006", "SPEC-007"]
    assert all(s["status"] == "draft" for s in state["specs"])
    r = spec(state, "SPEC-003")
    assert r["title"] == "Profit model and constraints" and r["role"] == "Data Analyst"
    assert r["scope"] == ["Build margin by product", "Rank categories by margin", "Compare ROAS targets to break-even", "Add order costs to the profit model", "Add exclusions to campaign structure"]
    f = spec(state, "SPEC-005")
    assert [i["source_item_id"] for i in f["inputs_needed_from_client"]] == ["A2", "F5"]
    assert f["depends_on"] == ["SPEC-002"]
    assert state["tickets"] == []


def test_sync_is_idempotent(ws):
    first = engine.sync(ws)
    second = engine.sync(ws)
    assert second["version"] == first["version"]
    assert [e["kind"] for e in second["events"]] == ["spec_drafted"] * 6


# G1


def test_only_the_owner_approves_a_spec(ws):
    engine.sync(ws)
    with pytest.raises(gates.GateError) as err:
        gates.approve_spec(ws, "SPEC-003", DA1)
    assert err.value.status == 403


def test_approving_splits_tickets_with_dependencies(ws):
    engine.sync(ws)
    state = gates.approve_spec(ws, "SPEC-003", OWNER, "go")
    assert spec(state, "SPEC-003")["approval"]["by"] == OWNER
    ids = [t["id"] for t in state["tickets"]]
    assert ids == [f"SPEC-003-T0{n}" for n in range(1, 6)]
    assert ticket(state, "SPEC-003-T03")["depends_on"] == ["SPEC-003-T01", "SPEC-003-T04"]
    assert ticket(state, "SPEC-003-T03")["role"] == "Marketing Specialist"
    assert all(t["stage"] == "tickets" and t["status"] == "To do" for t in state["tickets"])
    assert ticket(state, "SPEC-003-T01")["client_answer"].startswith("COGS lives in the Shopify metafield")


def test_rejecting_a_spec_makes_the_agent_redraft_it(ws):
    engine.sync(ws)
    with pytest.raises(gates.GateError):
        gates.reject_spec(ws, "SPEC-003", OWNER, "")
    state = gates.reject_spec(ws, "SPEC-003", OWNER, "Split order costs into its own workstream")
    revised = spec(state, "SPEC-003")
    assert revised["status"] == "draft" and revised["version"] == 2
    assert any("rejected by Avery Park: Split order costs" in r for r in revised["risks"])


# G2 and build


def test_accept_needs_the_right_role_and_moves_ready_work_to_build(ws):
    engine.sync(ws)
    gates.approve_spec(ws, "SPEC-003", OWNER)
    with pytest.raises(gates.GateError) as err:
        gates.accept_ticket(ws, "SPEC-003-T01", MS1)
    assert err.value.status == 403
    state = gates.accept_ticket(ws, "SPEC-003-T01", DA1)
    t1 = ticket(state, "SPEC-003-T01")
    assert t1["stage"] == "build" and t1["status"] == "In progress" and t1["assignee"] == DA1
    draft = ws.read_draft("SPEC-003-T01")
    assert draft and "## Working draft" in draft and "> COGS lives in the Shopify metafield" in draft
    state = gates.accept_ticket(ws, "SPEC-003-T02", DA1)
    t2 = ticket(state, "SPEC-003-T02")
    assert t2["stage"] == "tickets" and t2["waiting_on"][0]["reason"] == "SPEC-003-T01 hasn't passed review"
    with pytest.raises(gates.GateError) as err:
        gates.accept_ticket(ws, "SPEC-003-T01", DA2)
    assert err.value.status == 409


def test_break_even_draft_uses_client_figures_and_marks_derived_ones(ws):
    engine.sync(ws)
    gates.approve_spec(ws, "SPEC-003", OWNER)
    gates.accept_ticket(ws, "SPEC-003-T01", DA1)
    gates.submit_for_review(ws, "SPEC-003-T01", DA1)
    gates.review_ticket(ws, "SPEC-003-T01", DA2, "approved")
    state = gates.accept_ticket(ws, "SPEC-003-T02", DA1)
    assert ticket(state, "SPEC-003-T02")["stage"] == "build"
    draft = ws.read_draft("SPEC-003-T02")
    assert "| #1 | Tableware | 58% | ≈1.72 |" in draft


# review and G3


def test_precheck_flags_numbers_the_client_never_gave(ws):
    engine.sync(ws)
    gates.approve_spec(ws, "SPEC-003", OWNER)
    gates.accept_ticket(ws, "SPEC-003-T01", DA1)
    draft = ws.read_draft("SPEC-003-T01")
    gates.save_draft(ws, "SPEC-003-T01", DA1, draft + "\n## Summary\n\nAverage margin is 61% across 240 SKUs.\n")
    state = gates.submit_for_review(ws, "SPEC-003-T01", DA1)
    ac1 = ticket(state, "SPEC-003-T01")["acceptance_criteria"][0]
    assert ac1["result"] == "not_met" and "61, 240" in ac1["note"]
    with pytest.raises(gates.GateError) as err:
        gates.review_ticket(ws, "SPEC-003-T01", DA1, "approved")
    assert err.value.status == 409 and "differ from the builder" in err.value.message
    with pytest.raises(gates.GateError) as err:
        gates.review_ticket(ws, "SPEC-003-T01", DA2, "approved")
    assert "unmet criteria" in err.value.message
    with pytest.raises(gates.GateError) as err:
        gates.review_ticket(ws, "SPEC-003-T01", MS1, "approved")
    assert err.value.status == 403
    state = gates.review_ticket(ws, "SPEC-003-T01", DA2, "changes_requested", "Mark them derived.")
    assert ticket(state, "SPEC-003-T01")["stage"] == "build"
    fixed = ws.read_draft("SPEC-003-T01").replace("is 61% across 240 SKUs", "is ≈61% across ≈240 SKUs")
    gates.save_draft(ws, "SPEC-003-T01", DA1, fixed)
    state = gates.submit_for_review(ws, "SPEC-003-T01", DA1)
    assert ticket(state, "SPEC-003-T01")["acceptance_criteria"][0]["result"] == "met"
    state = gates.review_ticket(ws, "SPEC-003-T01", DA2, "approved")
    assert ticket(state, "SPEC-003-T01")["stage"] == "release"
    assert ticket(state, "SPEC-003-T02")["waiting_on"] == []


def test_submit_needs_the_assignee(ws):
    engine.sync(ws)
    gates.approve_spec(ws, "SPEC-003", OWNER)
    gates.accept_ticket(ws, "SPEC-003-T01", DA1)
    with pytest.raises(gates.GateError) as err:
        gates.submit_for_review(ws, "SPEC-003-T01", DA2)
    assert err.value.status == 403


# G4 and G5


def _to_release(ws):
    engine.sync(ws)
    gates.approve_spec(ws, "SPEC-003", OWNER)
    gates.accept_ticket(ws, "SPEC-003-T01", DA1)
    gates.submit_for_review(ws, "SPEC-003-T01", DA1)
    return gates.review_ticket(ws, "SPEC-003-T01", DA2, "approved")


def test_release_needs_owner_and_client_signoff(ws):
    _to_release(ws)
    with pytest.raises(gates.GateError) as err:
        gates.release_spec(ws, "SPEC-003", DA1, "x")
    assert err.value.status == 403
    with pytest.raises(gates.GateError) as err:
        gates.release_spec(ws, "SPEC-003", OWNER)
    assert err.value.status == 422
    state = gates.release_spec(ws, "SPEC-003", OWNER, "Nina Voss, email")
    done = ticket(state, "SPEC-003-T01")
    assert done["stage"] == "done" and done["status"] == "Done" and done["release"]["release_id"] == "REL-001"
    assert state["releases"][0]["tickets"] == ["SPEC-003-T01"]
    assert "Build margin by product" in state["releases"][0]["client_summary"]
    assert state["status"]["counts_by_stage"]["done"] == 1


def test_client_update_is_sent_once_by_the_owner(ws):
    _to_release(ws)
    gates.release_spec(ws, "SPEC-003", OWNER, "Nina Voss, email")
    with pytest.raises(gates.GateError) as err:
        gates.send_client_update(ws, DA1)
    assert err.value.status == 403
    state = gates.edit_client_update(ws, OWNER, "Hello Northline, short version.")
    assert state["status"]["client_update"]["draft"] == "Hello Northline, short version."
    state = gates.send_client_update(ws, OWNER)
    assert len(state["outbox"]) == 1
    assert [q["source_item_id"] for q in state["outbox"][0]["follow_up_questions"]] == ["A2", "A4", "F5", "D3", "D5", "C3"]
    assert state["status"]["client_update"]["approval"]["by"] == OWNER
    with pytest.raises(gates.GateError) as err:
        gates.send_client_update(ws, OWNER)
    assert err.value.status == 409


# contracts and local-only


def test_runtime_output_matches_the_contracts(ws):
    _to_release(ws)
    state = gates.release_spec(ws, "SPEC-003", OWNER, "Nina Voss, email")
    for name, objs in (("spec.schema.json", state["specs"]), ("ticket.schema.json", state["tickets"]), ("status_report.schema.json", [state["status"]])):
        v = validator(name)
        for obj in objs:
            assert [f"{list(e.path)}: {e.message}" for e in v.iter_errors(obj)] == []
    work_schema = json.loads((ROOT / "contracts" / "work_items.schema.json").read_text())
    base = list(work_schema["items"]["properties"])
    assert list(Draft202012Validator(work_schema).iter_errors([{k: t[k] for k in base} for t in state["tickets"]])) == []
    assert (ws.state_dir / "tickets.json").is_file() and (ws.state_dir / "status.json").is_file()


def test_model_url_must_be_loopback(monkeypatch):
    monkeypatch.setenv("SDLC_LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("SDLC_LLM_MODEL", "gpt")
    with pytest.raises(config.LocalOnlyError):
        config.model_settings()
    monkeypatch.setenv("SDLC_LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    assert config.model_settings().model == "gpt"
    monkeypatch.setenv("SDLC_LLM_BASE_URL", "http://[::1]:8000/v1")
    assert config.model_settings().base_url == "http://[::1]:8000/v1"


# http


def test_console_api_guards_writes_and_runs_gates(ws, monkeypatch):
    monkeypatch.setitem(config.SOURCES, "test", ws.input_dir)
    client = TestClient(create_app(Console("test")))
    assert client.get("/").status_code == 200 and "ACE OPS" in client.get("/").text
    state = client.get("/api/state").json()
    assert len(state["specs"]) == 6 and state["agent"]["mode"] == "rules"
    assert client.post("/api/specs/SPEC-003/approve", json={"actor": OWNER}).status_code == 403
    headers = {"X-ACE-Console": "1"}
    assert client.post("/api/specs/SPEC-003/approve", json={"actor": DA1}, headers=headers).status_code == 403
    view = client.post("/api/specs/SPEC-003/approve", json={"actor": OWNER}, headers=headers).json()
    assert len(view["tickets"]) == 5
    view = client.post("/api/tickets/SPEC-003-T01/accept", json={"actor": DA1}, headers=headers).json()
    assert ticket(view, "SPEC-003-T01")["stage"] == "build"
    assert client.get("/api/drafts/SPEC-003-T01").text.startswith("# Build margin by product")
    assert client.get("/api/drafts/nope").status_code == 404
    res = client.post("/api/tickets/SPEC-003-T01/review", json={"actor": DA2, "decision": "approved"}, headers=headers)
    assert res.status_code == 409
    view = client.post("/api/reset", json={}, headers=headers).json()
    assert view["tickets"] == [] and len(view["specs"]) == 6
