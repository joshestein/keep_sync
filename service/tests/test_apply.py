from pathlib import Path

from gkeepapi import Keep
from gkeepapi.node import TopLevelNode

from keep_sync.apply import apply_queue, create_note, fallback_id
from keep_sync.queue import list_op_files

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


def test_update_list_fails(keep: Keep, queue_dir: Path, write_op: WriteOp) -> None:
    lst = keep.createList("L", [("a", False)])
    path = write_op("update", note_id=lst.id, title="L", text="a")
    assert apply_queue(keep, queue_dir) == []
    assert (queue_dir / "failed" / path.name).exists()


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
