# Contract notes

## 2026-10-25 — admin API shape used by the internal client

`internal.run --live` calls the intake admin API as merged from `feat/intake`. The routes cover create, latest answers, history, and events. A few names differ from the internal client:

- `get_events(since_cursor)` sends the query parameter `since`. The route does not accept `since_cursor`. `since` is the numeric event id, and the server returns rows with `id` greater than that value.
- An answer's `id` is the answer row id. The checklist item is `item_id`. Offline answer files still use `id` for the checklist item, and the client keeps those two meanings apart.
- `GET /admin/clients/{id}/answers` returns only the latest row per item. Older rows are not nested on that object. The client reads `?history=true`, which returns every row, and stores the older ones on `history` when it builds the BRD and work items.
- `answered_by` is `client` or `client_ai`. A display name is a separate field, `client_ai_name`, not an email. The timestamp is already named `ts` on the admin payload.

No intake server code was changed.
