# ACE Ops: office hours

YC-style office hours (startup mode), 2026-10-25, 1:45 PM PT, answered from the team brief, event
page and repo.
**[F]** = fact (brief, event page or code). **[A]** = assumption: confirm with Carl before saying it on stage.

## Partner's verdict

- **Best asset: the agent catches money the client is losing.** Northline has never calculated
  break-even ROAS (R3). Its other answers put home goods at about 4.3x in Google's numbers (at an
  assumed 20% VAT). Lead with that, not "faster onboarding".
- **Biggest risk: the NVIDIA stack is invisible.** NemoClaw, OpenClaw and OpenShell appear only in
  `docs/sdlc/`, not in code or `scripts/run_demo.sh` [F].
- **Second risk: the demo data hides the story.** The last run was `mode: scripted`, which answers
  all 32 items "recorded for hackathon": a BRD with no content, 0 blocked items [F].
- **Demand evidence is one customer, ACE.** Fine today, not for a YC interview.

**Premises:** the agency owner buys, the client's AI is the channel; the metric is time to a
*profitable* first spend; local-first is the agency's trust promise; "the agent drafts, people
decide" is the product.

## 1. Pitch

**One sentence.** ACE Ops takes a new e-commerce client from signed contract to a profit-safe Google
Ads plan in an hour instead of weeks: the client's AI answers our onboarding checklist, an always-on
agent on a Dell GB10 turns it into assigned, approval-gated work, and client data never leaves the box.

**15 seconds.** "Agencies lose the first weeks of every client chasing access, margins and tracking
over email. Here, the client's AI answers our 32 onboarding questions directly. An agent on this box
writes the requirements, puts work on each person's plate, and just told our client their home-goods
ads lose money below 4.3x ROAS. Nothing leaves this machine, and the agent can't approve its own work."

