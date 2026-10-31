import type { Note } from "./store";

/** Notes whose title or text contains every word of the query, ignoring case. Keeps the input order. */
export function filterNotes(notes: Note[], query: string): Note[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return notes;
  return notes.filter((n) => {
    const haystack = `${n.title}\n${n.text}`.toLowerCase();
    return words.every((w) => haystack.includes(w));
  });
}

/** The list row title: the note title, else its first non-empty line. */
export function displayTitle(note: Note): string {
  return (
    note.title.trim() ||
    note.text
      .split("\n")
      .find((line) => line.trim())
      ?.trim() ||
    "Untitled"
  );
}
