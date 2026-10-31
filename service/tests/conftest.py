import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from gkeepapi import Keep

NOTE_ID = "18f2a9c3b10.3f9a0c1e2b4d5f60"
OTHER_ID = "18f2a9c3b11.0000000000000001"

WriteOp = Callable[..., Path]


@pytest.fixture
def keep() -> Keep:
    return Keep()


@pytest.fixture
def queue_dir(tmp_path: Path) -> Path:
    d = tmp_path / "queue"
    d.mkdir()
    return d


@pytest.fixture
def write_op(queue_dir: Path) -> WriteOp:
    """Write an op file the way the extension does. Names sort in call order."""
    counter = iter(range(1_700_000_000_000, 1_800_000_000_000))

    def write(op: str, note_id: str = NOTE_ID, raw: str | None = None, **fields: Any) -> Path:
        path = queue_dir / f"{next(counter)}-abcd1234.json"
        body = {"op": op, "note_id": note_id, **fields}
        path.write_text(raw if raw is not None else json.dumps(body))
        return path

    return write
