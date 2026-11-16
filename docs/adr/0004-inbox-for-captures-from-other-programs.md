# inbox/ takes captures and appends from other programs

Another program writes a JSON file to `inbox/<name>.json` and touches `queue/sync-now`. The service turns each file into an op in `queue/`, then deletes the file. A caller needs only a path, and the op format stays in two places. The service knows nothing about its callers.

The file is JSON, not plain text, so fields can be added later without a change to every caller. `text` is required. `append_to` names a note to append to. The service ignores fields it does not know.

Raycast stays on `queue/`. It needs the note id at capture time (ADR 0001), and it writes ops other than `create`.

## An append is an `update` op, not a new op kind

An `append` op kind would apply "add this line" at sync time. Rejected:

- It is not idempotent. The model lives across rounds, and each failed round applies the queue again, so an hour offline appends the line about 60 times. A fix needs a record of applied ops.
- It does not remove the need for a fresh copy. gkeepapi pushes the full note text, not a diff, so an append applied to a stale model still overwrites edits from other devices.
- Raycast's overlay treats every op except `delete` as a full replace, so a pending append would show the note as only the new line.

So the service builds the full new text (old text, a newline, the new text) and writes a normal `update` op.

## Creates before the network, appends after a sync

An `update` op replaces the full text, so the service must build it from the newest copy of the note. At the start of a round, the model can be minutes or hours old. A round does this:

1. Turn create files into `create` ops, with no network. Offline, a capture still reaches the queue, and the Mac shows it.
2. Apply the queue and sync. The model now holds the newest note, with the queued Raycast edits on it.
3. Turn append files into `update` ops, one at a time. Apply each op before the next file is read, so two appends to one note both stay. Then sync again.

An append waits in `inbox/` until a sync succeeds.

## Consequences

- A crash between the op write and the inbox delete makes a duplicate note or a duplicate line. Accepted.
- If the second sync fails, the append op stays in `queue/` with text built at that time. Edits made on another device before the next successful sync are overwritten. This is the same risk as a Raycast edit made from the cache. Accepted.
- An append to a missing, trashed, or deleted note goes to `inbox/failed/`. It does not follow the fallback chain that `update` ops follow. An archived note is a valid target.
