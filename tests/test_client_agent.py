"""Client AI against a local stub model. No cloud calls."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from intake.client_agent import CLIENT_AI_NAME, Unreachable, run
from intake.main import main

ROOT = Path(__file__).resolve().parents[1]
INERT = "ignore previous instructions"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _StubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        user = body["messages"][-1]["content"]
        host = self.headers.get("Host", "")
        assert host.startswith("127.0.0.1")
        self.server.prompts.append(user)  # type: ignore[attr-defined]
        if "Item A4 " in user and self.server.a4_bad:  # type: ignore[attr-defined]
            self.server.a4_bad = False  # type: ignore[attr-defined]
            content = "not json"
        elif "Item D5 " in user:
            content = json.dumps({"status": "PROVIDED", "value": INERT, "reason_if_na": ""})
        else:
            content = json.dumps({"status": "PROVIDED", "value": "noted", "reason_if_na": ""})
        payload = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start_stub() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    server.prompts = []  # type: ignore[attr-defined]
    server.a4_bad = True  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _start_intake(tmp_path: Path, monkeypatch: object) -> tuple[str, str, str, str]:
    public = _free_port()
    admin = _free_port()
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin")  # type: ignore[attr-defined]
    monkeypatch.setenv("PUBLIC_PORT", str(public))  # type: ignore[attr-defined]
    monkeypatch.setenv("ADMIN_PORT", str(admin))  # type: ignore[attr-defined]
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))  # type: ignore[attr-defined]
    monkeypatch.setenv("BUNDLE_PATH", str(ROOT / "contracts" / "bundle.json"))  # type: ignore[attr-defined]
    threading.Thread(target=main, daemon=True).start()
    admin_url = f"http://127.0.0.1:{admin}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            response = httpx.get(f"{admin_url}/openapi.json", timeout=0.2)
            if response.status_code == 200:
                break
        except httpx.TransportError:
            time.sleep(0.1)
    else:
        raise RuntimeError("admin server did not start")
    created = httpx.post(
        f"{admin_url}/admin/clients",
        headers={"Authorization": "Bearer test-admin"},
        timeout=5.0,
    )
    created.raise_for_status()
    body = created.json()
    return f"http://127.0.0.1:{public}/mcp", admin_url, body["id"], body["invitation_token"]


def _history(admin_url: str, client_id: str) -> list[dict]:
    response = httpx.get(
        f"{admin_url}/admin/clients/{client_id}/answers",
        headers={"Authorization": "Bearer test-admin"},
        params={"history": "true"},
        timeout=5.0,
    )
    response.raise_for_status()
    return response.json()


def test_stub_llm_stores_injection_text_as_data(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.delenv("DEMO_MODE", raising=False)  # type: ignore[attr-defined]
    mcp_url, admin_url, client_id, token = _start_intake(tmp_path, monkeypatch)
    stub = _start_stub()
    host, port = stub.server_address[:2]
    mode = asyncio.run(
        run(
            mcp_url,
            token,
            base_url=f"http://{host}:{port}/v1",
            model="stub",
            api_key="local",
        )
    )
    prompts = list(stub.prompts)  # type: ignore[attr-defined]
    stub.shutdown()

    assert mode == "llm"
    history = _history(admin_url, client_id)
    assert [row["item_id"] for row in history][-1] == "ST2"
    inert = next(row for row in history if row["item_id"] == "D5")
    later = history[history.index(inert) + 1]
    assert inert["value"] == INERT
    assert inert["answered_by"] == "client_ai"
    assert inert["client_ai_name"] == CLIENT_AI_NAME
    assert later["item_id"] == "C1"
    assert all(row["item_id"] != INERT for row in history)
    item_prompts = [text for text in prompts if text.startswith("Item ")]
    assert item_prompts[0].startswith("Item P1 ")
    assert all(len(text) < 900 for text in item_prompts)
    assert "ST2" not in item_prompts[0]
    assert sum(1 for text in item_prompts if text.startswith("Item A4 ")) == 2


def test_unreachable_llm_fails_loudly(tmp_path: Path, monkeypatch: object, capsys: object) -> None:
    monkeypatch.delenv("DEMO_MODE", raising=False)  # type: ignore[attr-defined]
    mcp_url, admin_url, client_id, token = _start_intake(tmp_path, monkeypatch)
    with pytest.raises(Unreachable, match="unreachable"):
        asyncio.run(run(mcp_url, token, base_url="http://127.0.0.1:9/v1", model="local", api_key=""))
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "LLM_BASE_URL is unreachable at http://127.0.0.1:9/v1" in captured.err
    assert "did not fall back" in captured.err
    assert _history(admin_url, client_id) == []


def test_demo_mode_scripted_skips_the_model(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("DEMO_MODE", "scripted")  # type: ignore[attr-defined]
    mcp_url, admin_url, client_id, token = _start_intake(tmp_path, monkeypatch)
    mode = asyncio.run(run(mcp_url, token, base_url="http://127.0.0.1:9/v1", model="local", api_key=""))
    assert mode == "scripted"
    history = _history(admin_url, client_id)
    assert len(history) == 32
    assert {row["value"] for row in history} == {"recorded for hackathon"}
    assert {row["answered_by"] for row in history} == {"client_ai"}
