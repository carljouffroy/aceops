"""Progress counts and the priority gate."""

from __future__ import annotations

from pathlib import Path

from internal.answers import load_json
from internal.progress import build_progress

ROOT = Path(__file__).resolve().parents[2]


def test_priority_gate_flips_when_every_priority_item_is_answered() -> None:
    bundle = load_json(ROOT / "contracts" / "bundle.json")
    payload = load_json(ROOT / "contracts" / "answers.sample.json")
    schema = load_json(ROOT / "contracts" / "progress.schema.json")
    open_gate = build_progress(bundle, payload, now="2026-10-25T12:00:00+00:00")

    assert set(schema["required"]) <= set(open_gate)
    assert open_gate["total"] == 32
    assert open_gate["answered"] == 27
    assert open_gate["remaining"] == 5
    assert open_gate["priority_gate"] == {
        "ids": ["P1", "A1", "A2", "A3"],
        "done": False,
    }
    assert open_gate["by_role"]["Developer"]["blocked"] >= 1
    assert open_gate["updated_at"] == "2026-10-25T12:00:00+00:00"

    closed_rows = [
        *payload["answers"],
        {
            "id": "A2",
            "status": "PROVIDED",
            "value": "Merchant Center 554433221",
            "answered_by": "nina.voss@northline.example",
            "ts": "2026-10-23T09:00:00Z",
        },
    ]
    closed = build_progress(
        bundle,
        {"client_name": payload["client_name"], "answers": closed_rows},
        now="2026-10-25T12:01:00+00:00",
    )
    assert closed["priority_gate"]["done"] is True
    assert closed["answered"] == 28
    assert closed["remaining"] == 4
    assert closed["by_role"]["Developer"]["blocked"] == (
        open_gate["by_role"]["Developer"]["blocked"] - 1
    )
