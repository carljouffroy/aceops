"""Command line: build brd.md and work_items.json from checklist answers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from internal.answers import load_json
from internal.brd import render_brd
from internal.dispatch import build_work_items
from internal.llm import polish_brd

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="internal.run",
        description="Build a BRD and dispatch work items from checklist answers.",
    )
    parser.add_argument("--answers", required=True, help="Path to answers JSON")
    parser.add_argument(
        "--bundle",
        default=str(ROOT / "contracts" / "bundle.json"),
        help="Path to the checklist bundle",
    )
    parser.add_argument(
        "--out",
        default="out",
        help="Directory for brd.md and work_items.json",
    )
    parser.add_argument(
        "--no-polish",
        action="store_true",
        help="Skip the optional wording polish",
    )
    args = parser.parse_args(argv)
    try:
        bundle = load_json(Path(args.bundle))
        answers = load_json(Path(args.answers))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"internal.run: {exc}", file=sys.stderr)
        return 1

    draft = render_brd(bundle, answers)
    source_ids = [str(item["id"]) for item in bundle["items"]]
    brd = draft if args.no_polish else polish_brd(draft, source_ids)
    work = build_work_items(bundle, answers)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    brd_path = out / "brd.md"
    work_path = out / "work_items.json"
    brd_path.write_text(brd, encoding="utf-8")
    work_path.write_text(
        json.dumps(work, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"brd.md: {brd_path}")
    print(f"work_items.json: {work_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
