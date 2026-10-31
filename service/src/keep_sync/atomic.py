import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, obj: Any) -> None:
    """Replace path with obj as JSON. Readers see the old file or the new file, never a partial one."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
