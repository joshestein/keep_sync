import { parseChecklist } from "./checklist";
import type { Note } from "./store";

/**
 * Show plain Keep text exactly as written. Keep does not render markdown, so every markdown
 * character is escaped, line breaks are kept, and leading spaces and tabs cannot start a code block.
 */
export function escapeMarkdown(text: string): string {
  return text
    .split("\n")
    .map((line) =>
      line
        .replace(/[\\`*_{}[\]()#+\-.!|<>~=]/g, "\\$&")
        .replace(/^[ \t]+/, (indent) => indent.replace(/ /g, " ").replace(/\t/g, " ".repeat(4))),
    )
    .join("  \n");
}

export function renderNote(note: Note): string {
  const title = note.title.trim() ? `# ${escapeMarkdown(note.title)}\n\n` : "";
  const body =
    note.kind === "list"
      ? parseChecklist(note.text)
          .map((item) => `${item.indented ? "  " : ""}- [${item.checked ? "x" : " "}] ${escapeMarkdown(item.text)}`)
          .join("\n")
      : escapeMarkdown(note.text);
  return title + body;
}
