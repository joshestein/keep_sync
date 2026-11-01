import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { isChecklist, ListItem, parseChecklist } from "../src/lib/checklist";

interface Case {
  name: string;
  text: string;
  is_checklist: boolean;
  items: ListItem[];
}

// The same cases run in service/tests/test_checklist.py.
const CASES = JSON.parse(
  readFileSync(join(__dirname, "..", "..", "testdata", "checklist-cases.json"), "utf8"),
) as Case[];

describe("shared checklist cases", () => {
  it.each(CASES)("$name", ({ text, is_checklist, items }) => {
    expect(parseChecklist(text)).toEqual(items);
    expect(isChecklist(text)).toBe(is_checklist);
  });
});
