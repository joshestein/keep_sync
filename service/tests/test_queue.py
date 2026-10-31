from pathlib import Path

import pytest

from keep_sync.queue import InvalidOp, Op, list_op_files, move_to_failed, parse_op, remove_ops

from .conftest import NOTE_ID, WriteOp


def test_lists_in_name_order_and_skips_other_files(queue_dir: Path, write_op: WriteOp) -> None:
    first = write_op("create", title="", text="a")
    second = write_op("delete")
    (queue_dir / ".1700000000005-ffff0000.json.tmp").write_text("{}")
    (queue_dir / ".hidden.json").write_text("{}")
    (queue_dir / "notes.json").write_text("{}")
    (queue_dir / "failed").mkdir()
    assert list_op_files(queue_dir) == [first, second]


def test_parses_create(write_op: WriteOp) -> None:
    path = write_op("create", title="T", text="body")
    assert parse_op(path) == Op(kind="create", note_id=NOTE_ID, title="T", text="body")


def test_title_defaults_to_empty(write_op: WriteOp) -> None:
    assert parse_op(write_op("create", text="body")).title == ""


def test_delete_needs_no_title_or_text(write_op: WriteOp) -> None:
    assert parse_op(write_op("delete")).kind == "delete"


def test_delete_ignores_title_and_text(write_op: WriteOp) -> None:
    op = parse_op(write_op("delete", title=None, text=3))
    assert (op.title, op.text) == ("", "")


def test_update_accepts_server_style_ids(write_op: WriteOp) -> None:
    """Notes made on the phone can have ids in another format."""
    assert parse_op(write_op("update", note_id="abc123", title="", text="x")).note_id == "abc123"


@pytest.mark.parametrize(
    ("op", "note_id", "raw", "fields"),
    [
        ("create", NOTE_ID, "{not json", {}),
        ("create", NOTE_ID, "[]", {}),
        ("archive", NOTE_ID, None, {}),
        ("create", "", None, {"text": "x"}),
        ("create", "not-a-keep-id", None, {"text": "x"}),
        ("create", NOTE_ID + "\n", None, {"text": "x"}),
        ("update", NOTE_ID, None, {"text": 3}),
        ("create", NOTE_ID, None, {"title": None, "text": "x"}),
    ],
)
def test_rejects_invalid(write_op: WriteOp, op: str, note_id: str, raw: str | None, fields: dict) -> None:
    with pytest.raises(InvalidOp):
        parse_op(write_op(op, note_id=note_id, raw=raw, **fields))


def test_move_to_failed_and_remove(queue_dir: Path, write_op: WriteOp) -> None:
    bad = write_op("create", raw="{")
    good = write_op("delete")
    move_to_failed(bad)
    assert (queue_dir / "failed" / bad.name).exists()
    remove_ops([good, good])
    assert list_op_files(queue_dir) == []
