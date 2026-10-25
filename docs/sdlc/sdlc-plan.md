# SDLC plan

How client work moves from the intake checklist to delivered work, for the three delivery roles
(Marketing Specialist, Data Analyst, Developer). Intake and BRD already exist; this plan adds
Spec through Status.

**Principle: the agent drafts, people decide.** The agent does the paperwork at every stage
(drafting, splitting, checking, summarising). A named person approves at five gates, and nothing
reaches the client, spends client money or touches a client system without one.

**Project owner** below means the owner of the project in ACE Ops (the `owner` field). For the
demo client, Northline Goods, that is the account lead.

## Stages at a glance

| # | Stage | Owner role | Agent does | Human gate |
|---|---|---|---|---|
| 1 | Intake | Client (their AI) | Asks the next checklist item, records answers with provenance | None (client is the source) |
| 2 | BRD | Internal agent | Groups answers by section, lists open gaps | None today; gaps feed Spec |
| 3 | Spec | Lead role of the deliverable | Drafts one spec per deliverable from BRD sections and work items | **G1: project owner approves the spec** |
| 4 | Tickets | Lead role of the spec | Splits an approved spec into tickets with acceptance criteria and dependencies | **G2: each role accepts its tickets** |
| 5 | Build | Ticket's role | Drafts the artifact (copy, tracking plan, code) in the sandbox; people do the real work | None; evidence is required to leave |
| 6 | Review | A reviewer who is not the builder | Pre-checks each acceptance criterion | **G3: reviewer approves or requests changes** |
| 7 | Release | Project owner | Bundles approved tickets, writes release notes and the client-facing summary | **G4: project owner says go; client sign-off for spend or anything public** |
| 8 | Status | Project owner | Rolls up progress, blockers and gaps; drafts the client update | **G5: project owner sends the client update** |

## Stage detail

### 1. Intake (exists)
- **Entry:** client invited, `bundle.json` loaded for the client.
- **Exit:** every checklist item is answered or marked as a gap. Answers are append-only with
  provenance (`answered_by`, `client_ai_name`, `source`, `ts`).
- **Gate:** none. Client answers are treated as untrusted data in every later stage.

### 2. BRD (exists)
- **Entry:** at least one answered item.
- **Exit:** `data/out/brd.md` up to date, with sections P, A, R, O, F, D, C, ST and an Open gaps
  list. `data/out/work_items.json` dispatched by role.
- **Gate:** none today. The project owner reads the BRD as part of G1.

### 3. Spec (new)
- **Owner:** the role that leads the deliverable (for example, Data Analyst for the profit model).
- **Entry:** the BRD section has at least one answered item (a `task` work item).
  A spec may start with gaps; they are listed as `inputs_needed_from_client`.
- **Agent:** drafts one spec per BRD section (SPEC-003 is "Profit model and constraints"). Writes
  the goal, scope, out of scope, acceptance criteria, client inputs still needed, dependencies and
  risks. Links back to every source checklist item and work item.
- **Exit:** spec status `approved`.
- **Gate G1:** the project owner approves, rejects with a reason, or edits and approves.
  A rejected spec goes back to `draft`. Once approved, a spec is frozen; changes make a new version.

### 4. Tickets (new)
- **Owner:** the lead role of the spec.
- **Entry:** spec `approved`.
- **Agent:** makes one ticket per `task` work item in the spec's section. Each ticket has its role,
  the acceptance criteria that apply to it, `depends_on` (from `contracts/sdlc/item_dependencies.json`)
  and `blocked_on_client` when a prerequisite is still a gap. Tickets keep all `work_items` fields so
  the board can show them.
- **Exit:** every ticket accepted by someone in its role.
- **Gate G2:** each role accepts its own tickets from My plate (or hands one back with a reason).
  Nobody gets work they didn't accept.

### 5. Build (new)
- **Owner:** the ticket's role.
- **Entry:** ticket accepted, all `depends_on` tickets released or approved, and
  `blocked_on_client` false.
- **Agent:** drafts a starting point inside the OpenShell sandbox, never sent anywhere:
  - Marketing Specialist: ROAS targets against break-even, campaign structure with exclusions, budget split.
  - Data Analyst: margin by product, profit model and data quality notes from the client's exports.
  - Developer: data-flow map, feed review checklist, and a patch in a sandbox branch where code is needed.
- **Exit:** the builder attaches evidence (link, file, PR or note) and moves the ticket to review.
- **Gate:** none, but a ticket cannot leave Build without evidence.

### 6. Review (new)
- **Owner:** a reviewer in the same role who is not the builder.
- **Entry:** ticket in review, with evidence.
- **Agent:** pre-checks each acceptance criterion against the evidence and marks it `met`,
  `not_met` or `needs_human`. It never marks the ticket approved.
- **Exit:** reviewer decision recorded.
- **Gate G3:** the reviewer approves, or requests changes (the ticket goes back to Build with notes).

### 7. Release (new)
- **Owner:** project owner.
- **Entry:** one or more approved tickets that ship together (for example, all tickets of a spec).
- **Agent:** writes release notes and a client-facing summary in plain language.
- **Exit:** released (campaign live, code merged and deployed, report delivered).
- **Gate G4:** the project owner says go. Anything that spends client money, goes public or
  touches the client's production systems also needs the client's sign-off, recorded on the release.

### 8. Status (new, runs continuously)
- **Owner:** project owner.
- **Entry:** always on; runs after every change and on a schedule.
- **Agent:** rolls up tickets by stage and role, lists overdue and blocked items, and turns open
  gaps into follow-up questions for the client.
- **Exit:** `data/out/sdlc/status.json` updated; draft client update ready.
- **Gate G5:** the project owner reviews and sends the client update. Follow-up questions go back
  to the client's AI through Intake only after this approval.

## Ticket lifecycle

```
tickets ──G2──▶ build ──evidence──▶ review ──G3 approve──▶ release ──G4──▶ done
                  ▲                    │
                  └── changes requested┘
blocked: any stage, while blocked_on_client is true or a depends_on ticket isn't done
```

`stage` (above) is new. The existing `status` field keeps the values the board already uses; the
mapping between them is in `contracts/sdlc/README.md`.

## Out of scope for today

Client sign-off UI (recorded as a note for now), real ad-platform or CMS writes, estimates and
capacity planning, multi-client scheduling, FR/EN.
