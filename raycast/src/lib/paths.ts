import { homedir } from "node:os";
import { join } from "node:path";

export const APP_DIR = join(homedir(), "Library", "Application Support", "keep-sync");
