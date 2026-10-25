"""CLI writes the rules BRD and the dispatched work items."""

from __future__ import annotations

import json
from pathlib import Path

from internal.answers import load_json
from internal.brd import render_brd
from internal.dispatch import build_work_items
from internal.run import main

ROOT = Path(__file__).resolve().parents[2]


def test_cli_writes_brd_and_work_items(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("INTERNAL_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("INTERNAL_LLM_MODEL", raising=False)
    out = tmp_path / "out"
    code = main(
        [
            "--answers",
            str(ROOT / "contracts" / "answers.sample.json"),
            "--bundle",
            str(ROOT / "contracts" / "bundle.json"),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    bundle = load_json(ROOT / "contracts" / "bundle.json")
    answers = load_json(ROOT / "contracts" / "answers.sample.json")
    assert (out / "brd.md").read_text(encoding="utf-8") == render_brd(bundle, answers)
    written = json.loads((out / "work_items.json").read_text(encoding="utf-8"))
    assert written == build_work_items(bundle, answers)
    assert any(
        item["source_item_id"] == "A2" and item["kind"] == "gap" for item in written
    )
