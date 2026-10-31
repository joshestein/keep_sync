/**
 * Local files shared with the keep-sync service. This module never touches the network.
 * The extension writes only op files. The service writes everything else.
 */
import { randomBytes } from "node:crypto";
import { closeSync, fsyncSync, mkdirSync, openSync, readdirSync, readFileSync, renameSync, writeSync } from "node:fs";
import { join } from "node:path";

export const APP_DIR = join(homedir(), "Library", "Application Support", "keep-sync");

export type Op =
  { op: "create" | "update"; note_id: string; title: string; text: string } | { op: "delete"; note_id: string };

export interface CachedNote {
  id: string;
  kind: "note" | "list";
  title: string;
  text: string;
  items: { text: string; checked: boolean }[] | null;
  pinned: boolean;
  archived: boolean;
  color: string;
  labels: string[];
  updated: string;
  url: string;
}

export interface SyncStatus {
  synced_at: string | null;
  last_attempt_at: string | null;
  error: { kind: "auth" | "network" | "other"; message: string } | null;
}

interface Cache extends SyncStatus {
  version: 1;
  notes: CachedNote[];
}

/** "synced": as in the cache. "pending": ops still in the queue. "failed": an op in queue/failed. */
export interface Note extends CachedNote {
  state: "synced" | "pending" | "failed";
}

const OP_FILE = /^(\d+)-[0-9a-f]+\.json$/;

const queueDir = (appDir: string) => join(appDir, "queue");
const failedDir = (appDir: string) => join(queueDir(appDir), "failed");

export function noteUrl(id: string): string {
  return `https://keep.google.com/u/0/#NOTE/${id}`;
}

/** Write one op file: temp file, fsync, then rename, so the service never reads a partial op (ADR 0002). */
export function writeOp(op: Op, appDir = APP_DIR): void {
  const dir = join(appDir, "queue");
  mkdirSync(dir, { recursive: true });
  const name = `${Date.now()}-${randomBytes(4).toString("hex")}.json`;
  const tmp = join(dir, `.${name}.tmp`);
  writeFileSync(tmp, JSON.stringify(op), { mode: 0o600, flush: true });
  renameSync(tmp, join(dir, name));
}

/** Ops in a queue directory, in apply order. Unreadable files are skipped: the service moves them to failed/. */
export function readOps(dir: string): QueuedOp[] {
  let names: string[];
  try {
    names = readdirSync(dir).sort();
  } catch {
    return [];
  }
  return names.flatMap((name) => {
    const match = OP_FILE.exec(name);
    if (!match) return [];
    try {
      return [{ ms: Number(match[1]), op: JSON.parse(readFileSync(join(dir, name), "utf8")) as Op }];
    } catch {
      return [];
    }
  });
}

/** The cache with queued and failed ops applied on top, so captures and edits show at once. */
export function overlay(notes: CachedNote[], queued: QueuedOp[], failed: QueuedOp[]): Note[] {
  const byId = new Map<string, Note>(notes.map((n) => [n.id, { ...n, state: "synced" }]));
  const apply = ({ ms, op }: QueuedOp, state: NoteState) => {
    const base = byId.get(op.note_id);
    if (op.op === "delete") {
      // A failed delete leaves the note in Keep, so keep showing it.
      if (state === "failed" && base) byId.set(op.note_id, { ...base, state });
      else byId.delete(op.note_id);
      return;
    }
    byId.set(op.note_id, {
      ...(base ?? newNote(op.note_id)),
      title: op.title,
      text: op.text,
      updated: new Date(ms).toISOString(),
      state,
    });
  };
  failed.forEach((q) => apply(q, "failed"));
  queued.forEach((q) => apply(q, "pending"));
  return [...byId.values()];
}

function newNote(id: string): Note {
  return {
    id,
    kind: "note",
    title: "",
    text: "",
    items: null,
    pinned: false,
    archived: false,
    color: "DEFAULT",
    labels: [],
    updated: "",
    url: noteUrl(id),
    state: "pending",
  };
}

/** Active before archived, pinned first, then newest first. */
export function sortNotes(notes: Note[]): Note[] {
  return [...notes].sort(
    (a, b) =>
      Number(a.archived) - Number(b.archived) ||
      Number(b.pinned) - Number(a.pinned) ||
      b.updated.localeCompare(a.updated),
  );
}

export function loadNotes(appDir = APP_DIR): { notes: Note[]; status: SyncStatus | null } {
  let cache: Cache | null = null;
  try {
    cache = JSON.parse(readFileSync(join(appDir, "cache.json"), "utf8")) as Cache;
  } catch {
    // No cache yet: the service has not synced. Queued ops still show.
  }
  const notes = overlay(cache?.notes ?? [], readOps(queueDir(appDir)), readOps(failedDir(appDir)));
  return { notes: sortNotes(notes), status: cache };
}

const STALE_MS = 10 * 60 * 1000;

/** A warning for the list, or null when sync is healthy. */
export function syncWarning(status: SyncStatus | null, now = Date.now()): string | null {
  if (status === null) return "No sync yet. Is the keep-sync service installed?";
  if (status.error?.kind === "auth") return "Keep sync failing (auth). Run `keep-sync setup`.";
  if (status.error) return `Keep sync failing (${status.error.kind}): ${status.error.message}`;
  if (status.synced_at === null) return "No sync yet.";
  const age = now - Date.parse(status.synced_at);
  if (age > STALE_MS) return `Last sync ${Math.round(age / 60_000)} min ago.`;
  return null;
}
