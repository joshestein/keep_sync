import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from gkeepapi import Keep
from gkeepapi.node import List

from keep_sync.checklist import format_items, is_checklist, parse, set_items

# The same cases run in raycast/test/checklist.test.ts.
CASES: list[dict[str, Any]] = json.loads(
    (Path(__file__).parents[2] / "testdata" / "checklist-cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_cases(case: dict[str, Any]) -> None:
    assert [asdict(i) for i in parse(case["text"])] == case["items"]
    assert is_checklist(case["text"]) is case["is_checklist"]


def shape(lst: List) -> list[tuple[str, bool, str | None]]:
    """Items in Keep order: text, checked, and the text of the parent item."""
    return [(i.text, i.checked, i.parent_item.text if i.parent_item else None) for i in lst.items]


def test_format_round_trips() -> None:
    lst = Keep().createList("L", [("a", False), ("b", True), ("c", False)])
    lst.items[0].indent(lst.items[1])
    text = format_items(lst.items)
    assert text == "- [ ] a\n  - [x] b\n- [ ] c"
    assert [(i.text, i.checked, i.indented) for i in parse(text)] == [
        (i.text, i.checked, i.indented) for i in lst.items
    ]


def test_set_items_replaces_items_in_order() -> None:
    lst = Keep().createList("L", [("a", False), ("b", False)])
    old = lst.items
    set_items(lst, parse("- [x] b\n  - [ ] new\n  - [x] a\n- [ ] c"))
    assert shape(lst) == [("b", True, None), ("new", False, "b"), ("a", True, "b"), ("c", False, None)]
    assert all(i.deleted and i.dirty for i in old)


def test_set_items_with_same_items_changes_nothing() -> None:
    """A replayed op, or an edit that only changes the title, must not touch the items."""
    lst = Keep().createList("L", [("a", False), ("b", True)])
    set_items(lst, parse("- [ ] a\n  - [x] b"))
    items, updated = lst.items, lst.timestamps.updated

    set_items(lst, parse(format_items(lst.items)))

    assert lst.items == items
    assert lst.timestamps.updated == updated
