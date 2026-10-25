<!-- Append the section below to contracts/CHANGELOG.md once feat/sdlc is rebased on a main that
     has it. contracts/CHANGELOG.md is only on integration today, so adding it on feat/sdlc now
     would create an add/add conflict. -->

## 2026-10-25 — SDLC contracts (draft, feat/sdlc)

New files in `contracts/sdlc/`: `spec.schema.json`, `ticket.schema.json`,
`status_report.schema.json`, `item_dependencies.json`, three samples and a README.

- A ticket carries all 14 `work_items` fields with the same types and enums. With the SDLC fields
  removed it validates against `work_items.schema.json`. No existing contract was changed.
- SDLC output goes to `data/out/sdlc/`. It never writes `work_items.json` or `overrides.json`.
- `status` on a ticket uses the board's enum. The SDLC position is a separate `stage` field.

Proposed, not made (each owner decides):

1. **Board (Tyler):** read `data/out/sdlc/tickets.json` next to `work_items.json`, and show
   `stage` when it is present. Without this change the tickets don't appear on the board, and
   nothing else breaks.
2. **Internal (Carl):** refuse an `INTERNAL_LLM_BASE_URL` whose host isn't `127.0.0.1`,
   `localhost` or `::1`. Today only `.env.example` says local only. The SDLC service applies the
   same check.
3. **`item_dependencies.json` (Carl):** review the prerequisite pairs. They are inferred from the
   item texts in `bundle.json`.
4. **Intake (Carl, after today):** an admin route to queue a follow-up question for an item, so
   approved open gaps from Status can go back through `get_next_item`.
