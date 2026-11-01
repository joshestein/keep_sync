"""The plain-text form of a Keep list: one item per line, as "- [ ] text" or "- [x] text".

The Mac edits a list as this text. The same rules are in raycast/src/lib/checklist.ts, and
both sides test the same cases.
"""

import re
from dataclasses import dataclass

from gkeepapi.node import List, ListItem

# Lenient: "- [ ] a", "-[] a", "- [X] a". Leading whitespace indents the item.
TODO_RE = re.compile(r"^([ \t]*)-[ \t]*\[([ xX]?)\][ \t]?(.*)$")
INDENT = "  "


@dataclass(frozen=True)
class Item:
    text: str
    checked: bool
    indented: bool


def lines(text: str) -> list[str]:
    """The non-empty lines. CRLF and CR count as line breaks, and only spaces and tabs count as blank."""
    return [line for line in re.split(r"\r\n|\r|\n", text) if line.strip(" \t")]


def parse(text: str) -> list[Item]:
    """Every non-empty line is an item. A line with no checkbox is an unchecked item.

    An indented line goes under the item above it. Keep allows one level, so the first item cannot be indented.
    """
    items: list[Item] = []
    for line in lines(text):
        if m := TODO_RE.match(line):
            indent, mark, body = m.groups()
            checked, indented = mark in ("x", "X"), bool(indent)
        else:
            body, checked, indented = line.lstrip(" \t"), False, line[0] in " \t"
        items.append(Item(body, checked, indented and bool(items)))
    return items


def is_checklist(text: str) -> bool:
    """True if every non-empty line has a checkbox, and there is at least one. Capture then makes a list."""
    nonempty = lines(text)
    return bool(nonempty) and all(TODO_RE.match(line) for line in nonempty)


def format_items(items: list[ListItem]) -> str:
    return "\n".join(
        f"{INDENT if i.indented else ''}- [{'x' if i.checked else ' '}] {i.text}" for i in items
    )


def set_items(lst: List, wanted: list[Item]) -> None:
    """Replace the items of lst with wanted. If they are already the same, change nothing, so a replay is a no-op."""
    if [Item(i.text, i.checked, i.indented) for i in lst.items] == wanted:
        return
    for old in lst.items:
        old.delete()
        # gkeepapi's delete() does not mark the node dirty, so sync would not send it.
        old.touch(True)
    # Keep shows items by sortValue, highest first.
    parent: ListItem | None = None
    for k, w in enumerate(wanted):
        node = lst.add(w.text, w.checked, (len(wanted) - k) * List.SORT_DELTA)
        if w.indented and parent is not None:
            parent.indent(node)
        else:
            parent = node
