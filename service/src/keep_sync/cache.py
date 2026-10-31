"""cache.json: every note the Mac shows, plus sync status. Written only by the service."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from gkeepapi import Keep
from gkeepapi.node import List, TopLevelNode

from keep_sync.atomic import write_json_atomic

CACHE_VERSION = 1

ErrorKind = Literal["auth", "network", "other"]


@dataclass(frozen=True)
class SyncError:
    kind: ErrorKind
    message: str


@dataclass(frozen=True)
class Status:
    synced_at: datetime | None
    last_attempt_at: datetime | None
    error: SyncError | None


def iso(dt: datetime | None) -> str | None:
    """Same format as JS Date.toISOString(). gkeepapi datetimes are always UTC-aware."""
    if dt is None:
        return None
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def note_to_dict(node: TopLevelNode) -> dict[str, Any]:
    is_list = isinstance(node, List)
    return {
        "id": node.id,
        "kind": "list" if is_list else "note",
        "title": node.title,
        "text": "\n".join(i.text for i in node.items) if is_list else node.text,
        "items": [{"text": i.text, "checked": i.checked} for i in node.items] if is_list else None,
        "pinned": node.pinned,
        "archived": node.archived,
        "color": node.color.value,
        "labels": sorted(label.name for label in node.labels.all()),
        "updated": iso(node.timestamps.updated),
        "url": node.url,
    }


def serialize_notes(keep: Keep) -> list[dict[str, Any]]:
    return [note_to_dict(n) for n in keep.all() if not n.trashed and not n.deleted]


def read_cached_notes(path: Path) -> list[dict[str, Any]]:
    """The notes in the current cache.json, or [] if there is no usable file."""
    try:
        notes = json.loads(path.read_text(encoding="utf-8"))["notes"]
    except (OSError, ValueError, TypeError, KeyError):
        return []
    return notes if isinstance(notes, list) else []


def write_cache(path: Path, notes: list[dict[str, Any]], status: Status) -> None:
    error = status.error
    write_json_atomic(
        path,
        {
            "version": CACHE_VERSION,
            "synced_at": iso(status.synced_at),
            "last_attempt_at": iso(status.last_attempt_at),
            "error": {"kind": error.kind, "message": error.message} if error else None,
            "notes": notes,
        },
    )
