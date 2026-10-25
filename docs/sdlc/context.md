# SDLC lane: context

Branch `feat/sdlc`. Owner: Moorthy. Written 2026-10-25, 1:40 PM PT, from the ACE Ops updates
(12:15 STATUS, 12:57 SDLC brief) and the code on `integration` at `9b3098b` (13:11).

## What exists

The pipeline turns an advertiser's answers into assigned work, on the GB10 with local inference.

| Stage | Code | What it does |
|---|---|---|
| Intake | `src/intake/` | MCP server for the client's AI on `127.0.0.1:8787/mcp` (`get_next_item`, `submit_answer`, `get_progress`); admin API on `127.0.0.1:8788` (loopback only). Answers are append-only; `?history=true` returns every row. `client_agent.py` plays the client with a local model (`LLM_BASE_URL`, `LLM_MODEL`). |
| BRD | `src/internal/brd.py` | Writes `data/out/brd.md`: `# Business requirements`, `Client: …`, one `## <section title>` per BRD section with `- <answer> (<item id>) answered_by=… ts=…`, then `## Open gaps`. Optional wording polish through `INTERNAL_LLM_*`; falls back to the rules text. |
| Dispatch | `src/internal/dispatch.py` | One work item per checklist item, id `WI-<item id>`. Answered (DONE/PROVIDED) → `kind: task`, `status: To do`, title from `task_if_answered`. Otherwise → `kind: gap`, `status: Blocked`, `blocked_on_client: true`, title from `task_if_gap`. |
| Live mode | `src/internal/run.py --live` | Polls the intake admin API and rewrites `brd.md`, `work_items.json` and `progress.json` atomically (temp file + rename). |
| Board | `src/board/` | `127.0.0.1:8790`. Reads `data/out/work_items.json` (falls back to `contracts/work_items.sample.json`), `progress.json` and `brd.md`. Status edits (`PATCH /api/items/{id}`) go to `data/out/overrides.json`, never to `work_items.json`. |
| Demo | `scripts/run_demo.sh` | Starts intake, the board and the live client together. |

Contracts:

- `bundle.json`: 32 items, each with `id`, `section`, `priority`, `role`, `text`, `why`, `task_if_answered`, `task_if_gap`. Sections: P Commercial terms, A Access and permissions, R Profit model and constraints, O Objectives and key dates, F Tools, feed and tracking, D Data requirements, C Market and customer context, ST Stock and supply. Reply format `ID | STATUS | value` with STATUS DONE, PROVIDED or N/A.
- `work_items.schema.json`: an array of objects with `additionalProperties: false` and 14 required fields: `id`, `title`, `role`, `source_item_id`, `kind` (task, gap), `priority` (boolean), `status` (To do, In progress, Blocked, Done), `blocked_on_client`, `due`, `client_answer`, `answered_by`, `client_ai_name`, `ts`, `history`.
- `progress.schema.json`: totals, `priority_gate`, `by_role.{open, blocked}`.
- Samples: 30 work items for the fictional Northline Goods, 8 of them gaps (A2 Merchant Center access is the priority one).

## Where the SDLC plugs in

Today the pipeline stops at "a work item is on someone's plate". The SDLC carries the work through
to delivery and reports back:

```
Intake ─▶ BRD ─▶ Dispatch ─▶ Board                                    (exists)
                    │
                    ▼
                  Spec ─▶ Tickets ─▶ Build ─▶ Review ─▶ Release ─▶ Status   (this lane)
                                                                     │
                     open gaps go back to the client through Intake ◀┘
```

- **One spec per BRD section** with at least one `task` work item (spec ids are fixed by section
  order: SPEC-001 = P … SPEC-008 = ST). **One ticket per task work item**, plus dependencies from
  `contracts/sdlc/item_dependencies.json`. Gaps become the spec's `inputs_needed_from_client`.
- **Reads only:** `data/out/brd.md`, `data/out/work_items.json`, `data/out/overrides.json`, `contracts/bundle.json`.
- **Writes only:** `data/out/sdlc/` (`specs.json`, `tickets.json`, `status.json`, `drafts/`).
  Never `work_items.json` (live mode rewrites it) and never `overrides.json` (the board owns it).
- **Board:** a ticket minus its SDLC fields is a valid work item (checked), so the board can show
  tickets once it also reads `data/out/sdlc/tickets.json`. That one change is Tyler's call.
- **Runtime:** same local model endpoint as the internal agent (`INTERNAL_LLM_*`), rules-only fallback.

## Things I noticed that matter for the SDLC

1. `main` has only the scaffold and `bundle.json`; all contracts and code are on `integration`.
   `feat/sdlc` is cut from `main` as asked and adds new files only, so it can't conflict.
2. `contracts/CHANGELOG.md` exists only on `integration`; the SDLC entry is in
   `contracts/sdlc/CHANGELOG-entry.md` until `feat/sdlc` is rebased.
3. Nothing in code stops `INTERNAL_LLM_BASE_URL` from pointing at a cloud host; only
   `.env.example` comments say not to. The SDLC service will refuse non-loopback URLs, and the
   same three lines could go into `src/internal/llm.py` (proposal, Carl's call).
4. `pytest` collects only `tests/` (`testpaths`), so SDLC tests in `src/sdlc/tests/` need
   `pytest src/sdlc`, or a `tests/sdlc/` folder if Carl allows it.

## Still open

- Which runtime (NemoClaw / OpenClaw / OpenShell) and model are confirmed on the GB10 (Tyler).
- Whether the board reads `data/out/sdlc/tickets.json` today or SDLC stays a separate view.
