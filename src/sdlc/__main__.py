"""Run the SDLC agent: console + admin API, the always-on sync loop, and the MCP server.

uv run python -m sdlc                    # live pipeline output (data/out)
uv run python -m sdlc --source sample    # Northline sample answers (data/sample_out)
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

import uvicorn

from sdlc import engine
from sdlc.api import Console, create_app
from sdlc.config import LocalOnlyError, console_port, load_dotenv, mcp_port, model_settings
from sdlc.mcp_server import build_server
from sdlc.sample import ensure_sample

SYNC_EVERY_S = 3.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sdlc", description="ACE Ops SDLC agent and console")
    parser.add_argument("--source", choices=("live", "sample"), default="live")
    parser.add_argument("--no-mcp", action="store_true", help="Don't start the agent MCP server")
    args = parser.parse_args(argv)

    load_dotenv()
    try:
        settings = model_settings()
    except LocalOnlyError as exc:
        print(f"sdlc: {exc}", file=sys.stderr)
        return 2
    ensure_sample()
    console = Console(args.source)
    print(f"sdlc: model {'rules only' if settings is None else settings.model + ' at ' + settings.base_url}", flush=True)
    print(f"sdlc: console http://127.0.0.1:{console_port()}  source {args.source}", flush=True)

    def loop() -> None:
        while True:
            try:
                engine.sync(console.workspace())
            except Exception as exc:  # keep the always-on loop alive; the next tick retries
                print(f"sdlc: sync failed: {exc}", file=sys.stderr, flush=True)
            time.sleep(SYNC_EVERY_S)

    threading.Thread(target=loop, name="sdlc-loop", daemon=True).start()

    app = create_app(console)
    if args.no_mcp:
        uvicorn.run(app, host="127.0.0.1", port=console_port(), log_level="warning")
        return 0

    def serve_console() -> None:
        uvicorn.run(app, host="127.0.0.1", port=console_port(), log_level="warning")

    threading.Thread(target=serve_console, name="sdlc-console", daemon=True).start()
    print(f"sdlc: agent MCP http://127.0.0.1:{mcp_port()}/mcp", flush=True)
    build_server(console.workspace).run(
        transport="streamable-http",
        host="127.0.0.1",
        port=mcp_port(),
        json_response=True,
        stateless_http=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
