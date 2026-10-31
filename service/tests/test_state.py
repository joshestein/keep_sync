import json
from pathlib import Path

from gkeepapi import Keep

from keep_sync.apply import create_note
from keep_sync.state import load_state, save_state

from .conftest import NOTE_ID


def test_round_trip(keep: Keep, tmp_path: Path) -> None:
    create_note(keep, "T", "body", NOTE_ID)
    path = tmp_path / "state.json"
    save_state(keep, path)

    restored = Keep()
    assert load_state(restored, path)
    assert restored.get(NOTE_ID).text == "body"


def test_missing_file_gives_empty_model(keep: Keep, tmp_path: Path) -> None:
    assert not load_state(keep, tmp_path / "state.json")
    assert keep.all() == []


def test_bad_state_resets_partial_model(keep: Keep, tmp_path: Path) -> None:
    create_note(keep, "", "stale", NOTE_ID)
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"labels": [], "nodes": [{"bad": 1}], "keep_version": "v"}))

    assert not load_state(keep, path)
    assert keep.all() == []


def test_corrupt_json(keep: Keep, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{")
    assert not load_state(keep, path)
