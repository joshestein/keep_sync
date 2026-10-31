import { randomBytes } from "node:crypto";

/** A Keep note id in gkeepapi's client-side format: "{ms:x}.{random64:016x}" (ADR 0001). */
export function mintNoteId(now = Date.now()): string {
  return `${now.toString(16)}.${randomBytes(8).toString("hex")}`;
}
