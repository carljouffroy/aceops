"""Command line: build brd.md and work_items.json from checklist answers."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from internal.answers import load_json
from internal.brd import render_brd
from internal.dispatch import build_work_items
from internal.intake_client import IntakeAdminClient, IntakeAdminError
from internal.llm import polish_brd

ROOT = Path(__file__).resolve().parents[2]
POLL_SECONDS = 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="internal.run",
        description="Build a BRD and dispatch work items from checklist answers.",
    )
    parser.add_argument(
        "--answers",
        help="Offline answers JSON. Also the fallback when --live cannot reach the admin API.",
    )
    parser.add_argument("--live", action="store_true", help="Poll the intake admin API")
    parser.add_argument(
        "--bundle",
        default=str(ROOT / "contracts" / "bundle.json"),
        help="Path to the checklist bundle",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Directory for brd.md and work_items.json",
    )
    parser.add_argument(
        "--no-polish",
        action="store_true",
        help="Skip the optional wording polish",
    )
    parser.add_argument(
        "--max-polls",
        type=int,
        default=None,
        help="Stop the live loop after this many polls",
    )
    args = parser.parse_args(argv)
    try:
        bundle = load_json(Path(args.bundle))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"internal.run: {exc}", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else Path("data/out" if args.live else "out")
    if args.live:
        try:
            return run_live(
                bundle,
                out,
                polish=not args.no_polish,
                max_polls=args.max_polls,
            )
        except IntakeAdminError as exc:
            if args.answers and exc.unreachable:
                where = exc.url or "the admin API"
                print(f"mode: offline; admin API unreachable at {where}")
                return run_offline(bundle, Path(args.answers), out, polish=not args.no_polish)
            print(f"mode: live; {exc}", file=sys.stderr)
            return 1
    if not args.answers:
        print("internal.run: pass --answers or --live", file=sys.stderr)
        return 1
    print("mode: offline")
    return run_offline(bundle, Path(args.answers), out, polish=not args.no_polish)


def run_offline(bundle: dict, answers_path: Path, out: Path, *, polish: bool) -> int:
    try:
        answers = load_json(answers_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"internal.run: {exc}", file=sys.stderr)
        return 1
    brd_path, work_path = write_outputs(bundle, answers, out, polish=polish)
    print(f"brd.md: {brd_path}")
    print(f"work_items.json: {work_path}")
    return 0


def run_live(
    bundle: dict,
    out: Path,
    *,
    polish: bool,
    max_polls: int | None = None,
    client: IntakeAdminClient | None = None,
    sleep=time.sleep,
) -> int:
    admin = client or IntakeAdminClient.from_env()
    out.mkdir(parents=True, exist_ok=True)
    ensure_client(admin, out)
    print("mode: live")
    cursor = 0
    seen: dict[str, tuple] = {}
    polls = 0
    try:
        while True:
            events = admin.get_events(cursor)
            if events:
                cursor = max(int(event["id"]) for event in events)
            answer_events = [
                event for event in events if event.get("kind") == "answer_submitted"
            ]
            if polls == 0 or answer_events:
                changes = _apply_answers(seen, admin.get_answers())
                payload = {"answers": list(seen_answers(seen))}
                write_outputs(bundle, payload, out, polish=polish)
                for line in changes:
                    print(line)
            polls += 1
            if max_polls is not None and polls >= max_polls:
                return 0
            sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        return 0


def ensure_client(client: IntakeAdminClient, out: Path) -> str:
    path = out / "client.json"
    if path.is_file():
        saved = json.loads(path.read_text(encoding="utf-8"))
        client.client_id = str(saved["id"])
        try:
            client.get_events(0)
            return client.client_id
        except IntakeAdminError as exc:
            if "404" not in str(exc):
                raise
    created = client.create_client()
    path.write_text(json.dumps({"id": created["id"]}) + "\n", encoding="utf-8")
    return created["id"]


def write_outputs(bundle: dict, answers_payload, out: Path, *, polish: bool) -> tuple[Path, Path]:
    draft = render_brd(bundle, answers_payload)
    source_ids = [str(item["id"]) for item in bundle["items"]]
    brd = draft if not polish else polish_brd(draft, source_ids)
    work = build_work_items(bundle, answers_payload)
    out.mkdir(parents=True, exist_ok=True)
    brd_path = out / "brd.md"
    work_path = out / "work_items.json"
    brd_path.write_text(brd, encoding="utf-8")
    work_path.write_text(
        json.dumps(work, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return brd_path, work_path


def seen_answers(seen: dict[str, tuple]) -> list[dict]:
    return [entry[1] for entry in seen.values()]


def _apply_answers(seen: dict[str, tuple], latest: list[dict]) -> list[str]:
    """Record the latest answers. Return one printable line per change."""
    lines = []
    for answer in latest:
        item_id = str(answer.get("id") or "")
        if not item_id:
            continue
        signature = _signature(answer)
        previous = seen.get(item_id)
        if previous is not None and previous[0] == signature:
            continue
        corrected = previous is not None
        seen[item_id] = (signature, answer)
        lines.append(_change_line(answer, corrected=corrected))
    return lines


def _signature(answer: dict) -> tuple:
    return (
        answer.get("status"),
        answer.get("value"),
        answer.get("answered_by"),
        answer.get("client_ai_name"),
        answer.get("ts"),
    )


def _change_line(answer: dict, *, corrected: bool) -> str:
    item_id = answer.get("id") or "-"
    status = answer.get("status") or "-"
    who = answer.get("answered_by") or "-"
    name = answer.get("client_ai_name")
    if name:
        who = f"{who} name={name}"
    stamp = answer.get("ts") or "-"
    if corrected:
        text = f"{item_id} corrected {status} answered_by={who} ts={stamp}"
    else:
        text = f"{item_id} {status} answered_by={who} ts={stamp}"
    return " ".join(str(text).split())


if __name__ == "__main__":
    raise SystemExit(main())
