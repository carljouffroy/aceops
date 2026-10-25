"""Create one client and answer every checklist item."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from intake.config import load_dotenv  # noqa: E402


async def run(admin_url: str, mcp_url: str, admin_token: str) -> None:
    async with httpx.AsyncClient(timeout=30.0) as http:
        created = await http.post(
            f"{admin_url.rstrip('/')}/admin/clients",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        created.raise_for_status()
        body = created.json()
    invitation = body["invitation_token"]
    client_id = body["id"]
    print(f"client {client_id}")

    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {invitation}"},
        timeout=httpx2.Timeout(30.0, read=300.0),
    ) as http_client:
        transport = streamable_http_client(mcp_url, http_client=http_client)
        async with Client(transport) as client:
            while True:
                result = await client.call_tool("get_next_item", {})
                if result.is_error:
                    raise SystemExit(_text(result))
                payload = result.structured_content or {}
                if payload.get("done") is True:
                    print(f"done {payload.get('progress')}")
                    return
                item_id = payload["id"]
                print(f"{item_id} {payload.get('progress')}")
                saved = await client.call_tool(
                    "submit_answer",
                    {
                        "item_id": item_id,
                        "status": "PROVIDED",
                        "value": "recorded for hackathon",
                    },
                )
                if saved.is_error:
                    raise SystemExit(_text(saved))


def _text(result: object) -> str:
    content = getattr(result, "content", ()) or ()
    parts = [getattr(block, "text", "") for block in content]
    return " ".join(part for part in parts if part) or "tool call failed"


def main() -> None:
    load_dotenv(Path(".env"))
    parser = argparse.ArgumentParser(description="Finish one ACE Ops intake as a fake client.")
    parser.add_argument("--admin-url", default=os.environ.get("ADMIN_URL", "http://127.0.0.1:8788"))
    parser.add_argument("--mcp-url", default=os.environ.get("MCP_URL", "http://127.0.0.1:8787/mcp"))
    args = parser.parse_args()
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if not admin_token:
        raise SystemExit("ADMIN_TOKEN is required")
    asyncio.run(run(args.admin_url, args.mcp_url, admin_token))


if __name__ == "__main__":
    main()
