import json
from datetime import UTC, datetime
from pathlib import Path

from gkeepapi import Keep

from keep_sync.apply import create_note
from keep_sync.cache import CACHE_VERSION, Status, SyncError, iso, read_cached_notes, serialize_notes, write_cache

from .conftest import NOTE_ID, OTHER_ID


def test_serializes_notes_and_lists_and_skips_trashed(keep: Keep) -> None:
    note = create_note(keep, "T", "body", NOTE_ID)
    note.pinned = True
    keep.createList("L", [("a", False), ("b", True)])
    create_note(keep, "gone", "x", OTHER_ID).trash()

    notes = {n["title"]: n for n in serialize_notes(keep)}

    assert set(notes) == {"T", "L"}
    assert notes["T"]["kind"] == "note"
    assert notes["T"]["text"] == "body"
    assert notes["T"]["pinned"] is True
    assert notes["T"]["archived"] is False
    assert notes["T"]["color"] == "DEFAULT"
    assert notes["T"]["labels"] == []
    assert notes["T"]["url"].endswith(note.id)
    assert notes["T"]["updated"].endswith("Z")
    assert notes["L"]["kind"] == "list"
    assert notes["L"]["text"] == "- [ ] a\n- [x] b"


def test_includes_archived(keep: Keep) -> None:
    create_note(keep, "A", "x", NOTE_ID).archived = True
    [note] = serialize_notes(keep)
    assert note["archived"] is True


def test_iso_matches_js_format() -> None:
    assert iso(datetime(2026, 10, 29, 9, 14, 3, 120456, tzinfo=UTC)) == "2026-10-29T09:14:03.120Z"
    assert iso(None) is None


def test_write_cache(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    at = datetime(2026, 10, 29, tzinfo=UTC)
    notes = [{"id": "1", "title": "T"}]

    write_cache(path, notes, Status(synced_at=None, last_attempt_at=at, error=SyncError("auth", "revoked")))

    data = json.loads(path.read_text())
    assert data["version"] == CACHE_VERSION
    assert data["synced_at"] is None
    assert data["last_attempt_at"] == "2026-10-29T00:00:00.000Z"
    assert data["error"] == {"kind": "auth", "message": "revoked"}
    assert data["notes"] == notes



def test_read_cached_notes(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    assert read_cached_notes(path) == []
    path.write_text("{")
    assert read_cached_notes(path) == []
    path.write_text("[]")
    assert read_cached_notes(path) == []
    path.write_text('{"version": 1, "notes": [{"id": "1"}]}')
    assert read_cached_notes(path) == []
    write_cache(path, [{"id": "1"}], Status(None, None, None))
    assert read_cached_notes(path) == [{"id": "1"}]
