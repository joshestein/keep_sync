# Glossary

**Note**: A Google Keep note (title, text, pinned, archived, color, labels). Checklists are notes that the Mac shows read-only as text.

**Note id**: The Keep id of a note. The client that creates the note makes the id, not the Keep server. A note has its note id from the moment of capture.

**Capture**: To make a new note on the Mac. A capture never waits for the network.

**Op**: One requested change to a note: `create`, `update`, or `delete`. Every op names its note by note id.

**Delete**: To move a note to Keep's trash. A deleted note is recoverable in Keep for 7 days. The Mac never deletes a note permanently.

**Archived note**: A note that the user removed from the main Keep view without deleting it. The Mac shows it in search with a mark.

**Queue**: The ordered list of ops that the Mac has requested and Keep has not yet accepted.

**Pending note**: A note with one or more ops still in the queue. The Mac shows the result of those ops before Keep accepts them.

**Failed op**: An op that can never succeed, for example one that cannot be read. A failed op leaves the queue and does not block the ops after it. The Mac still shows it, so a capture is never lost without a sign.

**Cache**: The last copy of all notes that the Mac received from Keep.

**Sync**: One exchange with Keep: send the ops in the queue, then get the changes made on other devices.
