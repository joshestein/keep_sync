"""Apply queued ops to the local gkeepapi model."""

import hashlib
import logging
from pathlib import Path

from gkeepapi import Keep
from gkeepapi.node import List, Note, TopLevelNode

from keep_sync.queue import InvalidOp, Op, list_op_files, move_to_failed, parse_op

log = logging.getLogger(__name__)


def _is_gone(node: TopLevelNode | None) -> bool:
    return node is None or node.trashed or node.deleted


def create_note(keep: Keep, title: str, text: str, note_id: str) -> Note:
    # gkeepapi annotates **kwargs as dict, so the checker rejects a str id_.
    note = Note(id_=note_id)  # pyright: ignore[reportArgumentType]
    note.title = title
    note.text = text
    keep.add(note)
    return note


def fallback_id(note_id: str) -> str:
    """gkeepapi-format id for the note that replaces a gone note. Same note id, same fallback id.

    Every update to one gone note goes to one fallback note, so replays and repeated edits make no duplicates.
    Keep treats the id as opaque, so the 'ms' part is a hash, not a time.
    """
    h = hashlib.sha256(f"fallback:{note_id}".encode()).hexdigest()
    return f"{int(h[:10], 16):x}.{h[10:26]}"


def apply_op(keep: Keep, op: Op) -> None:
    """Apply one op. Every op is idempotent, so a crash before cleanup is safe to replay."""
    node = keep.get(op.note_id)
    match op.kind:
        case "create":
            if node is None:
                create_note(keep, op.title, op.text, op.note_id)
        case "update":
            # Follow the chain of fallbacks: the fallback note itself can be trashed later.
            note_id = op.note_id
            while _is_gone(node):
                note_id = fallback_id(note_id)
                node = keep.get(note_id)
                if node is None:
                    create_note(keep, op.title, op.text, note_id)
                    log.warning("update for missing or trashed note %s: created %s", op.note_id, note_id)
                    return
            if isinstance(node, List):
                raise InvalidOp("cannot update a list")
            # Skip unchanged fields so a replayed op does not touch the note.
            if node.title != op.title:
                node.title = op.title
            if node.text != op.text:
                node.text = op.text
        case "delete":
            if not _is_gone(node):
                node.trash()


def apply_queue(keep: Keep, queue_dir: Path) -> list[Path]:
    """Apply all queued ops in order. Return the applied files; move failed ones to failed/."""
    applied = []
    for path in list_op_files(queue_dir):
        try:
            apply_op(keep, parse_op(path))
        except Exception:
            log.exception("failed op %s", path.name)
            try:
                move_to_failed(path)
            except OSError:
                log.exception("could not move %s to failed/", path.name)
        else:
            applied.append(path)
    return applied
