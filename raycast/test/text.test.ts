import { describe, expect, it } from "vitest";

import { escapeMarkdown, renderNote } from "../src/lib/markdown";
import { displayTitle, filterNotes } from "../src/lib/search";
import type { Note } from "../src/lib/store";

const note = (fields: Partial<Note>): Note => ({
  id: "a",
  kind: "note",
  title: "",
  text: "",
  pinned: false,
  archived: false,
  color: "DEFAULT",
  labels: [],
  updated: "",
  url: "",
  state: "synced",
  ...fields,
});

describe("escapeMarkdown", () => {
  it("escapes markdown characters", () => {
    expect(escapeMarkdown("# 3 *items* [x](y)")).toBe("\\# 3 \\*items\\* \\[x\\]\\(y\\)");
    expect(escapeMarkdown("1. a - b")).toBe("1\\. a \\- b");
  });

  it("keeps line breaks and stops indented lines from becoming code", () => {
    expect(escapeMarkdown("a\n    b")).toBe("a  \n    b");
     expect(escapeMarkdown("a\n\t b")).toBe("a  \n     b");
  });
});

describe("renderNote", () => {
  it("renders title and escaped text", () => {
    expect(renderNote(note({ title: "T_1", text: "x" }))).toBe("# T\\_1\n\nx");
  });

  it("omits an empty title", () => {
    expect(renderNote(note({ text: "x" }))).toBe("x");
  });

  it("renders a checklist", () => {
    const list = note({ kind: "list", text: "- [ ] milk\n\toat\n-[x] [eggs]" });
    expect(renderNote(list)).toBe("- [ ] milk\n  - [ ] oat\n- [x] \\[eggs\\]");
  });
});

describe("list search and title", () => {
  const list = note({ kind: "list", text: "- [x] milk\n- [ ] eggs" });

  it("ignores the checkboxes", () => {
    expect(filterNotes([list], "x")).toEqual([]);
    expect(filterNotes([list], "eggs")).toEqual([list]);
    expect(displayTitle(list)).toBe("milk");
  });
});

describe("filterNotes", () => {
  const notes = [note({ id: "1", title: "Shopping", text: "milk eggs" }), note({ id: "2", text: "Call mom" })];
  const ids = (q: string) => filterNotes(notes, q).map((n) => n.id);

  it("matches every word in title or text, ignoring case", () => {
    expect(ids("shop EGGS")).toEqual(["1"]);
    expect(ids("mom")).toEqual(["2"]);
    expect(ids("milk mom")).toEqual([]);
    expect(ids("  ")).toEqual(["1", "2"]);
  });
});

describe("displayTitle", () => {
  it("falls back to the first non-empty line", () => {
    expect(displayTitle(note({ title: " T " }))).toBe("T");
    expect(displayTitle(note({ text: "\n  first\nsecond" }))).toBe("first");
    expect(displayTitle(note({}))).toBe("Untitled");
  });
});
