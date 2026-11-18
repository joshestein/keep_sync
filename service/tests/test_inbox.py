from pathlib import Path

import pytest
from gkeepapi import Keep
from gkeepapi.node import List, TopLevelNode

from keep_sync import checklist
from keep_sync import inbox as inbox_module
from keep_sync.apply import apply_op, create_note
from keep_sync.inbox import Inbox, InvalidInboxFile, appended_text, parse_inbox_file
from keep_sync.queue import NOTE_ID_RE, Op, list_op_files, parse_op

from .conftest import OTHER_ID, WriteInbox

NOW_MS = 1_794_830_400_000


@pytest.fixture
def inbox(inbox_dir: Path) -> Inbox:
    return Inbox(inbox_dir)


def queued_ops(queue_dir: Path) -> list[Op]:
    return [parse_op(p) for p in list_op_files(queue_dir)]


def failed_names(inbox: Inbox) -> list[str]:
    return [p.name for p in inbox.failed()]


def test_create_without_append_to(inbox: Inbox, queue_dir: Path, write_inbox: WriteInbox) -> None:
    path = write_inbox(text="  buy milk\n")

    inbox.ingest_creates(queue_dir, NOW_MS)

    [op] = queued_ops(queue_dir)
    assert (op.kind, op.title, op.text) == ("create", "", "buy milk")
    assert NOTE_ID_RE.fullmatch(op.note_id)
    assert op.note_id.startswith(f"{NOW_MS:x}.")
    assert not path.exists()


def test_creates_skip_appends(inbox: Inbox, queue_dir: Path, write_inbox: WriteInbox) -> None:
    path = write_inbox(text="later", append_to=OTHER_ID)
    inbox.ingest_creates(queue_dir, NOW_MS)
    assert queued_ops(queue_dir) == []
    assert path.exists()


def test_ops_sort_after_queued_ops(inbox: Inbox, queue_dir: Path, write_inbox: WriteInbox) -> None:
    """A clock step back must not put an inbox op before an op already in the queue."""
    future = queue_dir / "1900000000000-abcd1234.json"
    future.write_text('{"op": "delete", "note_id": "x"}')
    write_inbox(text="a")
    write_inbox(text="b")

    inbox.ingest_creates(queue_dir, NOW_MS)

    paths = list_op_files(queue_dir)
    assert paths[0] == future
    assert [parse_op(p).text for p in paths[1:]] == ["a", "b"]


def test_append_to_text_note(inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox) -> None:
    create_note(keep, "Ideas", "first\nsecond\n", OTHER_ID)
    path = write_inbox(text="try the new parser", append_to=OTHER_ID)

    written = inbox.ingest_appends(keep, queue_dir, NOW_MS)

    assert queued_ops(queue_dir) == [Op("update", OTHER_ID, "Ideas", "first\nsecond\ntry the new parser")]
    assert written == list_op_files(queue_dir)
    # Applied to the model, so a second append builds on it.
    assert keep.get(OTHER_ID).text == "first\nsecond\ntry the new parser"
    assert not path.exists()


def test_append_to_empty_note_has_no_leading_newline(
    inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox
) -> None:
    create_note(keep, "T", "", OTHER_ID)
    write_inbox(text="only", append_to=OTHER_ID)
    inbox.ingest_appends(keep, queue_dir, NOW_MS)
    assert queued_ops(queue_dir)[0].text == "only"


def test_append_to_list_adds_one_unchecked_item(
    inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox
) -> None:
    node = create_note(keep, "Shop", "- [x] eggs\n  - [ ] large\n- [ ] milk", OTHER_ID)
    assert isinstance(node, List)
    ids = [i.id for i in node.items]
    write_inbox(text="bread\nand butter", append_to=OTHER_ID)

    inbox.ingest_appends(keep, queue_dir, NOW_MS)

    [op] = queued_ops(queue_dir)
    assert op.text == "- [x] eggs\n  - [ ] large\n- [ ] milk\n- [ ] bread and butter"
    # Only the new item is added: the push leaves the other items alone.
    assert [i.id for i in node.items][:3] == ids
    assert checklist.format_items(node.items) == op.text
    # A replay after a failed sync changes nothing.
    apply_op(keep, op)
    assert [i.id for i in node.items][:3] == ids
    assert [(i.text, i.checked, i.indented) for i in node.items] == [
        ("eggs", True, False),
        ("large", False, True),
        ("milk", False, False),
        ("bread and butter", False, False),
    ]


