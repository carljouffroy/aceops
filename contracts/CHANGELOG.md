# Contract notes

## 2026-10-25 — admin API shape used by the internal client

`internal.run --live` calls the intake admin API as merged from `feat/intake`. The routes cover create, latest answers, history, and events. A few names differ from the internal client:

- `get_events(since_cursor)` sends the query parameter `since`. The route does not accept `since_cursor`. `since` is the numeric event id, and the server returns rows with `id` greater than that value.
- An answer's `id` is the answer row id. The checklist item is `item_id`. Offline answer files still use `id` for the checklist item, and the client keeps those two meanings apart.
- `GET /admin/clients/{id}/answers` returns only the latest row per item. Older rows are not nested on that object. The client reads `?history=true`, which returns every row, and stores the older ones on `history` when it builds the BRD and work items.
- `answered_by` is `client` or `client_ai`. A display name is a separate field, `client_ai_name`, not an email. The timestamp is already named `ts` on the admin payload.

No intake server code was changed.

## 2026-10-25 — progress.json

`internal.run` also writes `progress.json` next to `brd.md` and `work_items.json`. The shape is `contracts/progress.schema.json`.

- `priority_gate.ids` lists checklist items with `priority: true`, in bundle order. `priority_gate.done` is true only when each of those items is DONE or PROVIDED. N/A and a missing answer leave the gate closed.
- `by_role.<role>.open` counts that role's work items whose status is not Done. `by_role.<role>.blocked` counts the ones with `blocked_on_client` true.
- Each output file is replaced atomically: the new text is written to a temporary file in the same directory, then renamed.

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
