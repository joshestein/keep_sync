from pathlib import Path

import pytest
from gkeepapi import Keep
from gkeepapi.node import List, Note, TopLevelNode

from keep_sync import apply
from keep_sync.apply import SORT_STEP, apply_queue, create_note, fallback_id
from keep_sync.queue import Op, list_op_files

from .conftest import NOTE_ID, OTHER_ID, WriteOp


def live(keep: Keep) -> list[TopLevelNode]:
    return [n for n in keep.all() if not n.trashed]


def test_create_uses_client_minted_id(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    write_op("create", title="T", text="body")
    apply_queue(keep, queue_dir)
    note = keep.get(NOTE_ID)
    assert (note.title, note.text) == ("T", "body")


def test_replaying_the_queue_creates_no_duplicates(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    """Crash after sync, before the op files are removed: the next round applies them again."""
    write_op("create", title="", text="milk")
    write_op("update", title="Shopping", text="milk, eggs")
    apply_queue(keep, queue_dir)
    updated = keep.get(NOTE_ID).timestamps.updated

    apply_queue(keep, queue_dir)

    assert len(live(keep)) == 1
    assert keep.get(NOTE_ID).text == "milk, eggs"
    assert keep.get(NOTE_ID).timestamps.updated == updated


def test_create_after_phone_trashed_it_is_skipped(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    write_op("create", text="x")
    apply_queue(keep, queue_dir)
    keep.get(NOTE_ID).trash()

    apply_queue(keep, queue_dir)

    assert live(keep) == []


def test_update_existing(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    create_note(keep, "", "", OTHER_ID)
    write_op("update", note_id=OTHER_ID, title="new", text="body")
    apply_queue(keep, queue_dir)
    assert (keep.get(OTHER_ID).title, keep.get(OTHER_ID).text) == ("new", "body")


def test_update_missing_note_creates_one_new_note(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    """A replay of the same op must not create a second note."""
    write_op("update", note_id="gone", title="T", text="keep me")
    assert len(apply_queue(keep, queue_dir)) == 1
    apply_queue(keep, queue_dir)
    [note] = live(keep)
    assert note.id != "gone"
    assert note.text == "keep me"


def test_update_trashed_note_creates_new_note(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    create_note(keep, "", "old", OTHER_ID).trash()
    write_op("update", note_id=OTHER_ID, title="", text="new")

    apply_queue(keep, queue_dir)

    [note] = live(keep)
    assert note.id != OTHER_ID
    assert note.text == "new"
    assert keep.get(OTHER_ID).text == "old"


def test_edits_to_one_gone_note_make_one_new_note(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    """Phone trashes the note, Mac edits it twice before sync: one new note with the last edit."""
    create_note(keep, "", "old", OTHER_ID).trash()
    write_op("update", note_id=OTHER_ID, title="", text="edit 1")
    write_op("update", note_id=OTHER_ID, title="", text="edit 2")

    apply_queue(keep, queue_dir)
    apply_queue(keep, queue_dir)

    [note] = live(keep)
    assert note.id == fallback_id(OTHER_ID)
    assert note.text == "edit 2"


def test_update_after_fallback_note_trashed_makes_next_fallback(
    keep: Keep, queue_dir: Path, write_op: WriteOp
) -> None:
    write_op("update", note_id="gone", title="", text="first")
    apply_queue(keep, queue_dir)
    keep.get(fallback_id("gone")).trash()
    write_op("update", note_id="gone", title="", text="second")

    apply_queue(keep, queue_dir)

    [note] = live(keep)
    assert note.id == fallback_id(fallback_id("gone"))
    assert note.text == "second"


def test_create_all_todo_lines_makes_a_list(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    write_op("create", title="Shop", text="- [ ] milk\n  - [x] oat\n- [ ] eggs")
    apply_queue(keep, queue_dir)
    lst = keep.get(NOTE_ID)
    assert isinstance(lst, List)
    assert lst.title == "Shop"
    assert [(i.text, i.checked, i.indented) for i in lst.items] == [
        ("milk", False, False),
        ("oat", True, True),
        ("eggs", False, False),
    ]


def test_create_with_a_plain_line_makes_a_note(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    write_op("create", text="- [ ] milk\nthoughts")
    apply_queue(keep, queue_dir)
    assert isinstance(keep.get(NOTE_ID), Note)


def test_update_list_replaces_items(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    lst = keep.createList("L", [("a", False), ("b", False)])
    write_op("update", note_id=lst.id, title="L2", text="- [x] a\n- [ ] b\nc")
    apply_queue(keep, queue_dir)
    assert lst.title == "L2"
    assert [(i.text, i.checked) for i in lst.items] == [("a", True), ("b", False), ("c", False)]


def test_update_note_with_todo_text_stays_a_note(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    create_note(keep, "", "x", OTHER_ID)
    write_op("update", note_id=OTHER_ID, title="", text="- [ ] a")
    apply_queue(keep, queue_dir)
    note = keep.get(OTHER_ID)
    assert isinstance(note, Note)
    assert note.text == "- [ ] a"


def test_delete_trashes(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    create_note(keep, "", "", OTHER_ID)
    write_op("delete", note_id=OTHER_ID)
    apply_queue(keep, queue_dir)
    assert keep.get(OTHER_ID).trashed
    assert not keep.get(OTHER_ID).deleted


def test_delete_missing_is_noop(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    path = write_op("delete", note_id="gone")
    assert apply_queue(keep, queue_dir) == [path]
    assert keep.all() == []


def test_capture_then_delete_before_sync(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    write_op("create", text="oops")
    write_op("delete")
    apply_queue(keep, queue_dir)
    assert live(keep) == []


def test_failed_op_does_not_block_later_ops(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    bad = write_op("create", raw="{")
    good = write_op("create", text="after")

    applied = apply_queue(keep, queue_dir)

    assert applied == [good]
    assert keep.get(NOTE_ID).text == "after"
    assert list_op_files(queue_dir) == [good]
    assert (queue_dir / "failed" / bad.name).exists()


def test_failed_move_does_not_block_later_ops(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    (queue_dir / "failed").write_text("")  # a file, so mkdir fails
    bad = write_op("create", raw="{")
    good = write_op("create", text="after")

    assert apply_queue(keep, queue_dir) == [good]
    assert bad.exists()


def test_applied_files_stay_until_caller_removes_them(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    """The service removes op files only after sync and cache write succeed."""
    path = write_op("create", text="x")
    apply_queue(keep, queue_dir)
    assert path.exists()


def test_later_op_removes_older_failed_op_for_same_note(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    """A failed create the user trashes or edits must not stay in failed/ and come back in the overlay."""
    failed = write_op("create", text="x")
    other = write_op("create", note_id=OTHER_ID, text="y")
    (queue_dir / "failed").mkdir()
    for path in (failed, other):
        path.rename(queue_dir / "failed" / path.name)
    delete = write_op("delete")

    assert apply_queue(keep, queue_dir) == [delete, queue_dir / "failed" / failed.name]


def test_failed_op_newer_than_applied_op_stays(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    delete = write_op("delete")
    newer = write_op("create", text="x")
    (queue_dir / "failed").mkdir()
    newer.rename(queue_dir / "failed" / newer.name)

    assert apply_queue(keep, queue_dir) == [delete]


def test_later_op_removes_op_that_failed_in_same_run(
    keep: Keep, queue_dir: Path, write_op: WriteOp, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_note(keep, "", "x", OTHER_ID)
    bad = write_op("update", note_id=OTHER_ID, title="", text="boom")
    delete = write_op("delete", note_id=OTHER_ID)
    real_apply = apply.apply_op

    def apply_op(keep: Keep, op: Op) -> None:
        if op.text == "boom":
            raise RuntimeError("unexpected")
        real_apply(keep, op)

    monkeypatch.setattr(apply, "apply_op", apply_op)

    assert apply_queue(keep, queue_dir) == [delete, queue_dir / "failed" / bad.name]


def test_new_note_goes_to_top_of_custom_order(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    """Like Keep clients: highest sortValue plus a step. gkeepapi's default is random."""
    create_note(keep, "", "old", OTHER_ID).sort = 5_000_000_000
    write_op("create", text="new")
    apply_queue(keep, queue_dir)
    assert keep.get(NOTE_ID).sort == 5_000_000_000 + SORT_STEP
