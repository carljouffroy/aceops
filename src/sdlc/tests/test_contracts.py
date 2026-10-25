"""SDLC contract checks: samples match the schemas, gates reject bad states, tickets fit work_items.

Run with: uv run pytest src/sdlc -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SDLC = ROOT / "contracts" / "sdlc"
WORK_ITEMS_SCHEMA = ROOT / "contracts" / "work_items.schema.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = _load(SDLC / name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.fixture(scope="module")
def specs():
    return _load(SDLC / "specs.sample.json")


@pytest.fixture(scope="module")
def tickets():
    return _load(SDLC / "tickets.sample.json")


def _by_stage(tickets: list[dict], stage: str) -> dict:
    return next(t for t in tickets if t["stage"] == stage)


@pytest.mark.parametrize(
    ("schema", "sample", "is_list"),
    [
        ("spec.schema.json", "specs.sample.json", True),
        ("ticket.schema.json", "tickets.sample.json", True),
        ("status_report.schema.json", "status_report.sample.json", False),
    ],
)
def test_samples_match_schemas(schema, sample, is_list):
    validator = _validator(schema)
    payload = _load(SDLC / sample)
    for obj in payload if is_list else [payload]:
        errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(obj)]
        assert errors == []


@pytest.mark.skipif(not WORK_ITEMS_SCHEMA.is_file(), reason="work_items.schema.json not on this branch yet")
def test_ticket_without_sdlc_fields_is_a_work_item(tickets):
    schema = _load(WORK_ITEMS_SCHEMA)
    base_fields = list(schema["items"]["properties"])
    stripped = [{k: t[k] for k in base_fields} for t in tickets]
    errors = [f"{list(e.path)}: {e.message}" for e in Draft202012Validator(schema).iter_errors(stripped)]
    assert errors == []


def test_ticket_references_resolve(specs, tickets):
    spec_ids = {s["id"] for s in specs}
    ticket_ids = {t["id"] for t in tickets}
    for t in tickets:
        assert t["spec_id"] in spec_ids
        assert set(t["depends_on"]) <= ticket_ids


def test_build_entry_rule_holds_in_sample(tickets):
    by_id = {t["id"]: t for t in tickets}
    for t in tickets:
        if t["stage"] in ("build", "review", "release", "done"):
            assert not t["blocked_on_client"], t["id"]
            for dep in t["depends_on"]:
                assert (by_id[dep].get("review") or {}).get("decision") == "approved", (t["id"], dep)


def test_reviewer_is_not_the_builder(tickets):
    for t in tickets:
        if t.get("review"):
            assert t["review"]["reviewer"] != t["assignee"], t["id"]


def test_approved_spec_needs_approval(specs):
    approved = next(s for s in specs if s["status"] == "approved")
    assert not _validator("spec.schema.json").is_valid({**approved, "approval": None})


@pytest.mark.parametrize(
    ("stage", "change"),
    [
        ("build", {"assignee": None}),
        ("review", {"evidence": []}),
        ("release", {"review": {"reviewer": "x", "decision": "changes_requested", "notes": None, "at": "2026-10-25T14:00:00-07:00"}}),
        ("release", {"stage": "done", "status": "Done", "release": None}),
        ("build", {"status": "in_progress"}),
        ("build", {"priority": "high"}),
        ("build", {"kind": "ticket"}),
    ],
    ids=[
        "build-without-assignee",
        "review-without-evidence",
        "release-with-changes-requested",
        "done-without-release",
        "status-the-board-does-not-know",
        "string-priority",
        "kind-outside-work-items-enum",
    ],
)
def test_ticket_gates_reject_bad_states(tickets, stage, change):
    assert not _validator("ticket.schema.json").is_valid({**_by_stage(tickets, stage), **change})


def test_dependencies_only_name_bundle_items():
    bundle = ROOT / "contracts" / "bundle.json"
    ids = {item["id"] for item in _load(bundle)["items"]}
    deps = _load(SDLC / "item_dependencies.json")["depends_on"]
    for item, prereqs in deps.items():
        assert item in ids
        assert set(prereqs) <= ids
        assert item not in prereqs
