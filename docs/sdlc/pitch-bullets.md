# SDLC story for the pitch deck and writeup

Three bullets, in the order they land. Each one is something the judges can watch happen on the console.

1. **From brief to delivered work, without a project manager typing.** The moment the client's AI finishes the checklist, the agent drafts one spec per BRD section, and after the owner approves it, splits it into dependency-ordered tickets and writes the first draft of each deliverable from the client's own figures. For Northline Goods that means ranked category margins and a break-even ROAS table before anyone opens a spreadsheet.

2. **The agent drafts, people decide, and the code enforces it.** Five gates stay with humans: approve the spec, accept the ticket, review a peer's work, release, send the client update. The agent's MCP server simply has no tool for any of them, a builder who tries to approve their own ticket gets a 409, and a ticket with a failing traceability check cannot be approved. Every number in a draft either traces to a client answer or is marked derived.

3. **Local-first is a buying reason, not a hackathon rule.** Margins, COGS, ad-account IDs and exports are the most sensitive data an agency holds for a client. All of it stays on one GB10: every server binds loopback, the SDLC service refuses to start if the model URL isn't local, the console loads nothing from the network, and the rules engine keeps working if the model goes down. "No new AI subprocessor in your data agreement" is the sentence that closes the sale.

## One-liner for the writeup

ACE Ops turns a client's answers into approved, reviewed, delivered agency work on a single local machine: the client's AI answers the brief through MCP, an always-on agent drafts specs, tickets, deliverables and client updates, and five human gates decide what ships.
