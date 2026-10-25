"""Run one stage agent once, in this process, and print its outcome as JSON.

    python -m sdlc.agents <agent key> <workspace input dir> <subject>

The orchestrator starts this as a separate process for every run, so the agent
begins with nothing but the files its stage declares.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 3:
        print(json.dumps({"ok": False, "action": "error", "detail": "usage: sdlc.agents <agent> <input_dir> <subject>"}))
        return 2
    key, input_dir, subject = argv
    from sdlc.agents.stages import AGENTS
    from sdlc.config import load_dotenv
    from sdlc.gates import GateError
    from sdlc.store import Workspace

    load_dotenv()
    cls = AGENTS.get(key)
    if cls is None:
        print(json.dumps({"ok": False, "action": "error", "detail": f"unknown agent {key}"}))
        return 2
    ws = Workspace(Path(input_dir))
    try:
        ctx = cls.context(ws, subject)
        outcome = cls().run(ctx, ws)
        payload = {**outcome.as_dict(), "inputs": sorted(ctx.inputs), "pid": ctx.pid}
    except GateError as exc:
        payload = {"ok": False, "action": "refused", "detail": f"{exc.status}: {exc.message}"}
    except Exception as exc:  # the parent records the failure; the next tick retries
        payload = {"ok": False, "action": "error", "detail": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
