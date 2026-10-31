"""state.json: the gkeepapi model dump. Written and read only by the service."""

import json
import logging
from pathlib import Path

from gkeepapi import Keep

from keep_sync.atomic import write_json_atomic

log = logging.getLogger(__name__)

_EMPTY_STATE = {"keep_version": None, "labels": [], "nodes": []}


def load_state(keep: Keep, path: Path) -> bool:
    """Restore the model from path. Return False if there is no usable state.

    On False the model is empty, so ops must not be applied until a full sync fills it.
    Otherwise an update to a phone note would make a duplicate and a delete would be lost.
    """
    try:
        keep.restore(json.loads(path.read_text(encoding="utf-8")))
        return True
    except FileNotFoundError:
        log.info("no %s: full sync before applying ops", path.name)
    except Exception:
        log.exception("cannot restore %s: full sync before applying ops", path.name)
    # A failed restore can leave a partial model. Reset it.
    keep.restore(_EMPTY_STATE)
    return False


def save_state(keep: Keep, path: Path) -> None:
    write_json_atomic(path, keep.dump())
