"""Apply queued ops to the local gkeepapi model."""

import hashlib
import logging
from collections import defaultdict
from pathlib import Path

from gkeepapi import Keep
from gkeepapi.node import List, Note, TopLevelNode

from keep_sync import checklist
from keep_sync.queue import InvalidOp, Op, list_op_files, move_to_failed, parse_op

log = logging.getLogger(__name__)


def _is_gone(node: TopLevelNode | None) -> bool:
    return node is None or node.trashed or node.deleted


# Keep clients put a new note at the top of the custom order: the highest sortValue plus this step.
SORT_STEP = 2**20


def create_note(keep: Keep, title: str, text: str, note_id: str) -> Note | List:
    """A list if every line of text is a todo ("- [ ] a"), else a note."""
    # gkeepapi annotates **kwargs as dict, so the checker rejects a str id_.
    node = List(id_=note_id) if checklist.is_checklist(text) else Note(id_=note_id)  # pyright: ignore[reportArgumentType]
    # gkeepapi picks a random sortValue, which puts the note at a random place in Keep's custom order.
    node.sort = max((n.sort for n in keep.all()), default=0) + SORT_STEP
    node.title = title
    if isinstance(node, List):
        checklist.set_items(node, checklist.parse(text))
    else:
        node.text = text
    keep.add(node)
    return node


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
            # Skip unchanged fields so a replayed op does not touch the note.
            if node.title != op.title:
                node.title = op.title
            if isinstance(node, List):
                checklist.set_items(node, checklist.parse(op.text))
            elif node.text != op.text:
                node.text = op.text
        case "delete":
            if not _is_gone(node):
                node.trash()


def _failed_by_note(queue_dir: Path) -> dict[str, list[Path]]:
    """Failed op files by note id, oldest first. Unreadable failed ops have no note id and are left out."""
    failed_dir = queue_dir / "failed"
    by_note: dict[str, list[Path]] = defaultdict(list)
    if failed_dir.is_dir():
        for path in list_op_files(failed_dir):
            try:
                by_note[parse_op(path).note_id].append(path)
            except InvalidOp:
                continue
    return by_note


def _pop_older(paths: list[Path], than: Path) -> list[Path]:
    """Remove and return the paths whose names sort before than."""
    older = [p for p in paths if p.name < than.name]
    paths[:] = [p for p in paths if p.name >= than.name]
    return older


def apply_queue(keep: Keep, queue_dir: Path) -> list[Path]:
    """Apply all queued ops in order and move failed ones to failed/.

    Return the files to remove after sync: the applied ops and the older failed ops for the same note.
    A later op that applies replaces them. Without this, a failed op stays in the overlay for good:
    for example, a trashed failed create comes back.
    """
    failed = _failed_by_note(queue_dir)
    done = []
    for path in list_op_files(queue_dir):
        op = None
        try:
            op = parse_op(path)
            apply_op(keep, op)
        except Exception:
            log.exception("failed op %s", path.name)
            try:
                move_to_failed(path)
            except OSError:
                log.exception("could not move %s to failed/", path.name)
            else:
                if op is not None:
                    failed[op.note_id].append(path.parent / "failed" / path.name)
        else:
            done.append(path)
            done.extend(_pop_older(failed[op.note_id], path))
    return done
