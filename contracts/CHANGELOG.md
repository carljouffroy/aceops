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
