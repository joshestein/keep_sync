# The extension mints Keep note ids at capture

A captured note must be editable and deletable before the service syncs it, and a crash between sync and cleanup must not duplicate it. gkeepapi already generates node ids client-side (`"{:x}.{:016x}"`: ms timestamp, random 64-bit) and accepts `Node(id_=...)`, so the extension generates the id itself and every op references notes by Keep id. Idempotency becomes "skip `create` if `keep.get(id)` exists", which removes the client_id → note_id map.

## Consequences

- Depends on gkeepapi internals (id format, `id_` constructor param). Accepted: the project already depends on the unofficial API.
- `client_id` is no longer needed for idempotency: `update` and `delete` are idempotent by nature.
