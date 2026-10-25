"""Board API: sort, progress, escaped client text, and status overrides."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from board.app import create_app


def _item(**overrides) -> dict:
    row = {
        "id": "WI-1",
        "title": "Check the feed",
        "role": "Developer",
        "source_item_id": "F1",
        "kind": "task",
        "priority": False,
        "status": "To do",
        "blocked_on_client": False,
        "due": None,
        "client_answer": "plain",
        "answered_by": "nina.voss@northline.example",
        "client_ai_name": None,
        "ts": "2026-10-14T11:20:00Z",
        "history": [],
    }
    row.update(overrides)
    return row


def test_board_api_keeps_status_edits_out_of_the_source(tmp_path: Path) -> None:
    out = tmp_path / "data" / "out"
    out.mkdir(parents=True)
    source = [
        _item(
            id="WI-I",
            title="Rank categories",
            role="Data Analyst",
            source_item_id="R2",
            priority=True,
            status="In progress",
            client_answer="tableware 58%",
        ),
        _item(
            id="WI-P",
            title="Verify Google Ads access",
            role="Marketing Specialist",
            source_item_id="A1",
            priority=True,
            status="To do",
            client_answer="<img src=x onerror=alert(1)>",
        ),
        _item(
            id="WI-B",
            title="Chase Merchant Center access",
            role="Developer",
            source_item_id="A2",
            kind="gap",
            status="Blocked",
            blocked_on_client=True,
            client_answer=None,
            answered_by=None,
            ts=None,
        ),
        _item(
            id="WI-D",
            title="Review feed setup",
            role="Developer",
            source_item_id="F2",
            status="Done",
            client_answer="hourly feed",
        ),
    ]
    work_path = out / "work_items.json"
    original = json.dumps(source, indent=2) + "\n"
    work_path.write_text(original, encoding="utf-8")
    (out / "brd.md").write_text("# Business requirements\n\nClient: Northline Goods\n", encoding="utf-8")
    (out / "progress.json").write_text(
        json.dumps(
            {
                "total": 32,
                "answered": 27,
                "remaining": 5,
                "priority_gate": {"ids": ["P1", "A1", "A2", "A3"], "done": False},
                "by_role": {},
                "updated_at": "2026-10-25T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    client = TestClient(create_app(tmp_path))
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Ready to start" in page.text
    assert "textContent" in page.text
    assert "innerHTML" not in page.text
    assert "http://" not in page.text and "https://" not in page.text
    assert "<img src=x onerror=alert(1)>" not in page.text

    listed = client.get("/api/board")
    assert listed.status_code == 200
    assert listed.headers["content-type"].startswith("application/json")
    body = listed.json()
    assert body["client_name"] == "Northline Goods"
    assert body["source"] == "out"
    assert body["progress"] == {"answered": 27, "total": 32, "priority_gate_done": False}
    assert [row["id"] for row in body["items"]] == ["WI-I", "WI-P", "WI-B", "WI-D"]
    assert body["counts"]["blocked_on_client"] == 1
    assert body["counts"]["roles"]["Developer"] == 2
    answer = next(row for row in body["items"] if row["id"] == "WI-P")["client_answer"]
    assert answer == "<img src=x onerror=alert(1)>"

    saved = client.patch("/api/items/WI-B", json={"status": "Done"})
    assert saved.status_code == 200
    assert saved.json()["status"] == "Done"
    assert saved.json()["blocked_on_client"] is True
    assert work_path.read_text(encoding="utf-8") == original
    overrides = json.loads((out / "overrides.json").read_text(encoding="utf-8"))
    assert overrides == {"statuses": {"WI-B": "Done"}}
    again = client.get("/api/board").json()
    assert [row["id"] for row in again["items"]] == ["WI-I", "WI-P", "WI-B", "WI-D"]
    assert next(row for row in again["items"] if row["id"] == "WI-B")["status"] == "Done"

    assert client.patch("/api/items/WI-B", json={"status": "<script>"}).status_code == 422
    assert client.patch("/api/items/WI-missing", json={"status": "To do"}).status_code == 404
    assert work_path.read_text(encoding="utf-8") == original

    sample_root = tmp_path / "sample-root"
    sample_dir = sample_root / "contracts"
    sample_dir.mkdir(parents=True)
    sample_path = sample_dir / "work_items.sample.json"
    sample_body = json.dumps(
        [_item(id="WI-S", title="Sample task", priority=True, client_answer=None)]
    ) + "\n"
    sample_path.write_text(sample_body, encoding="utf-8")
    fallback = TestClient(create_app(sample_root))
    fallback_body = fallback.get("/api/board").json()
    assert fallback_body["source"] == "sample"
    assert fallback_body["items"][0]["id"] == "WI-S"
    assert fallback_body["client_name"] == "Northline"
    assert fallback_body["progress"] == {
        "answered": 0,
        "total": 1,
        "priority_gate_done": False,
    }
    assert fallback.patch("/api/items/WI-S", json={"status": "In progress"}).status_code == 200
    assert sample_path.read_text(encoding="utf-8") == sample_body
    stored = json.loads((sample_root / "data" / "out" / "overrides.json").read_text(encoding="utf-8"))
    assert stored["statuses"]["WI-S"] == "In progress"
    assert fallback.get("/api/board").json()["items"][0]["status"] == "In progress"
