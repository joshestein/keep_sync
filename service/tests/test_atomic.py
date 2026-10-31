import json
from pathlib import Path

import pytest

from keep_sync import atomic
from keep_sync.atomic import write_json_atomic


def test_writes_and_replaces(tmp_path: Path) -> None:
    path = tmp_path / "cache.json"
    write_json_atomic(path, {"v": 1})
    write_json_atomic(path, {"v": 2})
    assert json.loads(path.read_text()) == {"v": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["cache.json"]


def test_failure_keeps_old_file_and_removes_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cache.json"
    write_json_atomic(path, "old")

    def crash(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(atomic.os, "replace", crash)
    with pytest.raises(OSError):
        write_json_atomic(path, "new")

    assert json.loads(path.read_text()) == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["cache.json"]
