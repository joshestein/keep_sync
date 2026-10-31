"""The op queue: one JSON file per op in the queue directory (ADR 0002)."""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

OpKind = Literal["create", "update", "delete"]

# gkeepapi's client-side id format: "{ms:x}.{random64:016x}" (ADR 0001)
NOTE_ID_RE = re.compile(r"[0-9a-f]+\.[0-9a-f]{16}")


class InvalidOp(ValueError):
    """An op that can never succeed."""


@dataclass(frozen=True)
class Op:
    kind: OpKind
    note_id: str
    title: str
    text: str


def list_op_files(queue_dir: Path) -> list[Path]:
    """Op files in apply order. Names start with a ms timestamp. Temp files start with '.'."""
    return sorted(p for p in queue_dir.glob("*.json") if not p.name.startswith("."))


def parse_op(path: Path) -> Op:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise InvalidOp(f"unreadable: {e}") from e
    if not isinstance(raw, dict):
        raise InvalidOp("not an object")

    kind = raw.get("op")
    if kind not in get_args(OpKind):
        raise InvalidOp(f"unknown op: {kind!r}")
    note_id = raw.get("note_id")
    if not isinstance(note_id, str) or not note_id:
        raise InvalidOp("missing note_id")
    if kind == "create" and not NOTE_ID_RE.fullmatch(note_id):
        raise InvalidOp(f"bad note_id for create: {note_id!r}")

    title = raw.get("title", "")
    text = raw.get("text", "")
    if kind == "delete":
        title, text = "", ""
    elif not (isinstance(title, str) and isinstance(text, str)):
        raise InvalidOp("title and text must be strings")

    return Op(kind=cast(OpKind, kind), note_id=note_id, title=title, text=text)


def move_to_failed(path: Path) -> None:
    dest = path.parent / "failed"
    dest.mkdir(exist_ok=True)
    os.replace(path, dest / path.name)


def remove_ops(paths: list[Path]) -> None:
    for p in paths:
        p.unlink(missing_ok=True)
