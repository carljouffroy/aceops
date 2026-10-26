# ACE Ops · what to say while the product runs

Read this aloud while the console's **Tour** button drives the screen (each line below is one
tour step; press **Next** or **Do it for me** as you finish the line). Total about 3 minutes
for the short version; the long version adds the bracketed lines. Three voices: **Carl** opens and
closes, **Tyler** owns intake and local-first, **Moorthy** owns the gates and the Data room.

## Before you start
- Everything runs **on the GB10**, on its own display or HDMI out; the box is in frame, not a laptop.
  On the box: `cd aceops && git pull origin main && uv sync`, then `make sdlc-sample` (console
  `http://127.0.0.1:8792`), source **Northline sample**, autopilot **off**.
- Press **Tour**. If it asks, choose **Reset and start**.
- A terminal window next to the console, already showing:
  `watch -n 2 nvidia-smi --query-gpu=name,memory.used,utilization.gpu --format=csv` (the GB10 and
  the Nemotron runner on the GPU), and a second tab with `ollama ps` and `nemoclaw status`.
- The OpenClaw chat in the sandbox (`nemoclaw launch`), for the 20-second beat after the 409.
- The network cable out of the box, visibly, before the first word.

## Show the box · 25 seconds, right after Carl's opener (Tyler)
*(point at the GB10)* "This is a Dell Pro Max with GB10. Everything you'll see runs on it and
nothing else: Nemotron 3 Nano, thirty billion parameters, served locally by Ollama" *(show
`ollama ps` and `nvidia-smi`: the model sitting in GPU memory)* "inside NVIDIA's NemoClaw and
OpenShell sandbox" *(show `nemoclaw status`)*. "The cable is out. There is no cloud in this demo,
and the product refuses to start if you point it at one."

## Step 1 · "This is the real product, running now" (Carl)
"I run a performance-marketing agency. Every new client costs us weeks before we spend a single
euro for them. What you're looking at is the product running on this box, right now: the client's
answers became a brief, work items and six draft specs. Nothing on this screen is a mock-up."

## Step 2 · G1, approve a spec (Carl, then Moorthy takes the mouse)
"I'm the project owner. I approve the profit model workstream."
*(click Approve)* "The agent split it into five tickets, in dependency order, the moment I did."

## Step 3 · G2, accept the ticket (Moorthy)
"Now I'm Jordan, a data analyst. This is on my plate. I accept it, and the agent writes a working
draft from the client's own figures, not from a template."

## Step 4 · Build, submit (Moorthy)
"Here's the draft: the client's answer quoted as data, their numbers in a table, the steps, the
acceptance criteria. I submit it. The agent pre-checks every criterion; every number in my draft
either traces to something the client said or it's marked as derived."

## Step 5 · The 409 (Moorthy)
"Now watch. I'm still Jordan, and I try to approve my own work." *(click Approve)*
"Refused. 'The reviewer must differ from the builder.' That's in the code, not in a prompt."
[Long version, Tyler: "And the agent has the same discipline. In the sandbox, OpenClaw can read the
brief, list the specs, run a pre-check. Ask it to approve something." *(show the OpenClaw chat)*
"It can't. There is no approve tool. Every other agent asks permission; ours can't ask, because it
has no hands."]

## Step 6 · A different person approves (Moorthy)
"Morgan, also a data analyst, approves it. The ticket moves to release, and the ticket that was
waiting on it unblocks."

## Step 7 · The money moment (Moorthy)
"I accept the next one: rank categories by margin. The agent ranks the client's categories and
derives the break-even ROAS each one needs. Seasonal decor needs three-point-four to break even.
Anything under that loses money on every order. A human finds this in week six. The agent put it
in the first draft."

## Step 8 · G4, release (Carl)
"Back to me as the owner. I release the workstream. The dialog won't let me unless I record who
signed off at the client, because this touches their ad account. The agent writes the release
notes."

## Step 9 · G5, the client update (Carl)
"The agent drafted a plain-language update for the client with one follow-up question per open
gap. I read it, and I send it. Nothing reaches the client without a person."

## Step 10 · The Data room (Moorthy)
"One more thing clients give us: data. This is a real sales export, nine thousand nine hundred
and ninety-four order lines. The Analyst agent found which products sell more on promotion and
which promotions lose money, by region and by customer segment. One click, and it's a spec with
tickets, through the same gates."

## Step 11 · Autopilot (Tyler)
"When the owner delegates, seven agents take over: analyst, spec, dev, test, debug, deploy,
status. Each one runs in its own process with nothing but its stage's files. Watch the run log:
the dev agent builds, the test agent reviews, and the same 409 would stop either of them reviewing
their own ticket. All of it on this GB10, on Nemotron, with the network cable out."

## Step 12 · Close (Carl)
"Intake to released work on one machine, with people at every gate until they choose to delegate.
It saves us about ten hours per client onboarding today, and it's the same engine for every
workflow an agency runs. We're ACE Ops."

## If something breaks
- The engine runs without the model: say "rules first, the model polishes" and keep going.
- If a click doesn't take, press **Do it for me** on the tour panel; it runs the same gate.
- Backup: the website runs the same engine in a browser tab, and the recorded video.
