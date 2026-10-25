# SDLC contracts (draft)

Drafted 2026-10-25 for the 3:30 PM PT review, against `contracts/` on `integration` (`9b3098b`).
Nothing here changes an existing contract; changes needed elsewhere are proposed in
`CHANGELOG-entry.md`.

| File | Describes | Live file |
|---|---|---|
| `spec.schema.json` | One deliverable per BRD section, gate G1 | `data/out/sdlc/specs.json` (array) |
| `ticket.schema.json` | A ticket: all 14 `work_items` fields with the same types, plus SDLC fields; gates G2 to G4 | `data/out/sdlc/tickets.json` (array) |
| `status_report.schema.json` | Status rollup for one client, gate G5 | `data/out/sdlc/status.json` (object) |
| `item_dependencies.json` | Which checklist items' work must finish before another's starts (draft, for Carl to review) | — |
| `*.sample.json` | Built from the real Northline Goods `work_items.sample.json` and `bundle.json` | — |

The SDLC code reads `data/out/brd.md`, `data/out/work_items.json`, `data/out/overrides.json` and
`contracts/bundle.json`. It writes only under `data/out/sdlc/`.

## Tickets on the existing board

A ticket keeps all 14 `work_items` fields with the same types and enums, copied from its source
work item (`source_item_id`, `priority`, `client_answer`, `answered_by`, `client_ai_name`, `ts`,
`history`, …). **A ticket minus its SDLC fields validates against `work_items.schema.json`**; the
full ticket doesn't, because that schema sets `additionalProperties: false`. That's fine: the board
normalises rows rather than validating them.

SDLC fields: `spec_id`, `spec_version`, `source_work_item_id`, `stage`, `assignee`,
`acceptance_criteria` (each with the pre-check `result` and `note`), `depends_on`, `waiting_on`
(why the ticket can't enter build yet, rebuilt on every sync), `evidence`, `agent_draft`, `review`,
`release`, `provenance`. Specs carry `client_signoff_required`, set when the section's work touches
the client's ad account, feed or store; gate G4 then needs the client's sign-off.

`stage` is the SDLC position; `status` uses the board's enum and is derived from it:

| `stage` | `status` (when `blocked_on_client` is false) |
|---|---|
| `tickets` (not yet accepted) | `To do` |
| `build` | `In progress` |
| `review` | `In progress` |
| `release` (approved, waiting for go) | `In progress` |
| `done` | `Done` |

If `blocked_on_client` is true, `status` is `Blocked`, as dispatch does. A ticket waiting only on
another ticket stays `To do`; the reason shows in the status report's `blocked` list.

`kind` is `task` for tickets. Gaps stay with dispatch and appear on the spec as
`inputs_needed_from_client`.

## How specs and tickets are derived (rules first)

- One spec per BRD section that has at least one `task` work item. Ids follow `bundle.brd_sections`
  order: SPEC-001 P, 002 A, 003 R, 004 O, 005 F, 006 D, 007 C, 008 ST. Lead `role` is the most common
  role among the section's work items.
- One ticket per `task` work item, numbered in bundle order: `SPEC-003-T01` …
- For each prerequisite in `item_dependencies.json`: a `task` prerequisite becomes `depends_on` on
  its ticket; a `gap` prerequisite sets `blocked_on_client` and is added to the spec's
  `inputs_needed_from_client`.
- A human-set board status in `overrides.json` wins over the derived `status` for display.

## Ids

- Spec `SPEC-003`; ticket `SPEC-003-T02`; acceptance criterion `AC1` (numbered per spec, copied
  onto tickets); release `REL-001`. Dispatch ids are `WI-<item id>`, so nothing collides, and all of
  these match the board's id pattern.

## Rules the schemas encode

- A spec with `status: approved` carries `approval` (G1).
- A ticket past `tickets` has an `assignee` (G2).
- A ticket in `review` or later has at least one `evidence` entry.
- A ticket in `release` or `done` has `review.decision: approved` (G3).
- A `done` ticket has a `release` record (G4).
- `status`, `kind` and `priority` only take values the board already understands.

Rules enforced in code (not expressible in JSON Schema):

- `approval`, `review` and `release` are written only by the admin API, never by the agent.
- `review.reviewer` differs from `assignee`.
- A ticket enters `build` only when every `depends_on` ticket has passed review and
  `blocked_on_client` is false.
- `client_answer` and other client text are untrusted data: shown, never followed.

## Sample data

`specs.sample.json` has SPEC-003 (R, approved) and SPEC-005 (F, draft, waiting on gaps A2 and F5;
it depends on SPEC-002, which isn't in the sample). `tickets.sample.json` has SPEC-003's five
tickets at different stages. People's names are fictional.

The runtime (`src/sdlc`) writes the same shapes to `data/out/sdlc/`; `src/sdlc/tests/test_flow.py`
validates a full run against these schemas, so the contracts and the code can't drift apart.
