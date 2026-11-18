from pathlib import Path

import pytest
from gkeepapi import Keep
from gkeepapi.node import List

from keep_sync import checklist
from keep_sync.apply import apply_op, create_note
from keep_sync.inbox import Inbox, InboxItem, InvalidInboxFile, appended_text, parse_inbox_file
from keep_sync.queue import NOTE_ID_RE, Op, list_op_files, parse_op

from .conftest import OTHER_ID, WriteInbox


@pytest.fixture
def inbox(inbox_dir: Path) -> Inbox:
    return Inbox(inbox_dir)


def queued_ops(queue_dir: Path) -> list[Op]:
    return [parse_op(p) for p in list_op_files(queue_dir)]


def failed_names(inbox: Inbox) -> list[str]:
    return [p.name for p in inbox.failed()]


def test_create_without_append_to(inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox) -> None:
    path = write_inbox(text="  buy milk\n")

    inbox.ingest(keep, queue_dir)

    [op] = queued_ops(queue_dir)
    assert (op.kind, op.title, op.text) == ("create", "", "buy milk")
    assert NOTE_ID_RE.fullmatch(op.note_id)
    assert not path.exists()


def test_append_to_text_note(inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox) -> None:
    create_note(keep, "Ideas", "first\nsecond\n", OTHER_ID)
    path = write_inbox(text="try the new parser", append_to=OTHER_ID)

    inbox.ingest(keep, queue_dir)

    assert queued_ops(queue_dir) == [Op("update", OTHER_ID, "Ideas", "first\nsecond\ntry the new parser")]
    # Applied to the model, so a second append builds on it.
    assert keep.get(OTHER_ID).text == "first\nsecond\ntry the new parser"
    assert not path.exists()


def test_append_to_list_adds_one_unchecked_item(
    inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox
) -> None:
    node = create_note(keep, "Shop", "- [x] eggs\n  - [ ] large\n- [ ] milk", OTHER_ID)
    assert isinstance(node, List)
    ids = [i.id for i in node.items]
    write_inbox(text="bread\nand butter", append_to=OTHER_ID)

    inbox.ingest(keep, queue_dir)

    [op] = queued_ops(queue_dir)
    assert op.text == "- [x] eggs\n  - [ ] large\n- [ ] milk\n- [ ] bread and butter"
    assert checklist.format_items(node.items) == op.text
    # Only the new item is added, also on replay, so phone edits to other items stay.
    apply_op(keep, op)
    assert [i.id for i in node.items][:3] == ids


def test_two_appends_to_one_note_both_stay(inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox) -> None:
    create_note(keep, "T", "a", OTHER_ID)
    write_inbox(text="b", append_to=OTHER_ID)
    write_inbox(text="c", append_to=OTHER_ID)

    inbox.ingest(keep, queue_dir)

    assert [op.text for op in queued_ops(queue_dir)] == ["a\nb", "a\nb\nc"]


def test_append_to_archived_note(inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox) -> None:
    create_note(keep, "T", "a", OTHER_ID).archived = True
    write_inbox(text="b", append_to=OTHER_ID)
    inbox.ingest(keep, queue_dir)
    assert queued_ops(queue_dir)[0].text == "a\nb"


@pytest.mark.parametrize("state", ["missing", "trashed", "deleted"])
def test_append_to_gone_note_fails(
    inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox, state: str
) -> None:
    if state != "missing":
        node = create_note(keep, "T", "a", OTHER_ID)
        if state == "trashed":
            node.trash()
        else:
            node.delete()
    path = write_inbox(text="b", append_to=OTHER_ID)
    ok = write_inbox(text="c")

    inbox.ingest(keep, queue_dir)

    assert [op.kind for op in queued_ops(queue_dir)] == ["create"]
    assert failed_names(inbox) == [path.name]
    assert not ok.exists()


@pytest.mark.parametrize(
    ("raw", "fields"),
    [
        ("{not json", {}),
        ("[1]", {}),
        (None, {}),
        (None, {"text": ""}),
        (None, {"text": " \n "}),
        (None, {"text": 5}),
        (None, {"text": "a", "append_to": ""}),
        (None, {"text": "a", "append_to": 5}),
    ],
)
def test_parse_rejects(write_inbox: WriteInbox, raw: str | None, fields: dict) -> None:
    with pytest.raises(InvalidInboxFile):
        parse_inbox_file(write_inbox(raw=raw, **fields))


def test_parse_ignores_unknown_fields(write_inbox: WriteInbox) -> None:
    assert parse_inbox_file(write_inbox(text="a", extra=[1])) == InboxItem("a", None)


def test_bad_files_fail_and_do_not_block_others(
    inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox
) -> None:
    bad = write_inbox(raw="{not json")
    empty = write_inbox(text="")
    write_inbox(text="good")

    inbox.ingest(keep, queue_dir)

    assert [op.text for op in queued_ops(queue_dir)] == ["good"]
    assert failed_names(inbox) == [bad.name, empty.name]
    assert inbox.files() == []


def test_unfinished_and_other_files_are_ignored(
    inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox
) -> None:
    part = write_inbox(name="a.json.part", text="half")
    other = write_inbox(name="notes.txt", text="x")

    inbox.ingest(keep, queue_dir)

    assert queued_ops(queue_dir) == []
    assert part.exists() and other.exists()
    assert not inbox.failed_dir.exists()


@pytest.mark.parametrize(("old", "expected"), [("a", "a\nb"), ("a  \n\n", "a\nb"), ("", "b")])
def test_appended_text(keep: Keep, old: str, expected: str) -> None:
    assert appended_text(create_note(keep, "T", old, OTHER_ID), "b") == expected
