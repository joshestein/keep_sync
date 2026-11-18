"""The Inbox: captures and appends from other programs, one JSON file each (ADR 0004).

A caller writes `<name>.json.part`, renames it to `<name>.json`, then touches `queue/sync-now`.
A file with no `append_to` becomes a `create` op at the start of a round, with no network.
A file with `append_to` becomes an `update` op after a sync, so it builds on the newest note.
"""

import json
import logging
from collections.abc import Iterator
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
    """Unknown fields are ignored, so callers can add fields. An OSError is not caught: it can be temporary."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
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


class Inbox:
    def __init__(self, dir: Path) -> None:
        self.dir = dir
        self.failed_dir = dir / "failed"
        # Files whose op is in the queue but whose delete failed. Without this, each round queues them again.
        # Only for this process: a restart can make one more copy.
        self._stuck: set[str] = set()

    def files(self) -> list[Path]:
        """Inbox files in name order. Other names, for example `*.json.part`, are not finished."""
        return sorted(p for p in self.dir.glob("*.json") if p.is_file())

    def failed(self) -> list[Path]:
        return sorted(p for p in self.failed_dir.glob("*.json") if p.is_file())

    def ingest_creates(self, queue_dir: Path, now_ms: int) -> None:
        """Turn each file with no `append_to` into a `create` op. Needs no network."""
        for path, item in self._items():
            if item.append_to is None:
                op = Op("create", mint_note_id(now_ms), "", item.text)
                if self._queue(path, queue_dir, op, now_ms) is None:
                    return

    def ingest_appends(self, keep: Keep, queue_dir: Path, now_ms: int) -> list[Path]:
        """Turn each file with `append_to` into an `update` op, and apply it. Return the op files.

        Call only after a sync, so the text builds on the newest note and on the queued ops (ADR 0004).
        """
        written: list[Path] = []
        for path, item in self._items():
            if item.append_to is None:
                continue
            node = keep.get(item.append_to)
            if node is None or node.trashed or node.deleted:
                log.warning(
                    "failed inbox file %s: note %s is missing or trashed",
                    path.name,
                    item.append_to,
                )
                self._fail(path)
                continue
            # An archived note is still a valid target: the caller named it by id.
            try:
                op = Op("update", node.id, node.title, appended_text(node, item.text))
            except Exception:
                # A bug, not a bad file. In the inbox, it would fail every round.
                log.exception("failed inbox file %s", path.name)
                self._fail(path)
                continue
            op_path = self._queue(path, queue_dir, op, now_ms)
            if op_path is None:
                break
            # Before the next file, so a second append to this note builds on this one.
            # If this raises, the round fails once. The op is in the queue, so the next round applies it.
            apply_op(keep, op)
            written.append(op_path)
        return written

    def _items(self) -> Iterator[tuple[Path, InboxItem]]:
        """The valid files. One bad file does not stop the others."""
        for path in self.files():
            if path.name in self._stuck:
                continue
            try:
                item = parse_inbox_file(path)
            except OSError as e:
                # Maybe temporary. The file stays, and the next round tries again.
                log.warning("cannot read inbox file %s: %s", path.name, e)
                continue
            except InvalidInboxFile as e:
                # Permanent: in the inbox, it would log every round.
                log.warning("failed inbox file %s: %s", path.name, e)
                self._fail(path)
                continue
            yield path, item

    def _queue(self, path: Path, queue_dir: Path, op: Op, now_ms: int) -> Path | None:
        """Write the op, then delete the inbox file. None if the op could not be written."""
        try:
            op_path = write_op(queue_dir, op, now_ms)
        except OSError:
            # Maybe temporary, for example a full disk. The file stays, and the next round tries again.
            log.exception("cannot queue inbox file %s", path.name)
            return None
        # Only after the op is in the queue. A crash before this line makes a second copy. Accepted (ADR 0004).
        try:
            path.unlink()
        except OSError:
            log.exception("cannot remove inbox file %s: skipped until restart", path.name)
            self._stuck.add(path.name)
        return op_path

    def _fail(self, path: Path) -> None:
        try:
            move_to_failed(path)
        except OSError:
            log.exception("cannot move inbox file %s to failed: skipped until restart", path.name)
            self._stuck.add(path.name)
