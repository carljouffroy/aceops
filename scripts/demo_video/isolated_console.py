#!/usr/bin/env python3
"""Run the SDLC console on a private copy of the Northline sample workspace.

`python -m sdlc --source sample` always reads and writes data/sample_out/sdlc, so
a second console (for example the one record_product.py starts on :8794) would
share state with a console a person is using on :8792: its /api/reset would wipe
their demo and its autopilot would make their process run agents. This launcher
copies the sample inputs (brd.md, progress.json, work_items.json) into a private
directory, points the "sample" source at that copy, and then runs the ordinary
sdlc entry point. src/ is untouched: config.SOURCES is a plain dict that every
module holds by reference, so one item assignment redirects all of them (the
project's own tests isolate workspaces the same way).

    PYTHONPATH=src uv run python scripts/demo_video/isolated_console.py \
        [--workspace DIR] [--fresh] -- --source sample --no-mcp

Everything after the launcher's own flags is passed to `python -m sdlc`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "src"
DEFAULT_WORKSPACE = HERE / "out" / "workspace" / "sample_out"
SAMPLE_INPUTS = ("brd.md", "progress.json", "work_items.json")

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sdlc import config  # noqa: E402  (after the sys.path fix)


def prepare_workspace(workspace: Path, fresh: bool) -> Path:
    workspace = workspace.resolve()
    if fresh and workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    shared = config.SOURCES["sample"]
    for name in SAMPLE_INPUTS:
        source = shared / name
        target = workspace / name
        if source.is_file() and not target.is_file():
            shutil.copy2(source, target)
    # Item assignment on the shared dict: store.py, api.py and sample.py all see it.
    config.SOURCES["sample"] = workspace
    return workspace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="isolated_console", description="sdlc console on a private sample workspace", add_help=True
    )
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="private copy of data/sample_out")
    parser.add_argument("--fresh", action="store_true", help="delete the private workspace first")
    args, passthrough = parser.parse_known_args(argv)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    workspace = prepare_workspace(Path(args.workspace), args.fresh)
    print(f"isolated_console: sample workspace {workspace}", flush=True)
    # If the shared sample was never generated, sdlc's ensure_sample() builds it into
    # the private directory (SOURCES["sample"] now points there).
    from sdlc.__main__ import main as sdlc_main

    return sdlc_main(passthrough or ["--source", "sample", "--no-mcp"])


if __name__ == "__main__":
    raise SystemExit(main())
