import { mkdirSync, mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

import { CachedNote, loadNotes, mintNoteId, overlay, readOps, syncWarning, writeOp } from "../src/lib/store";

const cached = (id: string, fields: Partial<CachedNote> = {}): CachedNote => ({
  id,
  kind: "note",
  title: "",
  text: "",
  items: null,
  pinned: false,
  archived: false,
  color: "DEFAULT",
  labels: [],
  updated: "2026-10-01T00:00:00.000Z",
  url: `https://keep.google.com/u/0/#NOTE/${id}`,
  ...fields,
});

describe("mintNoteId", () => {
  it("matches gkeepapi's format and the service's create check", () => {
    expect(mintNoteId(0x18f2a9c3b10)).toMatch(/^18f2a9c3b10\.[0-9a-f]{16}$/);
    expect(mintNoteId()).not.toBe(mintNoteId());
  });
});

describe("writeOp and readOps", () => {
  let appDir: string;
  beforeEach(() => {
    appDir = mkdtempSync(join(tmpdir(), "keep-sync-"));
  });

  it("writes a file the service picks up, with no temp file left", () => {
    writeOp({ op: "create", note_id: "a", title: "", text: "x" }, appDir);
    const names = readdirSync(join(appDir, "queue"));
    expect(names).toHaveLength(1);
    expect(names[0]).toMatch(/^\d+-[0-9a-f]{8}\.json$/);
    expect(readOps(join(appDir, "queue"))).toEqual([{ op: "create", note_id: "a", title: "", text: "x" }]);
  });

  it("skips temp files, folders, and unreadable files", () => {
    const dir = join(appDir, "queue");
    mkdirSync(join(dir, "failed"), { recursive: true });
    writeFileSync(join(dir, ".1-abcd.json.tmp"), "{}");
    writeFileSync(join(dir, "2-abcd.json"), "{");
    writeFileSync(join(dir, "3-abcd.json"), JSON.stringify({ op: "delete", note_id: "a" }));
    expect(readOps(dir)).toEqual([{ op: "delete", note_id: "a" }]);
  });

  it("returns no ops when the queue does not exist", () => {
    expect(readOps(join(appDir, "nope"))).toEqual([]);
  });

  it("loads with no cache: queued captures still show", () => {
    writeOp({ op: "create", note_id: "a", title: "T", text: "x" }, appDir);
    const { notes, status } = loadNotes(appDir);
    expect(status).toBeNull();
    expect(notes.map((n) => [n.id, n.state])).toEqual([["a", "pending"]]);
  });

  it("sorts active before archived, pinned first, then newest", () => {
    writeFileSync(
      join(appDir, "cache.json"),
      JSON.stringify({
        synced_at: null,
        last_attempt_at: null,
        error: null,
        notes: [
          cached("archived", { archived: true, pinned: true, updated: "2026-10-03T00:00:00.000Z" }),
          cached("old", { updated: "2026-10-01T00:00:00.000Z" }),
          cached("new", { updated: "2026-10-02T00:00:00.000Z" }),
          cached("pinned", { pinned: true }),
        ],
      }),
    );
    expect(loadNotes(appDir).notes.map((n) => n.id)).toEqual(["pinned", "new", "old", "archived"]);
  });
});

describe("overlay", () => {
  const now = new Date("2026-10-31T12:00:00.000Z");

  it("shows a capture as pending, dated now", () => {
    const [note] = overlay([], [{ op: "create", note_id: "a", title: "T", text: "x" }], [], now);
    expect(note).toMatchObject({ id: "a", title: "T", text: "x", state: "pending", updated: now.toISOString() });
  });

  it("applies an edit to a cached note and keeps its other fields", () => {
    const [note] = overlay(
      [cached("a", { pinned: true, labels: ["home"] })],
      [{ op: "update", note_id: "a", title: "T", text: "new" }],
      [],
    );
    expect(note).toMatchObject({ text: "new", pinned: true, labels: ["home"], state: "pending" });
  });

  it("applies ops in order: capture, edit, delete", () => {
    const ops = [
      { op: "create", note_id: "a", title: "", text: "x" },
      { op: "update", note_id: "a", title: "", text: "y" },
    ] as const;
    expect(overlay([], [...ops], [])[0].text).toBe("y");
    expect(overlay([], [...ops, { op: "delete", note_id: "a" }], [])).toEqual([]);
  });

  it("hides a pending delete", () => {
    expect(overlay([cached("a")], [{ op: "delete", note_id: "a" }], [])).toEqual([]);
  });

  it("marks failed ops", () => {
    const [note] = overlay([cached("a")], [], [{ op: "update", note_id: "a", title: "", text: "lost?" }]);
    expect([note.state, note.text]).toEqual(["failed", "lost?"]);
  });
});

describe("syncWarning", () => {
  const now = Date.parse("2026-10-31T12:00:00.000Z");
  const ok = { synced_at: "2026-10-31T11:59:00.000Z", last_attempt_at: "2026-10-31T11:59:00.000Z", error: null };

  it("is silent when sync is healthy", () => {
    expect(syncWarning(ok, now)).toBeNull();
  });

  it("warns on errors, staleness, and no service", () => {
    expect(syncWarning({ ...ok, error: { kind: "auth", message: "x" } }, now)).toContain("keep-sync setup");
    expect(syncWarning({ ...ok, error: { kind: "network", message: "offline" } }, now)).toContain("offline");
    expect(syncWarning({ ...ok, synced_at: "2026-10-31T11:00:00.000Z" }, now)).toBe("Last sync 60 min ago.");
    expect(syncWarning(null, now)).toContain("service");
  });
});