def test_two_appends_to_one_note_both_stay(inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox) -> None:
    create_note(keep, "T", "a", OTHER_ID)
    write_inbox(text="b", append_to=OTHER_ID)
    write_inbox(text="c", append_to=OTHER_ID)

    inbox.ingest_appends(keep, queue_dir, NOW_MS)

    assert [op.text for op in queued_ops(queue_dir)] == ["a\nb", "a\nb\nc"]


def test_append_to_archived_note(inbox: Inbox, keep: Keep, queue_dir: Path, write_inbox: WriteInbox) -> None:
    create_note(keep, "T", "a", OTHER_ID).archived = True
    write_inbox(text="b", append_to=OTHER_ID)
    inbox.ingest_appends(keep, queue_dir, NOW_MS)
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

    assert inbox.ingest_appends(keep, queue_dir, NOW_MS) == []

    assert queued_ops(queue_dir) == []
    assert failed_names(inbox) == [path.name]
    assert ok.exists()


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
    path = write_inbox(
        text="a",
        append_to=None,
        capture="x",
        captured_at="2026-11-16T12:00:00Z",
        extra=[1],
    )
    item = parse_inbox_file(path)
    assert (item.text, item.append_to) == ("a", None)


def test_bad_files_fail_and_do_not_block_others(inbox: Inbox, queue_dir: Path, write_inbox: WriteInbox) -> None:
    bad = write_inbox(raw="{not json")
    empty = write_inbox(text="")
    write_inbox(text="good")

    inbox.ingest_creates(queue_dir, NOW_MS)

    assert [op.text for op in queued_ops(queue_dir)] == ["good"]
    assert failed_names(inbox) == [bad.name, empty.name]
    assert inbox.files() == []


def test_unfinished_and_other_files_are_ignored(inbox: Inbox, queue_dir: Path, write_inbox: WriteInbox) -> None:
    part = write_inbox(name="a.json.part", text="half")
    other = write_inbox(name="notes.txt", text="x")

    inbox.ingest_creates(queue_dir, NOW_MS)

    assert queued_ops(queue_dir) == []
    assert part.exists() and other.exists()
    assert not inbox.failed_dir.exists()


def test_read_error_keeps_the_file(inbox: Inbox, queue_dir: Path, write_inbox: WriteInbox) -> None:
    """A read error can be temporary: the file stays for the next round."""
    path = write_inbox(text="a")
    path.chmod(0)
    try:
        inbox.ingest_creates(queue_dir, NOW_MS)
    finally:
        path.chmod(0o644)
    assert path.exists()
    assert inbox.failed() == []

    inbox.ingest_creates(queue_dir, NOW_MS)
    assert [op.text for op in queued_ops(queue_dir)] == ["a"]


def test_append_build_error_fails_only_that_file(
    inbox: Inbox,
    keep: Keep,
    queue_dir: Path,
    write_inbox: WriteInbox,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_note(keep, "T", "a", OTHER_ID)
    bad = write_inbox(text="boom", append_to=OTHER_ID)
    write_inbox(text="b", append_to=OTHER_ID)
    real = inbox_module.appended_text

    def appended_text(node: TopLevelNode, text: str) -> str:
        if text == "boom":
            raise ValueError("bug")
        return real(node, text)

    monkeypatch.setattr(inbox_module, "appended_text", appended_text)

    inbox.ingest_appends(keep, queue_dir, NOW_MS)

    assert [op.text for op in queued_ops(queue_dir)] == ["a\nb"]
    assert failed_names(inbox) == [bad.name]


def test_failed_files_with_one_name_are_all_kept(inbox: Inbox, queue_dir: Path, write_inbox: WriteInbox) -> None:
    for _ in range(2):
        write_inbox(name="capture.json", raw="{bad")
        inbox.ingest_creates(queue_dir, NOW_MS)
    assert len(inbox.failed()) == 2


def test_write_failure_keeps_the_file(inbox: Inbox, tmp_path: Path, write_inbox: WriteInbox) -> None:
    path = write_inbox(text="a")
    inbox.ingest_creates(tmp_path / "no-such-dir", NOW_MS)
    assert path.exists()


def test_appended_text_trims_trailing_whitespace_of_old_text(keep: Keep) -> None:
    node = create_note(keep, "T", "a  \n\n", OTHER_ID)
    assert appended_text(node, "b") == "a\nb"
