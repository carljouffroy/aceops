"""Promotion effectiveness from a client's sales export.

For every product, region and customer segment: units per order with a promotion
against units per order without one. The lift, the number of orders behind it, how
much of the product's volume already runs on promotion, and (when the file has it)
profit per order under each condition. Pure rules, pure Python, no model: the
numbers must be reproducible from the file, and every figure the report uses is
kept in `figures` so the review pre-check can trace them.

Datasets live in contracts/sdlc/datasets/ (committed, with a licence note) or
data/clients/ (not committed). Each CSV has a <name>.profile.json mapping columns.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from sdlc.config import CONTRACTS, ROOT
from sdlc.store import now_iso

DATASET_DIRS = (CONTRACTS / "sdlc" / "datasets", ROOT / "data" / "clients")
MAX_LIST = 8
_CACHE: dict[str, tuple[float, dict]] = {}


def _profile_for(csv_path: Path) -> dict:
    profile_path = csv_path.with_suffix(".profile.json")
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def list_datasets() -> list[Path]:
    out = []
    for folder in DATASET_DIRS:
        if folder.is_dir():
            out += sorted(p for p in folder.glob("*.csv") if p.is_file())
    return out


def dataset_path(name: str) -> Path | None:
    for path in list_datasets():
        if path.stem == name:
            return path
    return None


def _to_float(value) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _is_promo(value, rule: dict) -> bool:
    kind = (rule or {}).get("kind", "truthy")
    number = _to_float(value)
    if kind == "greater_than":
        return number is not None and number > float(rule.get("value", 0))
    if kind == "equals":
        return str(value).strip().lower() == str(rule.get("value")).strip().lower()
    return str(value).strip().lower() in ("1", "true", "yes", "y", "promo", "promotion")


def _stats(rows: list[dict]) -> dict:
    promo = [r for r in rows if r["promo"]]
    base = [r for r in rows if not r["promo"]]
    units_promo = sum(r["units"] for r in promo) / len(promo) if promo else None
    units_base = sum(r["units"] for r in base) / len(base) if base else None
    lift = (units_promo - units_base) / units_base if units_promo is not None and units_base else None
    profit_promo = sum(r["profit"] for r in promo if r["profit"] is not None) / len(promo) if promo and any(r["profit"] is not None for r in promo) else None
    profit_base = sum(r["profit"] for r in base if r["profit"] is not None) / len(base) if base and any(r["profit"] is not None for r in base) else None
    return {
        "orders": len(rows),
        "units": int(sum(r["units"] for r in rows)),
        "n_promo": len(promo),
        "n_base": len(base),
        "promo_share": round(len(promo) / len(rows), 3) if rows else 0.0,
        "units_promo": round(units_promo, 2) if units_promo is not None else None,
        "units_base": round(units_base, 2) if units_base is not None else None,
        "lift": round(lift, 3) if lift is not None else None,
        "profit_promo": round(profit_promo, 2) if profit_promo is not None else None,
        "profit_base": round(profit_base, 2) if profit_base is not None else None,
    }


def analyze(csv_path: Path) -> dict:
    """Full analysis of one dataset, cached by file modification time."""
    key = str(csv_path)
    mtime = csv_path.stat().st_mtime
    cached = _CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    profile = _profile_for(csv_path)
    fields = profile.get("fields", {})
    rule = profile.get("promo_rule", {"kind": "truthy"})
    min_orders = int(profile.get("min_orders", 4))
    threshold = float(profile.get("lift_threshold", 0.15))
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8", errors="ignore", newline="") as handle:
        for raw in csv.DictReader(handle):
            units = _to_float(raw.get(fields.get("units", ""), ""))
            product = (raw.get(fields.get("product", ""), "") or "").strip()
            if units is None or not product:
                continue
            rows.append(
                {
                    "product": product,
                    "category": (raw.get(fields.get("category", ""), "") or "").strip() or None,
                    "region": (raw.get(fields.get("region", ""), "") or "").strip() or None,
                    "segment": (raw.get(fields.get("segment", ""), "") or "").strip() or None,
                    "units": units,
                    "promo": _is_promo(raw.get(fields.get("promo", ""), ""), rule),
                    "profit": _to_float(raw.get(fields.get("profit", ""), "")) if fields.get("profit") else None,
                }
            )
    by_product: dict[str, list[dict]] = defaultdict(list)
    by_region: dict[str, list[dict]] = defaultdict(list)
    by_segment: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_product[r["product"]].append(r)
        if r["region"]:
            by_region[r["region"]].append(r)
        if r["segment"]:
            by_segment[r["segment"]].append(r)

    products = []
    for name, prows in by_product.items():
        s = _stats(prows)
        if s["n_promo"] < min_orders or s["n_base"] < min_orders or s["lift"] is None:
            continue
        regions = sorted({r["region"] for r in prows if r["region"] and r["promo"]})
        segments = sorted({r["segment"] for r in prows if r["segment"]})
        score = s["lift"] * math.log(1 + s["n_promo"] + s["n_base"])
        products.append({"product": name, "category": next((r["category"] for r in prows if r["category"]), None), "regions": regions, "segments": segments, "score": round(score, 3), **s})
    promote = sorted((p for p in products if p["lift"] >= threshold and p["promo_share"] < 0.6 and (p["profit_promo"] is None or p["profit_promo"] >= 0)), key=lambda p: -p["score"])[:MAX_LIST]
    stop = sorted((p for p in products if p["lift"] <= -threshold or (p["profit_promo"] is not None and p["profit_base"] is not None and p["profit_promo"] < 0 <= p["profit_base"] and p["n_promo"] >= min_orders)), key=lambda p: p["score"])[:MAX_LIST]
    for p in stop:
        p["reason"] = "units fall under promotion" if p["lift"] <= -threshold else "promotion turns the order unprofitable"
    overall = {**_stats(rows), "products": len(by_product), "products_with_evidence": len(products)}
    result = {
        "name": csv_path.stem,
        "title": profile.get("title") or csv_path.stem,
        "source": profile.get("source", {}),
        "path": str(csv_path.relative_to(ROOT)) if csv_path.is_relative_to(ROOT) else str(csv_path),
        "fields": fields,
        "rows": len(rows),
        "overall": overall,
        "by_region": [{"key": k, **_stats(v)} for k, v in sorted(by_region.items())],
        "by_segment": [{"key": k, **_stats(v)} for k, v in sorted(by_segment.items())],
        "promote": promote,
        "stop": stop,
        "method": (
            f"Lift = units per order with a promotion ÷ units per order without, minus 1, per product; a product needs at least {min_orders} promoted and {min_orders} unpromoted orders to count. "
            f"'Promote' = lift ≥ {int(threshold * 100)}% with promo coverage under 60% and a non-negative profit per promoted order. "
            f"'Stop' = lift ≤ −{int(threshold * 100)}%, or a promotion that turns a profitable product unprofitable. Promotion signal: {fields.get('promo')} {rule.get('kind', 'truthy')} {rule.get('value', '')}."
        ).strip(),
        "generated_at": now_iso(),
    }
    result["figures"] = _figures(result)
    _CACHE[key] = (mtime, result)
    return result


def _figures(result: dict) -> list[float]:
    """Every number the reports may quote, so the trace check can accept them."""
    out: set[float] = set()

    def grab(stats: dict) -> None:
        for k in ("orders", "units", "n_promo", "n_base", "units_promo", "units_base", "profit_promo", "profit_base"):
            v = stats.get(k)
            if isinstance(v, (int, float)):
                out.add(round(float(v), 4))
        for k in ("lift", "promo_share"):
            v = stats.get(k)
            if isinstance(v, (int, float)):
                out.add(round(float(v), 4))
                out.add(float(round(v * 100)))
                out.add(round(v * 100, 1))

    grab(result["overall"])
    out.add(float(result["rows"]))
    out.add(float(result["overall"]["products"]))
    for group in ("by_region", "by_segment", "promote", "stop"):
        for item in result[group]:
            grab(item)
    return sorted(out)


def summaries(state: dict) -> list[dict]:
    """What the console and MCP show: the analysis of each dataset, plus the spec drafted from it."""
    out = []
    specs = {s.get("analysis", {}).get("dataset"): s["id"] for s in state.get("specs", []) if s.get("analysis")}
    for path in list_datasets():
        try:
            a = analyze(path)
        except Exception as exc:  # a bad file is reported, never fatal
            out.append({"name": path.stem, "title": path.stem, "rows": 0, "error": f"{type(exc).__name__}: {exc}", "overall": {}, "promote": [], "stop": [], "by_region": [], "by_segment": [], "fields": {}})
            continue
        out.append({**{k: a[k] for k in ("name", "title", "source", "path", "fields", "rows", "overall", "by_region", "by_segment", "promote", "stop", "method")}, "spec_id": specs.get(path.stem)})
    return out


# ---- specs and tickets from an analysis ----

ANALYSIS_SPEC_BASE = 100


def next_spec_id(state: dict) -> str:
    taken = {s["id"] for s in state["specs"]}
    n = ANALYSIS_SPEC_BASE + 1
    while f"SPEC-{n:03d}" in taken:
        n += 1
    return f"SPEC-{n:03d}"


def build_spec(state: dict, result: dict, client: str, now: str) -> dict:
    promote, stop = result["promote"], result["stop"]
    scope = [f"Run a promotion on {p['product']}" + (f" in {', '.join(p['regions'])}" if p["regions"] else "") for p in promote[:5]]
    scope += [f"Review the promotion on {p['product']} ({p['reason']})" for p in stop[:3]]
    needs = []
    criteria = [
        {"id": "AC1", "text": "Every number in the deliverable traces to the client's sales export or is marked as derived.", "verified_by": "agent_check"},
        {"id": "AC2", "text": "Each recommended promotion names the product, where it worked, the lift and the orders behind it.", "verified_by": "human_review"},
        {"id": "AC3", "text": "No promotion is recommended where profit per promoted order is negative.", "verified_by": "agent_check"},
        {"id": "AC4", "text": "The client confirms budget and timing for each promotion before it runs.", "verified_by": "client_confirmation"},
    ]
    return {
        "id": next_spec_id(state),
        "version": 1,
        "client": client,
        "title": f"Promotion effectiveness · {result['title']}",
        "role": "Marketing Specialist",
        "stage": "spec",
        "status": "draft",
        "brd_sections": [],
        "goal": f"Put promotions where they sell more units and stop the ones that lose money, from the client's own {result['rows']:,} order lines.",
        "scope": scope or ["No product cleared the evidence bar; review the dataset profile."],
        "out_of_scope": ["Changing prices outside promotions", "New product listings"],
        "acceptance_criteria": criteria,
        "inputs_needed_from_client": needs,
        "source_item_ids": [f"DS:{result['name']}"],
        "source_work_item_ids": [],
        "depends_on": [],
        "risks": [f"Lift is measured on units per order; a promotion can raise units and still lose money (profit guard applied where the file has profit)."],
        "client_signoff_required": True,
        "approval": None,
        "rejection": None,
        "analysis": {
            "dataset": result["name"],
            "path": result["path"],
            "rows": result["rows"],
            "generated_at": now,
            "promote": promote[:5],
            "stop": stop[:3],
            "overall": result["overall"],
            "figures": result["figures"],
        },
        "provenance": {"generated_by": "rules", "model": None, "generated_at": now, "inputs": [result["path"]]},
    }


def split_spec(spec: dict, now: str) -> list[dict]:
    a = spec["analysis"]
    items = [("promote", p) for p in a["promote"]] + [("stop", p) for p in a["stop"]]
    tickets = []
    for n, (kind, p) in enumerate(items, 1):
        if kind == "promote":
            title = f"Run a promotion on {p['product']}" + (f" in {', '.join(p['regions'])}" if p["regions"] else "")
            role = "Marketing Specialist"
            evidence = f"{p['units_promo']} units/order with promotion vs {p['units_base']} without ({p['n_promo']} vs {p['n_base']} orders); lift {round(p['lift'] * 100)}%; promo share {round(p['promo_share'] * 100)}%."
        else:
            title = f"Review the promotion on {p['product']}: {p['reason']}"
            role = "Data Analyst"
            evidence = f"{p['units_promo']} units/order with promotion vs {p['units_base']} without ({p['n_promo']} vs {p['n_base']} orders); lift {round(p['lift'] * 100)}%; profit/order {p['profit_promo']} vs {p['profit_base']}."
        criteria = [{**c, "result": None, "note": None} for c in spec["acceptance_criteria"] if c["id"] != "AC4" or kind == "promote"]
        tickets.append(
            {
                "id": f"{spec['id']}-T{n:02d}",
                "title": title,
                "role": role,
                "source_item_id": f"DS:{a['dataset']}",
                "kind": "task",
                "priority": n == 1,
                "status": "To do",
                "blocked_on_client": False,
                "due": None,
                "client_answer": evidence,
                "answered_by": "client sales export",
                "client_ai_name": None,
                "ts": a["generated_at"],
                "history": [],
                "spec_id": spec["id"],
                "spec_version": spec["version"],
                "source_work_item_id": f"WI-DS-{a['dataset']}",
                "stage": "tickets",
                "assignee": None,
                "acceptance_criteria": criteria,
                "depends_on": [],
                "waiting_on": [],
                "evidence": [],
                "agent_draft": None,
                "review": None,
                "release": None,
                "analysis": {**p, "kind": kind, "dataset": a["dataset"], "figures": a["figures"]},
                "provenance": {"generated_by": "rules", "model": None, "generated_at": now, "inputs": [a["path"], "data/out/sdlc/specs.json"]},
            }
        )
    return tickets


def draft_ticket(ticket: dict, spec: dict | None) -> str:
    p = ticket["analysis"]
    kind = p["kind"]
    lines = [
        f"# {ticket['title']}",
        "",
        f"{ticket['id']} · {ticket['role']} · {spec['title'] if spec else ticket['spec_id']} · source: the client's sales export ({p['dataset']})",
        "",
        "## Why this matters",
        "",
        "Promotions cost margin. This one is worth running only where it sells more units per order without turning the order unprofitable." if kind == "promote" else "A promotion that sells fewer units, or loses money per order, is a cost with no return.",
        "",
        "## What the client told us",
        "",
        f"> {ticket['client_answer']}",
        "",
        "## Working draft",
        "",
        f"Product: {p['product']}" + (f" · {p['category']}" if p.get("category") else ""),
        "",
        "| Condition | Orders | Units per order | Profit per order |",
        "|---|---|---|---|",
        f"| With promotion | {p['n_promo']} | {p['units_promo']} | {p['profit_promo'] if p['profit_promo'] is not None else 'n/a'} |",
        f"| Without promotion | {p['n_base']} | {p['units_base']} | {p['profit_base'] if p['profit_base'] is not None else 'n/a'} |",
        "",
        f"Lift in units per order: {round(p['lift'] * 100)}%. Share of this product's orders already on promotion: {round(p['promo_share'] * 100)}%.",
    ]
    if p.get("regions"):
        lines.append(f"Regions where the promotion ran: {', '.join(p['regions'])}.")
    if p.get("segments"):
        lines.append(f"Customer segments buying it: {', '.join(p['segments'])}.")
    lines += ["", "## Recommendation", ""]
    if kind == "promote":
        lines.append(f"Run the promotion on {p['product']}" + (f" in {', '.join(p['regions'])}" if p["regions"] else "") + ", with the client's budget and dates confirmed first (AC4).")
    else:
        lines.append(f"Pause the promotion on {p['product']} and re-test with a smaller discount; {p['reason']}.")
    lines += ["", "## Steps", "", "1. Confirm the figures above against the client's export (they are computed from it, not estimated).", "2. Agree the promotion window and depth with the client." if kind == "promote" else "2. Check the last three promotion windows for this product with the client.", "3. Write the campaign change as a one-page brief for the client's sign-off.", "", "## Acceptance criteria", ""]
    lines += [f"- [ ] {c['id']}: {c['text']}" for c in ticket["acceptance_criteria"]]
    lines += ["", "_Drafted on this machine by the ACE Ops Analyst agent from the client's sales export. Nothing here was sent anywhere._", ""]
    return "\n".join(lines)
