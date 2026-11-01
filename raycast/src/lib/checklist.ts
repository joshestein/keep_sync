/**
 * The plain-text form of a Keep list: one item per line, as "- [ ] text" or "- [x] text".
 * Same rules as service/src/keep_sync/checklist.py. Both sides test testdata/checklist-cases.json.
 */

export interface ListItem {
  text: string;
  checked: boolean;
  indented: boolean;
}

/** Lenient: "- [ ] a", "-[] a", "- [X] a". Leading whitespace indents the item. */
const TODO = /^([ \t]*)-[ \t]*\[([ xX]?)\][ \t]?(.*)$/;

/**
 * Every non-empty line is an item. A line with no checkbox is an unchecked item.
 * An indented line goes under the item above it. Keep allows one level, so the first item cannot be indented.
 */
export function parseChecklist(text: string): ListItem[] {
  const items: ListItem[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    const match = TODO.exec(line);
    const item = match
      ? { text: match[3], checked: match[2] === "x" || match[2] === "X", indented: match[1] !== "" }
      : { text: line.replace(/^[ \t]+/, ""), checked: false, indented: /^[ \t]/.test(line) };
    items.push({ ...item, indented: item.indented && items.length > 0 });
  }
  return items;
}

/** True if every non-empty line has a checkbox, and there is at least one. A capture then makes a list. */
export function isChecklist(text: string): boolean {
  const lines = text.split("\n").filter((line) => line.trim());
  return lines.length > 0 && lines.every((line) => TODO.test(line));
}
