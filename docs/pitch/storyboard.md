# ACE Ops — pitch storyboard

Dell × NVIDIA AI Hackathon, San Francisco, 2026-10-25. Deck: `docs/pitch/deck.html` (open in any
browser, press **F** for fullscreen, **N** for speaker notes, **←/→** to move, **R** replays a slide's
animation). Static export: `docs/pitch/deck.pptx`.

Team: **Carl · Tyler · Jasmine T · Moorthy**. Roles on stage: **Carl** opens and closes (slides 1–3,
9–10), **Tyler** owns intake and local-first (slides 4, 7), **Moorthy** owns the SDLC and the console
(slides 5, 6, 8 and the gate clicks), **Jasmine T** owns the client-update beat (G5, the "Approve &
send" click and the plain-language update) and leads Q&A. Swap freely; the script below is written
to be read by one voice.

Numbers marked **[hypothesis]** are not measured (2–4 weeks, 12 hours, $500/month, $1,200 saved).
Everything else on screen is a fact from the repo or the Northline Goods sample data.

---

## 1. The 3-minute pitch

Total **3:00**. Clock column is the cumulative time at which you should be *leaving* the slide.

### Slide 1 · Title — 0:15 (leave at 0:15)

**On screen:** dawn hero, ACE OPS wordmark, "The always-on delivery agent for agencies", team, event.
The GB10 is visibly offline (cable out, or the Wi-Fi menu open on the second screen).

**Say:** "I'm Carl. I run ACE, a Google Ads agency. Every new client costs us weeks before we spend a
single euro for them. Today a client is going to onboard itself, on this box, with the network off.
We call it ACE Ops."

**Click:** none.

### Slide 2 · The problem — 0:25 (leave at 0:40)

**On screen:** three counters (2–4 weeks [hypothesis], 8 of 32 answers missing at kickoff, 12 hours
[hypothesis]), the email-ping-pong strip, the punchline about revenue versus profit.

**Say:** "Here's what onboarding looks like today. A kickoff call, a checklist in a doc, then weeks of
email: who has Merchant Center access, what are your margins, where's the tracking. Nobody chases,
and the answers never turn into assigned work. In our sample client, eight of the thirty-two answers
were still missing at kickoff. And when the campaigns finally start, they're optimized to revenue,
not profit, because nobody ever calculated break-even. Those two to four weeks are our estimate; we
start measuring on our next real client."

**Click:** none.

### Slide 3 · The insight — 0:25 (leave at 1:05)

**On screen:** the client's assistant on the left, ACE's intake MCP server on the right, and the
exchange animating between them: R2 margins, A2 Merchant Center gap, D5 "ignore previous
instructions" stored as data.

**Say:** "Business owners already live inside an AI assistant. So we don't send them a form. We give
their assistant one MCP URL and a scoped token, and it answers our thirty-two onboarding questions
directly, one per turn. Every answer is stored append-only, with who said it, which AI, and when.
Watch the third message: their assistant sent 'ignore previous instructions'. We stored it as an
answer and nothing happened, because client text is data, never an instruction. That's in the
tests."

**Click:** none.

### Slide 4 · How it works — 0:25 (leave at 1:30)

**On screen:** the eight-stage pipeline with the light travelling left to right, G1–G5 badges on
Spec, Tickets, Review, Release and Status; "the agent does" versus "a named person does".

**Say:** "Eight stages, one always-on loop on the box. Intake and the BRD you've just seen. Then the
SDLC agent writes one spec per section of the requirements, splits it into tickets with their
dependencies, drafts a starting point for the builder, pre-checks every acceptance criterion, bundles
a release and writes the client update in plain language. Five gates, and every one of them is a named
person clicking a button. The agent drafts. People decide."

**Click:** none.

### Slide 5 · The money moment — 0:30 (leave at 2:00)

**On screen:** the break-even table for Northline Goods. Margins count up, the margin-only floors
grow as bars, the client's stated break-evens appear as gold ticks, the 3× dashed target line drops
in, and the seasonal-decor bar turns red: 3.00× < ≈3.03×.

**Say:** "This is the moment that pays for the product. Northline told our intake their margins:
tableware fifty-eight percent, down to seasonal decor at thirty-three. Their own break-even after
shipping and returns runs from two-point-one to three-point-four. The agent's draft ranks the
categories by margin and computes the margin-only floor from their own numbers, marked as derived.
Seasonal decor's floor is three-point-oh-three. The campaign being planned targets three-x. Every
order at that target loses money before you've even counted shipping and returns. A person finds
this in week six. The agent put it in the first draft."

**Click:** none.

### Slide 6 · Guardrails — 0:25 (leave at 2:25)

**On screen:** four lines on the left; on the right the review card for SPEC-003-T02. The cursor
presses Approve, the gate slams shut with a red **409 — The reviewer must differ from the builder**,
the reviewer changes to Morgan Diaz, and a gold APPROVED stamp lands.

**Say:** "Now the part a judge should care about. The agent's MCP server exposes read, draft, split,
pre-check and status tools. There is no approve tool, no send tool, no delete tool. It physically
cannot approve its own work. Not 'is told not to'. And people get the same discipline. Jordan built
this table. Jordan tries to approve the review, and the API answers four-oh-nine: the reviewer must
differ from the builder. Morgan reviews instead. If the pre-check had failed, approve would be
refused too. Every number in the draft either traces to a client answer or is marked derived."

**Click:** none (the animation replays with R if you need it).

### Slide 7 · Local-first by construction — 0:15 (leave at 2:40)

**On screen:** the GB10 box with every service on 127.0.0.1, the local model chip with the pulsing
dot, and the egress wire ending in a blocked symbol.

**Say:** "Local-first is the agency's trust promise, so we put it in the code. The service refuses to
start if the model URL isn't loopback. The console's content-security policy is default-src none: no
fonts, no CDN, nothing. The pipeline is rules-first, so if the model dies it still runs, and every
artifact records whether rules or the model wrote it. Everything you've seen runs on this one GB10,
under OpenShell, with egress blocked."

**Click:** none.

### Slide 8 · Live demo map — 0:10 (leave at 2:50)

**On screen:** the nine-click path through the console at 127.0.0.1:8792, with the real button
labels. The console itself is on the second screen, pre-staged (see "Pre-stage" below).

**Say:** "In the long demo this is sixty seconds and nine clicks: approve a spec, accept a ticket, the
draft, submit, a four-oh-nine, a real approval, a release with client sign-off, and the update goes
out. Here's the four-oh-nine, live."

**Click (Moorthy, on the console, two clicks, pre-staged):** with **Acting as: Jordan Lee**, open
SPEC-003-T02 and click **Approve (G3)** → the red toast *"409 The reviewer must differ from the
builder."* Switch **Acting as** to **Morgan Diaz**, click **Approve (G3)** → approved. If the console
isn't ready, say the line and don't click; slide 6 already showed it.

### Slide 9 · Why it's a business — 0:08 (leave at 2:58)

**On screen:** who pays, $500/month [hypothesis], 12 h × $100 ≈ $1,200 [hypothesis], wedge →
expansion, why now.

**Say:** "Who pays? The agency owner. ACE is customer zero; every Google Ads agency serving e-commerce
has the same unbilled onboarding hours. Our pricing hypothesis is five hundred dollars a month per
agency: two onboardings a year pay for it."

**Click:** none.

### Slide 10 · Close — 0:02 (leave at 3:00)

**On screen:** built today, next week, the ask, the wordmark.

**Say:** "Built in one day. Sixty-one tests pass. Nothing leaves the box. Monday our next real client
goes through it. Thank you."

**Click:** none. Stop at 3:00 even if you're mid-sentence on slide 9.

**Time check:** 0:15 + 0:25 + 0:25 + 0:25 + 0:30 + 0:25 + 0:15 + 0:10 + 0:08 + 0:02 = **3:00**.

### Pre-stage (do this before the 3-minute pitch and before the 10-minute demo)

1. `make demo` has run; intake finished for Northline Goods; the board shows 30 work items, 8 gaps.
2. SDLC console at `http://127.0.0.1:8792`, source **Northline sample**, **Acting as: Avery Park**.
3. For the 3-minute version only: SPEC-003 already approved (G1), SPEC-003-T01 accepted and
   approved, SPEC-003-T02 accepted by **Jordan Lee**, draft saved, **Submit for review** clicked, so
   the ticket sits in *review* with Jordan as builder. The 409 is then two clicks away.
4. For the 10-minute version: SPEC-003 still a **draft**, so the whole path runs live.
5. Deck open in a second browser window on `#1`, fullscreen (F). Notes window (N) on the laptop screen.
6. Recorded backup video of a full run on the desktop, one click away.

---

## 2. The 10-minute live demo (top-8 run-of-show)

One client (Northline Goods), three roles, three planned wows (the injection, the break-even catch,
the 409). The deck is the second screen; the console and terminal are the first. Clock is the time
you *start* the row.

| Clock | Who | Screen | Click / command | Say |
|---|---|---|---|---|
| 0:00 | Carl | Deck slide 1; GB10 taken offline on camera | pull the cable / Wi-Fi off | "I run ACE, a Google Ads agency. New clients cost us weeks. Today one onboards itself, offline, on this box." |
| 0:40 | Tyler | Deck slide 4 beside a terminal | `nvidia-smi` | "Client AI, intake, BRD, dispatch, board, SDLC, console. One box, one GPU, everything on loopback." |
| 1:20 | Tyler | Terminal with the client log; board on the other half | `make demo` (live mode) | "This is Northline's own assistant answering our checklist, one question per turn. Watch the board fill as answers land." |
| 2:30 | Tyler | Client log paused on D5 | none | **Wow 1.** "Their AI just sent 'ignore previous instructions'. Stored as an answer, flagged untrusted. Nothing happened." |
| 3:10 | Tyler | `data/out/brd.md` | open the file | "The BRD writes itself: eight sections, every line with who answered and when, and an open-gaps list." |
| 3:50 | Tyler | Board → Developer → My plate | click the Blocked card | "Merchant Center access, blocked on the client. Nobody typed this ticket." |
| 4:30 | Moorthy | SDLC console, Specs tab, Acting as Avery Park | **Approve** (G1) on SPEC-003 | "One spec per section. The owner approves the profit-model spec, and the agent splits it into five tickets in dependency order." |
| 5:00 | Moorthy | Tickets, Acting as **Jordan Lee** | **Accept as Jordan Lee** (G2) on SPEC-003-T01, then on T02 | "A person in the role accepts; nobody gets work they didn't accept. The moment it enters build, the agent writes a draft from the client's own figures." |
| 5:40 | Moorthy | Draft drawer for SPEC-003-T02 (break-even table) | scroll the draft | **Wow 2.** "Ranked by margin. Margin-only floors, marked derived. Seasonal decor's floor is three-point-oh-three. A three-x campaign loses money on every order." |
| 6:20 | Moorthy | Same ticket | **Submit for review** | "The agent pre-checks each criterion. The traceability check: every number traces to a client answer or carries the derived mark." |
| 6:40 | Moorthy | Same ticket, still Acting as Jordan Lee | **Approve** (G3) | **Wow 3.** Red toast: 409, the reviewer must differ from the builder. "It can't. Not 'shouldn't'." |
| 7:00 | Moorthy | Acting as **Morgan Diaz** | **Approve** (G3) | "A different person in the role approves." (Repeat accept → submit → approve for T01 if it isn't done; keep it brisk.) |
| 7:30 | Moorthy | Acting as **Avery Park**, Releases | **Release SPEC-003…** (G4), tick client sign-off, confirm | "Releasing touches the client's ad account, so client sign-off is recorded on the release." |
| 7:50 | Jasmine T | Update tab, Acting as Avery Park | **Approve & send** (G5) | "The agent drafted the client update in plain language, with a follow-up question for every open gap: Merchant Center access, COGS completeness. The owner sends it; the questions go back to the client's AI through intake, and the loop starts again." |
| 8:15 | Tyler | Terminal | kill the model process; re-run the SDLC sync; then start it with a cloud URL in `INTERNAL_LLM_BASE_URL` | "Model dead: the pipeline still runs from rules, provenance says so. Cloud URL: it refuses to start. And from inside the sandbox, `curl https://example.com` is blocked." |
| 9:00 | Carl | Deck slide 9, then 10 | none | "Five hundred a month per agency, hypothesis. Monday our next real client goes through this. We built it in a day; sixty-one tests pass; nothing left the box." |
| 9:30 | Jasmine T leads, all answer | Deck slide 10 | none | Questions (section 3 below). Jasmine fields each one and hands it to whoever owns the answer. |

Fallbacks: if the model is slow, say "rules-first" and keep going, the drafts still appear. If the
console misbehaves, switch to the recorded run at the same timestamp. Kill the model only after intake
has finished: the client agent fails closed.

---

## 3. Eight likely judge questions

1. **"Where exactly are NemoClaw, OpenClaw or OpenShell in this?"**
   The always-on loops (the internal agent, the client agent and the SDLC service) run inside an
   OpenShell sandbox with a localhost-only egress policy, which is why the blocked `curl` is part of
   the demo. We claim the runtime we actually run and nothing more.

2. **"The client's AI is probably ChatGPT. How is that local-first?"**
   The client decides what its own assistant sees; that's their data and their choice. The
   aggregation point, where thirty clients' margins, COGS and ad-account access meet for months, is
   ACE's side, and that never leaves the box.

3. **"How does a cloud assistant reach a box under your desk?"**
   Today everything is on loopback and the demo client runs on the same machine. In production we
   expose only the three-tool intake endpoint through an authenticated tunnel with a per-client
   scoped token; the admin APIs and the agent's MCP server stay loopback-only.

4. **"What stops the client's AI from making things up?"**
   Answers are append-only with `answered_by`, the AI's name, a timestamp and full history, so
   nothing is silently overwritten. Developers verify access before anything is built on it, and
   anything that spends money or touches the client's account needs the client's sign-off at G4.

5. **"Prompt injection?"**
   Client text reaches prompts only as quoted data between fixed delimiters, and the D5 "ignore
   previous instructions" case is a test that must pass. The deeper answer is the tool list: the
   agent has no approve, send, delete or network tool, so there is nothing for an injection to drive.

6. **"If it runs with the model off, what is the AI actually doing?"**
   Rules are the floor: specs, tickets, the break-even table and the pre-check all work without a
   model, which is what makes it safe to run unattended. The local model writes: the client answers,
   the BRD wording, tighter acceptance criteria and the plain-language client update, and every
   artifact records which path produced it.

7. **"Is this a product or ACE's internal tool?"**
   Internal today, with one customer, and we're honest that this is founder-market fit rather than
   demand. The checklist is configuration (`bundle.json`) and the gates are generic, so the proof
   we're going after next is a second agency running it unaided on a paid pilot.

8. **"You wrote the client's answers yourselves. Isn't the demo rigged?"**
   The Northline persona keeps the demo repeatable, but the client's local model still has to return
   a valid answer per item with a retry and a fail-safe N/A, and the five gaps and the injection come
   from that run. The number that matters next is days-to-first-spend on ACE's next real client,
   measured against our last three.
