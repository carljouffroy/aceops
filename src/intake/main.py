"""Run the public MCP server and the loopback admin API."""

from __future__ import annotations

import threading

import uvicorn

from intake.admin import create_admin
from intake.bundle import load_bundle
from intake.config import load_settings
from intake.server import build_server
from intake.store import Database


def main() -> None:
    settings = load_settings()
    bundle = load_bundle(settings.bundle_path)
    db = Database(settings.db_path)
    mcp = build_server(
        db,
        bundle,
        resource_url=settings.resource_url,
        issuer_url=settings.issuer_url,
    )
    admin = create_admin(db, settings.admin_token)

    def serve_admin() -> None:
        uvicorn.run(admin, host="127.0.0.1", port=settings.admin_port, log_level="info")

    threading.Thread(target=serve_admin, name="intake-admin", daemon=True).start()
    mcp.run(
        transport="streamable-http",
        host=settings.public_host,
        port=settings.public_port,
        json_response=True,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
