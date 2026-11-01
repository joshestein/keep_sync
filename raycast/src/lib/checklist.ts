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
  for (const line of lines(text)) {
    const match = TODO.exec(line);
    const indented = match ? match[1] !== "" : /^[ \t]/.test(line);
    items.push({
      text: match ? match[3] : line.replace(/^[ \t]+/, ""),
      checked: match ? match[2] === "x" || match[2] === "X" : false,
      indented: indented && items.length > 0,
    });
  }
  return items;
}

/** The non-empty lines. CRLF and CR count as line breaks, and only spaces and tabs count as blank. */
function lines(text: string): string[] {
  return text.split(/\r\n|\r|\n/).filter((line) => /[^ \t]/.test(line));
}

/** True if every non-empty line has a checkbox, and there is at least one. A capture then makes a list. */
export function isChecklist(text: string): boolean {
  const nonempty = lines(text);
  return nonempty.length > 0 && nonempty.every((line) => TODO.test(line));
}
