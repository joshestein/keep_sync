"""The Inbox: captures and appends from other programs, one JSON file each (ADR 0004).

A caller writes `<name>.json.part`, renames it to `<name>.json`, then touches `queue/sync-now`.
After a sync, the service turns each file into an op in the queue. The op file wakes the next round, which sends it.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from gkeepapi import Keep
from gkeepapi.node import List, TopLevelNode

from keep_sync import checklist
from keep_sync.apply import apply_op
from keep_sync.queue import Op, mint_note_id, move_to_failed, write_op

log = logging.getLogger(__name__)


class InvalidInboxFile(Exception):
    """The file can never become an op."""


@dataclass(frozen=True)
class InboxItem:
    text: str
    # The note id to append to. None: make a new note.
    append_to: str | None


def parse_inbox_file(path: Path) -> InboxItem:
    """Unknown fields are ignored, so callers can add fields."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InvalidInboxFile(f"unreadable: {e}") from e
    if not isinstance(raw, dict):
        raise InvalidInboxFile("not an object")
    text = raw.get("text")
    text = text.strip() if isinstance(text, str) else ""
    if not text:
        raise InvalidInboxFile("text must be a non-empty string")
    append_to = raw.get("append_to")
    if append_to is not None and (not isinstance(append_to, str) or not append_to):
        raise InvalidInboxFile("append_to must be a non-empty string")
    return InboxItem(text, append_to)


def appended_text(node: TopLevelNode, text: str) -> str:
    """The note text with text added at the end. For a list, text becomes one new unchecked item."""
    if isinstance(node, List):
        old = checklist.format_items(node.items)
        # One file is one item: a newline in text would make more items.
        new = f"- [ ] {' '.join(text.split())}"
    else:
        old, new = node.text, text
    # A trailing newline in the old text would put a blank line before the new text.
    old = old.rstrip()
    return f"{old}\n{new}" if old else new


def to_op(keep: Keep, item: InboxItem, now_ms: int) -> Op:
    if item.append_to is None:
        return Op("create", mint_note_id(now_ms), "", item.text)
    node = keep.get(item.append_to)
    # An archived note is still a valid target: the caller named it by id.
    if node is None or node.trashed or node.deleted:
        raise InvalidInboxFile(f"note {item.append_to} is missing or trashed")
    return Op("update", node.id, node.title, appended_text(node, item.text))


class Inbox:
    def __init__(self, dir: Path) -> None:
        self.dir = dir
        self.failed_dir = dir / "failed"

    def files(self) -> list[Path]:
        """Inbox files in name order. Other names, for example `*.json.part`, are not finished."""
        return sorted(p for p in self.dir.glob("*.json") if p.is_file())

    def failed(self) -> list[Path]:
        return sorted(p for p in self.failed_dir.glob("*.json") if p.is_file())

    def ingest(self, keep: Keep, queue_dir: Path) -> None:
        """Turn each file into an op in the queue. Call only after a sync, so an append builds on the newest note."""
        now_ms = time.time_ns() // 1_000_000
        for i, path in enumerate(self.files()):
            try:
                op = to_op(keep, parse_inbox_file(path), now_ms)
            except InvalidInboxFile as e:
                log.warning("failed inbox file %s: %s", path.name, e)
                move_to_failed(path)
                continue
            # One ms apart, so the ops apply in file order.
            write_op(queue_dir, op, now_ms + i)
            path.unlink()
            # So a second append to this note builds on this one.
            apply_op(keep, op)
