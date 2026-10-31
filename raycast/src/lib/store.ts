/**
 * Local files shared with the keep-sync service. This module never touches the network.
 * The extension writes only op files. The service writes everything else.
 */
import { randomBytes } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
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

/** A Keep note id in gkeepapi's client-side format: "{ms:x}.{random64:016x}" (ADR 0001). */
export function mintNoteId(now = Date.now()): string {
  return `${now.toString(16)}.${randomBytes(8).toString("hex")}`;
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
export function readOps(dir: string): Op[] {
  let names: string[];
  try {
    names = readdirSync(dir).sort();
  } catch {
    return [];
  }
  return names.flatMap((name) => {
    if (!/^\d+-[0-9a-f]+\.json$/.test(name)) return [];
    try {
      return [JSON.parse(readFileSync(join(dir, name), "utf8")) as Op];
    } catch {
      return [];
    }
  });
}

/** The cache with failed, then queued, ops applied on top, so captures and edits show at once. */
export function overlay(notes: CachedNote[], queued: Op[], failed: Op[], now = new Date()): Note[] {
  const byId = new Map<string, Note>(notes.map((n) => [n.id, { ...n, state: "synced" }]));
  const apply = (op: Op, state: Note["state"]) => {
    if (op.op === "delete") {
      byId.delete(op.note_id);
      return;
    }
    const base = byId.get(op.note_id) ?? {
      id: op.note_id,
      kind: "note",
      items: null,
      pinned: false,
      archived: false,
      color: "DEFAULT",
      labels: [],
      url: `https://keep.google.com/u/0/#NOTE/${op.note_id}`,
    };
    // `updated` is now, so a capture or edit sorts to the top.
    byId.set(op.note_id, { ...base, title: op.title, text: op.text, updated: now.toISOString(), state });
  };
  failed.forEach((op) => apply(op, "failed"));
  queued.forEach((op) => apply(op, "pending"));
  return [...byId.values()];
}

/** Notes sorted active first, then pinned first, then newest first. */
export function loadNotes(appDir = APP_DIR): { notes: Note[]; status: SyncStatus | null } {
  let cache: Cache | null = null;
  try {
    cache = JSON.parse(readFileSync(join(appDir, "cache.json"), "utf8")) as Cache;
  } catch {
    // No cache yet: the service has not synced. Queued ops still show.
  }
  const queue = join(appDir, "queue");
  const notes = overlay(cache?.notes ?? [], readOps(queue), readOps(join(queue, "failed"))).sort(
    (a, b) =>
      Number(a.archived) - Number(b.archived) ||
      Number(b.pinned) - Number(a.pinned) ||
      b.updated.localeCompare(a.updated),
  );
  return { notes, status: cache };
}

const STALE_MS = 10 * 60 * 1000;

/** A warning for the list, or null when sync is healthy. */
export function syncWarning(status: SyncStatus | null, now = Date.now()): string | null {
  if (status?.error?.kind === "auth") return "Keep sync failing (auth). Run `keep-sync setup`.";
  if (status?.error) return `Keep sync failing (${status.error.kind}): ${status.error.message}`;
  if (!status?.synced_at) return "No sync yet. Is the keep-sync service running?";
  const age = now - Date.parse(status.synced_at);
  return age > STALE_MS ? `Last sync ${Math.round(age / 60_000)} min ago.` : null;
}
