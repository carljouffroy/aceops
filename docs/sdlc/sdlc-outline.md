# SDLC automation outline

What the SDLC agent does at each stage, the tools it uses, where people approve, and how work
reaches each role. Stages and gates are defined in `sdlc-plan.md`; data shapes in
`contracts/sdlc/`.

## Shape

`src/sdlc/` runs as one always-on process on the GB10 with two faces, the same split intake uses
(MCP for the AI, admin API for people):

| Face | Proposed address | Used by | Can approve? |
|---|---|---|---|
| SDLC MCP server | `127.0.0.1:8791/mcp` | the SDLC agent (local model) | **No.** Approval tools are not on its tool list. |
| SDLC admin API | `127.0.0.1:8792` | the board's buttons (people) | Yes: gates G1 to G5 |

Ports are a proposal; confirm with Carl and Tyler. Board stays on `:8790`, intake on `:8787`/`:8788`.

The agent can't approve its own work because the approve endpoints aren't reachable through its
tools. That is the main safety property, and it's easy to show in the demo.

## The always-on loop

`python -m sdlc.run --live` checks every 5 s (file modification times, so it's cheap):

1. **`work_items.json` changed** → group new work items into deliverables and draft specs.
   Approved specs are never edited; new information creates a new draft version.
2. **A spec was approved (G1)** → split it into tickets.
3. **A ticket entered Build (after G2)** → write a draft artifact for the builder.
4. **A ticket entered Review (evidence attached)** → pre-check its acceptance criteria.
5. **All tickets of a spec approved (G3)** → draft release notes and the client summary, and flag
   the spec for G4.
6. **Anything changed** → rebuild `data/out/sdlc/status.json` and the draft client update.

It runs as a restarting background service, like the internal agent's `--live` mode.

## Agent tools (SDLC MCP server)

| Tool | Inputs | Output | Stage | Refuses when |
|---|---|---|---|---|
| `read_brd` | `client` | `{sections: {P..ST: markdown}, open_gaps: [{source_item_id, text}]}` from `data/out/brd.md` | Spec | BRD missing |
| `list_work_items` | `client`, `role?` | work items from `data/out/work_items.json` | Spec | — |
| `draft_spec` | `client`, `work_item_ids[]`, `title?` | spec with `status: draft` | Spec | ids unknown; output fails the schema |
| `revise_spec` | `spec_id`, `changes` | updated draft, or a new version if the spec was approved | Spec | spec rejected or superseded |
| `split_spec` | `spec_id` | tickets with `stage: tickets` | Tickets | spec not approved |
| `list_tickets` | `client`, `role?`, `stage?` | tickets | any | — |
| `draft_artifact` | `ticket_id` | `{path}` under `data/out/sdlc/drafts/` | Build | ticket not in build |
| `precheck` | `ticket_id` | `[{ac_id, result: met \| not_met \| needs_human, reason}]` | Review | ticket not in review; no evidence |
| `draft_release` | `spec_id` | `{release_id, notes, client_summary}` | Release | any ticket not approved |
| `build_status` | `client` | status report | Status | — |

Every write is validated against the schema before it is saved; a failing write is rejected and
logged, not repaired silently.

## Human gates (SDLC admin API, called by the board)

| Gate | Endpoint | Who | Checks in code |
|---|---|---|---|
| G1 | `POST /specs/{id}/approve` `{by, note}` · `POST /specs/{id}/reject` `{by, reason}` | project owner | spec is a draft |
| G2 | `POST /tickets/{id}/accept` `{by}` | someone in the ticket's role | ticket in `tickets` |
| Build exit | `POST /tickets/{id}/evidence` `{kind, ref, by}` | the assignee | ticket in `build`, dependencies passed review, not blocked on client |
| G3 | `POST /tickets/{id}/review` `{reviewer, decision, notes}` | reviewer in the same role | reviewer ≠ assignee (409 otherwise) |
| G4 | `POST /releases` `{spec_id, approved_by, client_signoff, notes}` | project owner | every ticket approved; `client_signoff` present when the spec spends money, goes public or touches client production |
| G5 | `POST /status/{client}/send` `{by}` | project owner | draft exists; queues approved follow-up questions for intake |

Plus `GET /events` so the board can refresh, as it does for intake progress.

## What the agent does, per stage

**Spec.** Rules first: one spec per BRD section that has at least one `task` work item, id fixed by
section order (SPEC-003 = R). Lead role is the section's most common role. Scope lines are the
section's `task_if_answered` titles. Gap work items in the section, and gap prerequisites from
`item_dependencies.json`, become `inputs_needed_from_client` with the checklist item's own text as
the question. Acceptance criteria start from a per-role template:
- Marketing Specialist: recommendations respect the client's exclusions and break-even ROAS; no claim the client hasn't confirmed.
- Data Analyst: every number traces to a named export or answer; totals reconcile with the client's source.
- Developer: findings name the account, property or feed checked; any code lives in a sandbox branch with a test.

The local model then tightens the wording and may suggest extra criteria; those are marked
`generated_by: local_llm`.

**Tickets.** One ticket per `task` work item in the section, numbered in bundle order, copying the
work item's fields. `depends_on` comes from `item_dependencies.json` (for SPEC-003: R2, R4 ← R1;
R3 ← R1, R4; R5 ← R2). A prerequisite that is still a gap sets `blocked_on_client` instead.