("Weeks" and "an hour" are [A]; swap in ACE's real numbers.)

## 2. Problem

**Who (Q3).** The account lead at a performance-marketing agency: Carl [F]. What gets them fired: a
client who churns in month two because launch slipped and campaigns optimized to VAT-inclusive
revenue instead of profit [A].

**Status quo (Q2).** Kickoff call, checklist doc, email threads, Loom videos on granting access, then
a board typed up by hand [A: confirm ACE's tools].

| Claim | Basis |
|---|---|
| 32-item checklist, 8 sections, 3 delivery roles; payment and access are the priority gate | [F] |
| 2 to 4 weeks of back-and-forth, 8 to 15 senior hours per onboarding | [A] |
| Access gaps surface after kickoff; undocumented asks become scope creep | [A] |
| Clients don't know their break-even ROAS | [F] Northline, [A] in general |

**How often.** Intake once per client; gaps, follow-ups and status for the life of the account.
That's why it's an always-on agent, not a form.

**Cost.** Late first spend and wrong targets burn budget and cause churn [A]. Put one real ACE
number on a slide: days from signature to first spend.

## 3. Who pays and why

1. **ACE, customer zero [F].** Buyer and user. Founder-market fit, not demand (Q1).
2. **Google Ads agencies serving e-commerce [A].** Onboarding hours are unbilled; launch speed keeps clients.
3. **In-house growth teams [A]** onboarding agencies and freelancers: same checklist, reversed.

**Pricing hypothesis [A].** $500/month per agency up to 20 active clients, box bought or leased.
12 hours saved × $100/h ≈ $1,200 per onboarding: two a year cover it. Test with paid pilots.

## 4. Why local-first is a buying reason

Per client, this box holds [F]: the Google Ads customer ID, Merchant Center and GA4 access, a Shopify
seat, COGS per product, margin by category, revenue and next year's target (1.2M to 1.4M EUR), and
return and stock-out patterns. Sales and returns exports (D1, D2) likely add customer names and
addresses: personal data [A].

That's a client's P&L, and an agency holds 20 to 40 of them [A]: the aggregation point is the risk.
Sales line: "Your margins and customer exports stay on a machine in our office. No new AI
subprocessor in your data agreement." [A: check ACE's contracts for subprocessor clauses.] Also:
always-on loops cost a fixed box, not a token bill, and rules-first output survives a dead model [F].

## 5. Why now (and Q6, future-fit)

- Owners now work inside AI assistants, and MCP lets them call another company's tools. ACE's
  intake is an MCP server with three tools and a scoped token [F]: a handshake, not an integration.
- A desk-side 128 GB box runs capable open models; NVIDIA's sandbox makes unattended agents
  acceptable [F, event page].
- Three years out, AI-to-AI onboarding is the norm. The threat is Google automating setup; but
  profit-aware setup (break-even, exclusions, VAT) is what platform automation won't do for the client [A].

## 6. Competition and the wedge

| Alternative [A, not researched today] | Gap |
|---|---|
| Forms, sheets, email, Asana/ClickUp | Nobody chases; answers never become assigned work |
| Access-request tools (Leadsie-style) | Access only; no profit model, no routing |
| Client portals, onboarding platforms (Content Snare, Rocketlane) | Client still types; generic, cloud |
| ChatGPT/Claude with pasted notes | No provenance, no gates, data in a cloud |

**Wedge (Q4).** One link: the client's AI answers, and an hour later the agency has a BRD, a gap list
and a break-even table. That sells without SDLC; SDLC makes it recurring.

## 7. Hardest questions, honest answers

1. **"Where's NemoClaw/OpenClaw/OpenShell?"** Today, only in docs [F]. After change #1: "The loops run
   in an OpenShell sandbox that allows only localhost; here's a blocked request." Claim nothing more.
2. **"The client's AI is probably ChatGPT. Local-first how?"** The client decides what its assistant
   sees. ACE's side, where 30 clients' data meets margins for months, never leaves the box.
3. **"How does a cloud AI reach a box under your desk?"** Loopback today [F]. Production: an
   authenticated tunnel exposing only the three-tool intake endpoint [A]; admin API stays loopback [F].
4. **"What if the client's AI makes things up?"** Answers are append-only with `answered_by`, name,
   timestamp and history [F]. Developers verify access; spend needs client sign-off at G4 [F, design].
5. **"Prompt injection?"** Northline answers D5 with "ignore previous instructions" [F]; it's stored as
   quoted data and tested [F]. Deeper answer: the agent has no approve, send or delete tool.
6. **"If it runs with the model off, what's the AI for?"** Rules are the floor; the model writes
   (client answers, BRD, specs, client updates). Show both.
7. **"Product or internal tool?"** Internal today [F]; the checklist is config (`bundle.json`). Proof
   needed: a second agency running it.
8. **"You wrote the client's answers. Rigged?"** The persona keeps the demo repeatable [F]. The model
   still has to return valid JSON per item, with a retry and fail-safe N/A [F]. Nobody outside the
   team has used it unaided yet (Q5); see the assignment.

## 8. Judging criteria: what top marks require

| Criterion | The demo must show |
|---|---|
| Technical execution | Live local-model run; board filling as answers land; 47 tests passing (31 core + 16 SDLC, run 1:46 PM) [F]; 409 on self-approval; model killed, pipeline still runs |
| Business value | Carl as owner; one real ACE onboarding number; the break-even catch in euros; a price |
| Local-first design | GB10 visibly offline; model on 127.0.0.1 with GPU busy; loopback guard refusing a cloud URL; OpenShell policy blocking egress |
| Demo quality | One client, three roles, three planned wows, under time, recorded backup from a real run |

## 9. Run-of-show

**10 minutes.** Carl opens and closes, Tyler drives intake and board, Moorthy drives SDLC. * = needs
the SDLC slice; if it misses 5:00, show the break-even table from a script and drop the 409.

| Time | Click | Say |
|---|---|---|
| 0:00 | Take the GB10 offline, on camera | "I run ACE, a Google Ads agency. New clients cost us weeks. Today one onboards itself, offline." |
| 0:45 | Architecture slide; `nvidia-smi` | "Client AI, intake, BRD, dispatch, board, delivery. One box." |
| 1:30 | `make demo` live; client log beside the board | "Northline's assistant, one question at a time." |
| 2:45 | Pause on D5 | **Wow 1:** "Their AI sent 'ignore previous instructions'. Stored as an answer. Nothing happened." |
| 3:30 | `data/out/brd.md` | Sections, provenance, open gaps |
| 4:30 | Board, Developer, My plate | "Merchant Center access, blocked on client. Nobody wrote this ticket." |
| 5:30 | Approve SPEC-003 (G1)* | Five tickets, in dependency order |
| 6:15 | Profit model draft* | **Wow 2:** "Break-even: apparel 2.9x, home 3.6x. Google counts VAT, so in-platform 3.4x and 4.3x. A 3x home campaign loses money." |
| 7:00 | Approve own review as builder* | **Wow 3:** 409. "It can't approve its own work, not 'is told not to'." |
| 7:45 | Client AI re-answers A2 | Blocked card flips to To do, live |
| 8:30 | Kill the model; rerun BRD | Still produced from rules; loopback guard rejects a cloud URL |
| 9:15 | Price slide | "$500 a month per agency. Our next real client goes through this Monday." |

Kill the model only after intake: the client agent fails closed [F].

**3 minutes:** hook offline (0:00), intake with D5 (0:20), blocked card (1:10), break-even catch
(1:35), 409 (2:10), local proof (2:30), price and ask (2:45).

## 10. Top 5 changes, ranked (each under 2 hours)

Clock [F]: review 3:30, SDLC merge cutoff 5:00, code lock 5:30, submit 6:00.

**SDLC approach, decide at 3:30:** (A) cut it, safest, loses wows 2 and 3; (B) all stages, won't land
by 5:00; (C) one slice through SPEC-003: approve, tickets, profit model, 409. **Recommend C.**

1. **NVIDIA stack real and visible (Tyler, ~1.5h).** Run `internal.run --live`, the client agent and
   the SDLC loop in an OpenShell sandbox (or NemoClaw) with a localhost-only egress policy. Show the
   policy and one blocked `curl`. Without it, "at least one must be used" is an eligibility risk.
2. **Demo data tells the story (Carl, ~45 min).** Primary run on the GB10 model with `INTERNAL_LLM_*`
   set so polish shows (unset today [F]). Make the scripted fallback in `tools/fake_client.py` replay
   `fixtures/client_persona.md` (real values, five N/A gaps, D5) instead of "recorded for hackathon".
3. **Break-even table as rules (Moorthy, ~1h).** From R1, R2, R4, F4: 1 / contribution margin, times
   (1 + VAT) for in-platform targets. VAT is unknown, so assume 20% and queue "confirm your VAT rate"
   as a follow-up. Put it on the SPEC-003 card.
4. **Live unblock (Carl + Moorthy, ~45 min).** Intake accepts corrections and live mode re-dispatches
   [F]. A short script has the client's AI re-answer A2; the blocked card flips on screen.
5. **Lock and record (everyone, from 5:00).** Add the loopback guard to `src/internal/llm.py` (today
   only an `.env.example` comment [F]). Freeze scope. Record the 3-minute video from a real run.
   Rehearse twice on a timer, once with the model killed.

## The assignment

Today: changes 1 to 3 by 4:00 PM, or fall back to approach A. After today: run ACE's next real client
through ACE Ops with consent, measure days to first spend against the last three clients, and send
the video to five agency owners with a $500 pilot ask.

## What I noticed

- "The agent physically cannot approve its own work." Safety lives in the tool list, not the prompt.
  Say exactly that on stage.
- "Rules-first ... works even when the model is down." Rare discipline at a hackathon. Demo it.
- Your persona answers R3 with "has not been calculated." That line is your best slide.
