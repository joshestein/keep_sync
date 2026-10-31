import { popToRoot, showHUD } from "@raycast/api";

import { mintNoteId, writeOp } from "./lib/store";
import { NoteForm } from "./note-form";

export default function Command() {
  return (
    <NoteForm
      submitTitle="Save Note"
      enableDrafts
      onSubmit={async ({ title, text }) => {
        // Only a local file write: the service syncs it in the background.
        writeOp({ op: "create", note_id: mintNoteId(), title, text });
        await showHUD("Note saved", { clearRootSearch: true });
        await popToRoot();
      }}
    />
  );
}
