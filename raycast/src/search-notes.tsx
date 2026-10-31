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
import { useEffect, useMemo, useState } from "react";

import { escapeMarkdown, renderNote } from "./lib/markdown";
import { displayTitle, filterNotes } from "./lib/search";
import { createNote, loadNotes, Note, syncWarning, writeOp } from "./lib/store";
import { NoteForm } from "./note-form";

const RELOAD_MS = 3000;

export default function Command() {
  const [{ notes, status }, setData] = useState(() => loadNotes());
  const [query, setQuery] = useState("");
  const reload = () => setData(loadNotes());
  // The service changes the files in the background: poll so pending states and the sync warning stay current.
  useEffect(() => {
    const timer = setInterval(() => setData(loadNotes()), RELOAD_MS);
    return () => clearInterval(timer);
  }, []);
  const shown = useMemo(() => filterNotes(notes, query), [notes, query]);
  const warning = syncWarning(status);

  return (
    <List isShowingDetail filtering={false} onSearchTextChange={setQuery} searchBarPlaceholder="Search Keep notes">
      {warning && (
        <List.Section title="Sync">
          <List.Item
            icon={{ source: Icon.Warning, tintColor: Color.Orange }}
            title={warning}
            detail={
              <List.Item.Detail
                markdown={`${escapeMarkdown(warning)}\n\nRun \`keep-sync status\` or check \`~/Library/Logs/keep-sync.log\`.`}
              />
            }
            actions={
              <ActionPanel>
                <ReloadAction reload={reload} />
                <NewNoteAction query={query} reload={reload} />
              </ActionPanel>
            }
          />
        </List.Section>
      )}
      <List.EmptyView
        title="No notes"
        description={query ? "Press Return to make a note from your search." : undefined}
        actions={
          <ActionPanel>
            <NewNoteAction query={query} reload={reload} />
          </ActionPanel>
        }
      />
      <List.Section title="Notes" subtitle={String(shown.length)}>
        {shown.map((note) => (
          <NoteItem key={note.id} note={note} query={query} reload={reload} />
        ))}
      </List.Section>
    </List>
  );
}

function NoteItem({ note, query, reload }: { note: Note; query: string; reload: () => void }) {
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
              target={<NoteEditor note={note} onSaved={reload} />}
            />
          )}
          <Action.CopyToClipboard title="Copy Text" content={note.text} />
          {note.title && (
            <Action.CopyToClipboard title="Copy Title" content={note.title} shortcut={Keyboard.Shortcut.Common.Copy} />
          )}
          <Action.OpenInBrowser title="Open in Keep" url={note.url} shortcut={Keyboard.Shortcut.Common.Open} />
          <NewNoteAction query={query} reload={reload} />
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

/** The search text becomes the body of the new note. */
function NewNoteAction({ query, reload }: { query: string; reload: () => void }) {
  return (
    <Action.Push
      title="New Note"
      icon={Icon.Plus}
      shortcut={Keyboard.Shortcut.Common.New}
      target={<NoteEditor initialText={query} onSaved={reload} />}
    />
  );
}

/** Edits `note`, or makes a new note when there is none. */
function NoteEditor({ note, initialText = "", onSaved }: { note?: Note; initialText?: string; onSaved: () => void }) {
  const { pop } = useNavigation();
  return (
    <NoteForm
      submitTitle={note ? "Save Changes" : "Save Note"}
      initial={{ title: note?.title ?? "", text: note?.text ?? initialText }}
      onSubmit={async ({ title, text }) => {
        if (!note) {
          createNote(title, text);
          // NoteForm trims the title, so compare with the trimmed title or every save writes an op.
        } else if (title !== note.title.trim() || text !== note.text) {
          writeOp({ op: "update", note_id: note.id, title, text });
        }
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
