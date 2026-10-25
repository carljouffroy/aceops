# Merge plan: feat/sdlc

Goal: merge `feat/sdlc` after Carl and Tyler's parts are on `main`, with no risk to the demo
flow. Checked against `integration` at `9b3098b` (13:11). The lane only adds new files.

## Where the branches are (1:40 PM PT)

- `main` (`d0cd5de`, 11:50): scaffold + `contracts/bundle.json` only.
- `integration` (`9b3098b`, 13:11): intake + internal + board + demo script, 27 commits ahead of `main`.
- `feat/sdlc`: cut from `main` as asked. Adds `docs/sdlc/` and `contracts/sdlc/` only.

## Touchpoints

| # | Touchpoint | Owner | How SDLC uses it | Risk | Plan |
|---|---|---|---|---|---|
| 1 | `data/out/work_items.json` | Carl (`run.py --live`) | Reads | **High if written**: live mode replaces it atomically on every poll | SDLC never writes it; output goes to `data/out/sdlc/`. |
| 2 | `data/out/overrides.json` | Tyler (board `PATCH /api/items/{id}`) | Reads (people's status edits win for display) | Medium if written: the board rewrites it under a lock | SDLC never writes it. |
| 3 | `contracts/work_items.schema.json` | Carl | Tickets copy all 14 fields with the same types | Low: checked, a ticket minus SDLC fields validates | If the schema changes, re-run the SDLC compat check before merging. |
| 4 | `src/board/store.py` `load_board` | Tyler | Board reads only `work_items.json` (or the sample) | Medium: showing tickets needs a second input file | Proposal 1. A small change by Tyler, or skip for today; nothing breaks either way. |
| 5 | `data/out/brd.md` format (`src/internal/brd.py`) | Carl | `read_brd` parses `## <section title>` headings and `(<item id>)` markers | Low: a heading change breaks parsing | Match on `bundle.brd_sections` titles; a test runs on the real BRD output. |
| 6 | `contracts/bundle.json` | Carl | Reads `brd_sections`, `items[].section/role/task_if_*` | Low | Read-only. |
| 7 | `contracts/CHANGELOG.md` | everyone | Appends one section | **Add/add conflict** if created on `feat/sdlc` now: the file exists only on `integration` | Keep the entry in `contracts/sdlc/CHANGELOG-entry.md`; append it after rebasing on a `main` that has the file. |
| 8 | `.env.example` | shared | Adds `SDLC_MCP_PORT=8791`, `SDLC_ADMIN_PORT=8792`; reuses `INTERNAL_LLM_*` | Low | Only with the prototype; lines at the end under `# sdlc`. |
| 9 | `pyproject.toml` / `uv.lock` | Carl | No new dependencies: `fastapi`, `mcp`, `uvicorn` are there; `jsonschema` is already locked through `mcp` | Low | Don't touch either file. If `jsonschema` is used directly, ask Carl to list it explicitly on `main`. |
| 10 | `pytest` `testpaths = ["tests"]` | Carl | SDLC tests | Low: tests in `src/sdlc/tests/` aren't collected by plain `pytest` | Run `pytest src/sdlc`, or put tests in `tests/sdlc/` if Carl agrees (new folder, no conflict). |
| 11 | Ports | Tyler | `8791` MCP, `8792` admin | Low: `run_demo.sh` checks 8787, 8788, 8790 | Add the SDLC ports to the demo script only if the prototype runs in the demo. |
| 12 | `README.md` / writeup | Tyler | One SDLC paragraph + 3 pitch bullets | Low | Send text to Tyler; don't edit the writeup. |

## Merge order

1. **Carl and Tyler:** `integration` → `main`, with one full end-to-end run on the GB10.
2. **Moorthy:** `git rebase origin/main` on `feat/sdlc`, then append `CHANGELOG-entry.md` to
   `contracts/CHANGELOG.md` and delete the entry file.
3. **Merge A, docs and contracts only.** New files plus one CHANGELOG section: no runtime risk.
   Can go in right after the 3:30 review.
4. **Owners decide on the proposals** (board input file, loopback guard in `llm.py`, dependency pairs).
5. **Merge B, prototype** (`src/sdlc/` + tests), only if approved at 3:30, its tests pass on the
   GB10, and it lands by **5:00 PM**, 30 minutes before code lock.
6. Re-run the demo flow after each merge.

## Pre-merge checks (on `feat/sdlc`, after the rebase)

```bash
git diff --stat origin/main...HEAD
uv run pytest -q
uv run pytest src/sdlc -q
grep -rniE "api\.openai\.com|anthropic\.com|generativelanguage|api\.groq" docs/sdlc contracts/sdlc src/sdlc
```

The first command should list only `docs/sdlc/`, `contracts/sdlc/`, `src/sdlc/` and
`contracts/CHANGELOG.md`. The grep should find nothing. Check by hand that the diff has no real
client names; demo data uses Northline Goods only.

## Rollback

Everything is additive. Revert the merge commit, or delete `src/sdlc/` and stop the SDLC service.
Intake → BRD → dispatch → board doesn't read any SDLC file.
