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

## Inbox files become ops after a sync

An `update` op replaces the full text, so it must build on the newest note. Each round:

1. Apply the queue and sync.
2. Turn each inbox file into an op in `queue/`, in name order. Apply each op to the model, so two appends to one note both stay.
3. The op files wake the queue watcher. The next round sends them.

Creates take the same path. Offline, a capture waits in `inbox/`.

## Consequences

One user, low edit rate. Accepted, not guarded:

- A crash between the op write and the inbox delete makes a duplicate.
- An append overwrites edits made between its sync and the next round: a Raycast edit queued during the sync, or an edit on another device.
- Files are processed in name order, not arrival order.
- A bad file goes to `inbox/failed/` at once and overwrites a failed file with the same name. Callers must write `.part`, then rename.
- An append to a missing, trashed, or deleted note goes to `inbox/failed/`. It does not follow the `update` fallback chain. An archived note is valid.
