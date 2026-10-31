import type { Note } from "./store";

/**
 * Show plain Keep text exactly as written. Keep does not render markdown, so every markdown
 * character is escaped, line breaks are kept, and leading spaces cannot start a code block.
 */
export function escapeMarkdown(text: string): string {
  return text
    .split("\n")
    .map((line) =>
      line.replace(/[\\`*_{}[\]()#+\-.!|<>~=]/g, "\\$&").replace(/^ +/, (spaces) => " ".repeat(spaces.length)),
    )
    .join("  \n");
}

export function renderNote(note: Note): string {
  const title = note.title.trim() ? `# ${escapeMarkdown(note.title)}\n\n` : "";
  const body = note.items
    ? note.items.map((item) => `- [${item.checked ? "x" : " "}] ${escapeMarkdown(item.text)}`).join("\n")
    : escapeMarkdown(note.text);
  return title + body;
}
