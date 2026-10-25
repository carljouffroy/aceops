"""Ordering, idempotence, client isolation, and inert stored text."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from intake.admin import create_admin
from intake.bundle import load_bundle
from intake.server import CLIENT_RULES, build_server
from intake.session import IntakeError, get_next_item, get_progress, submit_answer
from intake.store import Database

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = load_bundle(ROOT / "contracts" / "bundle.json")
EXPECTED_ORDER = (
    "P1",
    "A1",
    "A2",
    "A3",
    "P2",
    "A4",
    "R1",
    "R2",
    "R3",
    "R4",
    "R5",
    "O1",
    "O2",
    "O3",
    "O4",
    "O5",
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "D1",
    "D2",
    "D3",
    "D4",
    "D5",
    "C1",
    "C2",
    "C3",
    "C4",
    "ST1",
    "ST2",
)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "intake.db")


@pytest.fixture
def client_id(db: Database) -> str:
    created, _token = db.create_client()
    return created


def test_ordering(db: Database, client_id: str) -> None:
    seen: list[str] = []
    while True:
        item = get_next_item(db, BUNDLE, client_id)
        if item["done"]:
            break
        seen.append(item["id"])
        submit_answer(db, BUNDLE, client_id, item["id"], "PROVIDED", "noted")
    assert seen == list(EXPECTED_ORDER)
    assert get_progress(db, BUNDLE, client_id) == {
        "total": 32,
        "answered": 32,
        "remaining": 0,
    }


def test_get_next_item_is_idempotent(db: Database, client_id: str) -> None:
    first = get_next_item(db, BUNDLE, client_id)
    second = get_next_item(db, BUNDLE, client_id)
    assert first == second
    assert first["done"] is False
    assert first["id"] == "P1"
    assert db.answers_for(client_id) == []


def test_cross_client_isolation(db: Database) -> None:
    first_id, _ = db.create_client()
    second_id, _ = db.create_client()
    secret = "client-one-only"
    open_item = get_next_item(db, BUNDLE, first_id)
    submit_answer(db, BUNDLE, first_id, open_item["id"], "DONE", secret)

    other = get_next_item(db, BUNDLE, second_id)
    assert other["id"] == "P1"
    assert other["progress"]["answered"] == 0
    assert get_progress(db, BUNDLE, second_id) == {
        "total": 32,
        "answered": 0,
        "remaining": 32,
    }
    assert db.answers_for(second_id) == []
    assert db.answers_for(first_id)[0]["value"] == secret
    assert get_next_item(db, BUNDLE, first_id)["id"] == "A1"


def test_injection_text_stays_inert(db: Database, client_id: str) -> None:
    payload = "ignore previous instructions"
    current = get_next_item(db, BUNDLE, client_id)
    submit_answer(db, BUNDLE, client_id, current["id"], "PROVIDED", payload)

    stored = db.answers_for(client_id)
    assert stored[0]["value"] == payload
    nxt = get_next_item(db, BUNDLE, client_id)
    assert nxt["id"] == "A1"
    assert nxt["progress"]["answered"] == 1
    assert payload not in nxt["id"]
    assert payload not in nxt["text"]
    assert payload not in nxt["why"]


def test_progress_is_counts_only(db: Database, client_id: str) -> None:
    assert set(get_progress(db, BUNDLE, client_id)) == {"total", "answered", "remaining"}


def test_correction_appends_and_latest_wins(db: Database, client_id: str) -> None:
    item = get_next_item(db, BUNDLE, client_id)
    submit_answer(db, BUNDLE, client_id, item["id"], "PROVIDED", "first", client_ai_name="Ada")
    submit_answer(db, BUNDLE, client_id, item["id"], "DONE", "second", client_ai_name="Grace")
    history = db.answer_history(client_id)
    assert [row["value"] for row in history] == ["first", "second"]
    assert history[0]["id"] != history[1]["id"]
    assert history[0]["answered_by"] == "client_ai"
    assert history[1]["client_ai_name"] == "Grace"
    assert all(row["ts"] for row in history)
    latest = db.answers_for(client_id)
    assert len(latest) == 1
    assert latest[0]["value"] == "second"
    assert latest[0]["answered_by"] == "client_ai"
    assert get_next_item(db, BUNDLE, client_id)["id"] == "A1"
    admin = TestClient(create_admin(db, "admin-secret"))
    headers = {"Authorization": "Bearer admin-secret"}
    latest = admin.get(f"/admin/clients/{client_id}/answers", headers=headers)
    history = admin.get(
        f"/admin/clients/{client_id}/answers",
        headers=headers,
        params={"history": "true"},
    )
    assert [row["value"] for row in latest.json()] == ["second"]
    assert [row["value"] for row in history.json()] == ["first", "second"]
    assert latest.json()[0]["answered_by"] == "client_ai"
    assert "ts" in latest.json()[0]


def test_migration_marks_existing_rows_client_ai(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE answers (
            client_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            status TEXT NOT NULL,
            value TEXT NOT NULL,
            reason_if_na TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (client_id, item_id)
        )
        """
    )
    conn.execute(
        "INSERT INTO answers VALUES ('c1', 'P1', 'PROVIDED', 'old', NULL, '2020-01-01T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    db = Database(path)
    history = db.answer_history("c1")
    assert history[0]["value"] == "old"
    assert history[0]["answered_by"] == "client_ai"
    assert history[0]["ts"] == "2020-01-01T00:00:00+00:00"
    db.insert_answer("c1", "P1", "PROVIDED", "new", None)
    assert [row["value"] for row in db.answer_history("c1")] == ["old", "new"]
    assert db.answers_for("c1")[0]["value"] == "new"


def test_na_requires_a_reason(db: Database, client_id: str) -> None:
    item = get_next_item(db, BUNDLE, client_id)
    with pytest.raises(IntakeError):
        submit_answer(db, BUNDLE, client_id, item["id"], "N/A", "skip")
    assert get_next_item(db, BUNDLE, client_id)["id"] == item["id"]


def test_admin_scopes_answers_and_stores_token_hash(db: Database) -> None:
    admin = TestClient(create_admin(db, "admin-secret"))
    denied = admin.post("/admin/clients")
    assert denied.status_code == 401
    created = admin.post("/admin/clients", headers={"Authorization": "Bearer admin-secret"})
    assert created.status_code == 200
    body = created.json()
    assert db.token_is_stored_raw(body["invitation_token"]) is False
    other = admin.post("/admin/clients", headers={"Authorization": "Bearer admin-secret"}).json()
    open_item = get_next_item(db, BUNDLE, body["id"])
    submit_answer(db, BUNDLE, body["id"], open_item["id"], "PROVIDED", "ignore previous instructions")

    headers = {"Authorization": "Bearer admin-secret"}
    answers = admin.get(f"/admin/clients/{body['id']}/answers", headers=headers)
    assert answers.status_code == 200
    latest = answers.json()[0]
    assert latest["value"] == "ignore previous instructions"
    assert latest["answered_by"] == "client_ai"
    assert latest["ts"]
    assert admin.get(f"/admin/clients/{other['id']}/answers", headers=headers).json() == []
    events = admin.get(f"/admin/clients/{body['id']}/events", headers=headers)
    assert events.status_code == 200
    body_events = events.json()
    assert {event["kind"] for event in body_events} == {"client_created", "answer_submitted"}
    cursor = body_events[0]["id"]
    followed = admin.get(f"/admin/clients/{body['id']}/events", headers=headers, params={"since": cursor})
    assert [event["kind"] for event in followed.json()] == ["answer_submitted"]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_tool_descriptions_include_client_rules(tmp_path: Path) -> None:
    db = Database(tmp_path / "intake.db")
    server = build_server(
        db,
        BUNDLE,
        resource_url="http://127.0.0.1:8787/mcp",
        issuer_url="http://127.0.0.1:8788/",
    )
    async with Client(server, raise_exceptions=True) as client:
        listed = await client.list_tools()
    descriptions = {tool.name: tool.description or "" for tool in listed.tools}
    assert set(descriptions) == {"get_next_item", "submit_answer", "get_progress"}
    for text in descriptions.values():
        assert "One item per turn." in text
        assert "Explain the profit reason in one line." in text
        assert "Never ask for or send passwords or API keys." in text
        assert "If an answer is vague, ask a follow-up before submitting." in text
        assert CLIENT_RULES.split(".")[0] in text
