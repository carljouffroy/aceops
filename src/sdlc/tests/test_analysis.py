"""Promotion effectiveness from a client export: analysis, spec, tickets, gates, autopilot.

Run with: uv run pytest src/sdlc -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from internal.run import main as internal_main
from sdlc import analysis, engine, gates, pipeline
from sdlc.store import Workspace

ROOT = Path(__file__).resolve().parents[3]
SDLC = ROOT / "contracts" / "sdlc"
OWNER, MS1, MS2, DA1 = "Avery Park", "Riley Chen", "Casey Brooks", "Jordan Lee"


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    out = tmp_path / "out"
    assert internal_main(["--answers", str(ROOT / "contracts" / "answers.sample.json"), "--out", str(out), "--no-polish"]) == 0
    return Workspace(out)


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SDLC / name).read_text()), format_checker=FormatChecker())


def test_superstore_analysis_has_evidence_both_ways():
    path = analysis.dataset_path("superstore")
    assert path is not None
    a = analysis.analyze(path)
    assert a["rows"] == 9994 and a["overall"]["products"] == 1850
    assert 0.4 < a["overall"]["promo_share"] < 0.6
    assert {r["key"] for r in a["by_region"]} == {"Central", "East", "South", "West"}
    assert {r["key"] for r in a["by_segment"]} == {"Consumer", "Corporate", "Home Office"}
    assert a["promote"] and a["stop"], (len(a["promote"]), len(a["stop"]))
    for p in a["promote"]:
        assert p["lift"] >= 0.15 and p["n_promo"] >= 4 and p["n_base"] >= 4 and p["promo_share"] < 0.6
        assert p["profit_promo"] is None or p["profit_promo"] >= 0
    for p in a["stop"]:
        assert p["lift"] <= -0.15 or (p["profit_promo"] is not None and p["profit_promo"] < 0)
    assert a["figures"] and all(isinstance(f, float) for f in a["figures"])
    assert analysis.analyze(path) is a  # cached by mtime


def test_spec_from_data_flows_through_the_gates_and_matches_the_contracts(ws):
    engine.sync(ws)
    with pytest.raises(gates.GateError) as err:
        gates.draft_analysis_spec(ws, "superstore", DA1)
    assert err.value.status == 403
    with pytest.raises(gates.GateError) as err:
        gates.draft_analysis_spec(ws, "nope", OWNER)
    assert err.value.status == 404
    state = gates.draft_analysis_spec(ws, "superstore", OWNER)
    spec = next(s for s in state["specs"] if s.get("analysis"))
    assert spec["id"] == "SPEC-101" and spec["status"] == "draft" and spec["client_signoff_required"]
    assert list(validator("spec.schema.json").iter_errors(spec)) == []
    with pytest.raises(gates.GateError) as err:
        gates.draft_analysis_spec(ws, "superstore", OWNER)
    assert err.value.status == 409
    state = gates.approve_spec(ws, spec["id"], OWNER)
    tickets = [t for t in state["tickets"] if t["spec_id"] == spec["id"]]
    assert tickets and len(tickets) == len(spec["analysis"]["promote"]) + len(spec["analysis"]["stop"])
    for t in tickets:
        assert list(validator("ticket.schema.json").iter_errors(t)) == [], t["id"]
    first = tickets[0]
    assert first["role"] == "Marketing Specialist" and first["title"].startswith("Run a promotion on")
    state = gates.accept_ticket(ws, first["id"], MS1)
    draft = ws.read_draft(first["id"])
    assert draft and "| With promotion |" in draft and "## Recommendation" in draft
    state = gates.submit_for_review(ws, first["id"], MS1)
    t = next(x for x in state["tickets"] if x["id"] == first["id"])
    results = {c["id"]: c["result"] for c in t["acceptance_criteria"]}
    assert results["AC1"] == "met", t["acceptance_criteria"]
    assert results["AC3"] == "met"
    state = gates.review_ticket(ws, first["id"], MS2, "approved")
    assert next(x for x in state["tickets"] if x["id"] == first["id"])["stage"] == "release"
    assert any(d["spec_id"] == spec["id"] for d in analysis.summaries(state))
    status = state["status"]
    assert list(validator("status_report.schema.json").iter_errors(status)) == []


def test_autopilot_picks_up_client_data_on_its_own(ws, monkeypatch):
    monkeypatch.setenv("SDLC_AUTOPILOT", "1")
    runs = []
    for _ in range(12):
        batch = pipeline.tick(ws, isolation="thread")
        runs += batch
        if not batch:
            break
    state = engine.sync(ws)
    analyst = [r for r in runs if r["agent"] == "Analyst agent"]
    assert analyst and analyst[0]["action"] == "drafted", runs[:3]
    spec = next(s for s in state["specs"] if s.get("analysis"))
    assert spec["status"] == "approved" and spec["approval"]["by"] == "Spec agent"
    done = [t for t in state["tickets"] if t["spec_id"] == spec["id"] and t["stage"] == "done"]
    assert done, [(t["id"], t["stage"]) for t in state["tickets"] if t["spec_id"] == spec["id"]]
    assert all(t["review"]["reviewer"] == "Test agent" and t["assignee"] == "Dev agent" for t in done)
