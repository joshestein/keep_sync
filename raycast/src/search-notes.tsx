import {
  Action,
  ActionPanel,
  Alert,
  Color,
  confirmAlert,
  Icon,
  Image,
  Keyboard,
  List,
  showToast,
  Toast,
  useNavigation,
} from "@raycast/api";
import { useMemo, useState } from "react";

import { mintNoteId } from "./lib/id";
import { escapeMarkdown, renderNote } from "./lib/markdown";
import { displayTitle, filterNotes } from "./lib/search";
import { loadNotes, Note, SyncStatus, syncWarning, writeOp } from "./lib/store";
import { NoteForm } from "./note-form";

export default function Command() {
  const [{ notes, status }, setData] = useState(() => loadNotes());
  const [query, setQuery] = useState("");
  const reload = () => setData(loadNotes());
  const shown = useMemo(() => filterNotes(notes, query), [notes, query]);
  const warning = syncWarning(status);

  return (
    <List isShowingDetail filtering={false} onSearchTextChange={setQuery} searchBarPlaceholder="Search Keep notes">
      {warning && (
        <List.Section title="Sync">
          <List.Item
            icon={{ source: Icon.Warning, tintColor: Color.Orange }}
            title={warning}
            detail={<List.Item.Detail markdown={statusMarkdown(warning, status)} />}
            actions={
              <ActionPanel>
                <ReloadAction reload={reload} />
              </ActionPanel>
            }
          />
        </List.Section>
      )}
      <List.Section title="Notes" subtitle={String(shown.length)}>
        {shown.map((note) => (
          <NoteItem key={note.id} note={note} reload={reload} />
        ))}
      </List.Section>
    </List>
  );
}

function NoteItem({ note, reload }: { note: Note; reload: () => void }) {
  async function trash() {
    const confirmed = await confirmAlert({
      title: "Move note to trash?",
      message: "You can restore it in Keep for 7 days.",
      primaryAction: { title: "Move to Trash", style: Alert.ActionStyle.Destructive },
    });
    if (!confirmed) return;
    writeOp({ op: "delete", note_id: note.id });
    reload();
  }

  return (
    <List.Item
      title={displayTitle(note)}
      icon={rowIcon(note)}
      detail={<List.Item.Detail markdown={renderNote(note)} metadata={<NoteMetadata note={note} />} />}
      actions={
        <ActionPanel>
          {/* The first action runs on Return, the second on Cmd+Return. Lists cannot be edited, so Copy comes first. */}
          {note.kind === "note" && (
            <Action.Push
              title="Edit Note"
              icon={Icon.Pencil}
              shortcut={Keyboard.Shortcut.Common.Edit}
              target={<EditNote note={note} onSaved={reload} />}
            />
          )}
          <Action.CopyToClipboard title="Copy Text" content={note.text} />
          {note.title && (
            <Action.CopyToClipboard title="Copy Title" content={note.title} shortcut={Keyboard.Shortcut.Common.Copy} />
          )}
          <Action.OpenInBrowser title="Open in Keep" url={note.url} shortcut={Keyboard.Shortcut.Common.Open} />
          <Action.Push
            title="New Note"
            icon={Icon.Plus}
            shortcut={Keyboard.Shortcut.Common.New}
            target={<CreateNote onSaved={reload} />}
          />
          <Action
            title="Move to Trash"
            icon={Icon.Trash}
            style={Action.Style.Destructive}
            shortcut={Keyboard.Shortcut.Common.Remove}
            onAction={trash}
          />
          <ReloadAction reload={reload} />
        </ActionPanel>
      }
    />
  );
}

function ReloadAction({ reload }: { reload: () => void }) {
  return (
    <Action title="Reload" icon={Icon.ArrowClockwise} shortcut={Keyboard.Shortcut.Common.Refresh} onAction={reload} />
  );
}

function EditNote({ note, onSaved }: { note: Note; onSaved: () => void }) {
  const { pop } = useNavigation();
  return (
    <NoteForm
      submitTitle="Save Changes"
      initial={{ title: note.title, text: note.text }}
      onSubmit={async ({ title, text }) => {
        if (title !== note.title || text !== note.text) {
          writeOp({ op: "update", note_id: note.id, title, text });
          onSaved();
        }
        pop();
        await showToast({ style: Toast.Style.Success, title: "Saved", message: "Syncs in the background" });
      }}
    />
  );
}

function CreateNote({ onSaved }: { onSaved: () => void }) {
  const { pop } = useNavigation();
  return (
    <NoteForm
      submitTitle="Save Note"
      onSubmit={async ({ title, text }) => {
        writeOp({ op: "create", note_id: mintNoteId(), title, text });
        onSaved();
        pop();
        await showToast({ style: Toast.Style.Success, title: "Saved", message: "Syncs in the background" });
      }}
    />
  );
}

function NoteMetadata({ note }: { note: Note }) {
  const { Metadata } = List.Item.Detail;
  return (
    <Metadata>
      <Metadata.Label title="Status" text={STATE_LABEL[note.state]} />
      {note.labels.length > 0 && (
        <Metadata.TagList title="Labels">
          {note.labels.map((label) => (
            <Metadata.TagList.Item key={label} text={label} />
          ))}
        </Metadata.TagList>
      )}
      {note.updated && <Metadata.Label title="Updated" text={new Date(note.updated).toLocaleString()} />}
      {note.pinned && <Metadata.Label title="Pinned" icon={Icon.Pin} />}
      {note.archived && <Metadata.Label title="Archived" icon={Icon.Box} />}
      {note.color !== "DEFAULT" && <Metadata.Label title="Color" text={note.color.toLowerCase()} />}
    </Metadata>
  );
}

const STATE_LABEL: Record<Note["state"], string> = {
  synced: "Synced",
  pending: "Pending sync",
  failed: "Failed: see ~/Library/Logs/keep-sync.log",
};

function rowIcon(note: Note): Image.ImageLike {
  if (note.state === "failed") return { source: Icon.ExclamationMark, tintColor: Color.Red };
  if (note.state === "pending") return { source: Icon.Clock, tintColor: Color.SecondaryText };
  if (note.archived) return { source: Icon.Box, tintColor: Color.SecondaryText };
  if (note.pinned) return Icon.Pin;
  return note.kind === "list" ? Icon.BulletPoints : Icon.Document;
}

function statusMarkdown(warning: string, status: SyncStatus | null): string {
  const lines = [`## ${escapeMarkdown(warning)}`];
  if (status) {
    lines.push(`Last sync: ${status.synced_at ? new Date(status.synced_at).toLocaleString() : "never"}`);
    lines.push(`Last attempt: ${status.last_attempt_at ? new Date(status.last_attempt_at).toLocaleString() : "never"}`);
  }
  lines.push("Check `keep-sync status` and `~/Library/Logs/keep-sync.log`.");
  return lines.join("\n\n");
}
