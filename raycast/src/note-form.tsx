import { Action, ActionPanel, Form } from "@raycast/api";
import { useState } from "react";

export interface NoteFormValues {
  title: string;
  text: string;
}

interface Props {
  submitTitle: string;
  initial?: NoteFormValues;
  enableDrafts?: boolean;
  onSubmit: (values: NoteFormValues) => Promise<void> | void;
}

export function NoteForm({ submitTitle, initial, enableDrafts, onSubmit }: Props) {
  const [textError, setTextError] = useState<string>();

  async function submit({ title, text }: NoteFormValues) {
    if (!title.trim() && !text.trim()) {
      setTextError("Write a title or a note");
      return;
    }
    await onSubmit({ title: title.trim(), text });
  }

  return (
    <Form
      enableDrafts={enableDrafts}
      actions={
        <ActionPanel>
          <Action.SubmitForm title={submitTitle} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.TextField id="title" title="Title" placeholder="Optional" defaultValue={initial?.title} />
      <Form.TextArea
        id="text"
        title="Note"
        autoFocus
        defaultValue={initial?.text}
        error={textError}
        onChange={() => setTextError(undefined)}
      />
    </Form>
  );
}