**Build.** Writes a starting point the builder edits, never sent outside the GB10:
- Marketing Specialist: ROAS target vs break-even table by category, campaign structure with exclusions.
- Data Analyst: margin-by-product and profit model sheets from the client's exports, with data quality notes.
- Developer: data-flow map (source → destination → data → frequency), feed review checklist, a sandbox patch where code is needed.

**Review.** Checks each criterion against the evidence: `agent_check` criteria get a result with a
reason; `human_review` and `client_confirmation` ones are always `needs_human`. It never sets
`review`.

**Release.** Writes internal release notes and a short client-facing summary in plain language.

**Status.** Rolls up tickets by stage and role, lists blocked and overdue items, and turns open
gaps into follow-up questions. The client update is a draft until G5.

## How work reaches each role

1. Tickets land on the board's **My plate** for their role once the board also reads `data/out/sdlc/tickets.json` (proposal 1 in the CHANGELOG entry). The board's existing status edits keep going to `overrides.json`; SDLC reads that file and never writes it.
2. **Accept** on the card is gate G2 (a call to the SDLC admin API); the card then shows the agent's draft and an evidence field.
3. Stretch, if Tyler's OpenClaw chat channel lands: post "New ticket for Data Analyst: SPEC-001-T03 …" to the role's channel.
4. ACE Ops (our Myop tracker) is **not** called at runtime: it's a cloud app. The project owner can paste the status summary into ACE Ops by hand.

## Local-only inference

- Model calls go to the GB10 endpoint in `INTERNAL_LLM_BASE_URL` / `INTERNAL_LLM_MODEL` (OpenAI-compatible), shared with the internal agent.
- **The SDLC service refuses to start if that URL's host isn't `127.0.0.1`, `localhost` or `::1`.** A few lines of code that back up the local-first claim. `src/internal/llm.py` has no such check today (only an `.env.example` comment), so the same guard is proposed there.
- Every model call has a timeout (20 s) and a rules-only fallback, so the pipeline still runs if the model is down. `provenance` records which path produced each object.
- Runs under the same OpenClaw/OpenShell setup as the internal agent, with network access limited to localhost. Declare only the runtime we actually run.

## Untrusted client text

Client answers reach prompts only as quoted data between fixed delimiters, never as instructions.
The agent has no tool that approves, sends, deletes or reaches the network, and every output is
schema-checked. Answers that look like instructions ("ignore previous…") are flagged in the spec's
`risks`, reusing intake's injection test cases.

## Demo path (about 30 s of the video)

1. Intake finishes for Northline Goods → draft specs appear, one per BRD section.
2. Approve SPEC-003 (Profit model) → five tickets land on Data Analyst and Marketing Specialist plates, in dependency order.
3. Try to approve a review as the builder → 409, "reviewer must differ from assignee".
4. Status panel shows the draft client update asking for the two answers that block the feed review (A2 Merchant Center access, F5 COGS completeness).
