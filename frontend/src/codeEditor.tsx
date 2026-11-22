import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { LanguageDescription, syntaxHighlighting } from '@codemirror/language';
import { languages } from '@codemirror/language-data';
import { highlightSelectionMatches, search, searchKeymap } from '@codemirror/search';
import { Compartment, EditorState, type Text } from '@codemirror/state';
import {
  drawSelection,
  EditorView,
  highlightSpecialChars,
  keymap,
  lineNumbers,
} from '@codemirror/view';
import { useMutation } from '@tanstack/react-query';
import { RotateCcw, Save } from 'lucide-react';
import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { ApiError } from './api';
import { useI18n } from './i18n';
import { button, primaryButton } from './styles';
import { look, PHRASES, style } from './TextView';
import { errorMessage } from './tree';

export interface Opened {
  path: string;
  size: number;
  modified: string;
  kind: 'text' | 'binary' | 'large';
  text: string | null;
  hash: string | null;
}

export interface Written {
  path: string;
  size: number;
  modified: string;
  hash: string;
}

/** A text file in CodeMirror as Ponistra shows code, written back with Ctrl+S or Save while the
 * disk still holds what was read. */
export function CodeEditor({
  source,
  path,
  opened,
  read,
  write,
  onWritten,
  onRead,
  onDirty,
  readOnly = false,
}: {
  /** Where the file lives; with the path, what tells one file from another. */
  source: string;
  path: string;
  opened: Opened;
  read: () => Promise<Opened>;
  write: (text: string, hash: string) => Promise<Written>;
  onWritten: (written: Written, text: string) => void;
  onRead: (now: Opened) => void;
  onDirty: (dirty: boolean) => void;
  readOnly?: boolean;
}) {
  const { t } = useI18n();
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const saved = useRef<{ doc: Text | null; hash: string }>({ doc: null, hash: opened.hash! });
  const [dirty, setDirty] = useState(false);
  const [changed, setChanged] = useState(false);
  const marked = useEffectEvent((now: boolean) => {
    setDirty(now);
    onDirty(now);
  });
  const settled = (written: Written, doc: Text) => {
    saved.current = { doc, hash: written.hash };
    setChanged(false);
    marked(false);
    onWritten(written, doc.toString());
  };
  const writing = useMutation({
    mutationFn: ({ doc, hash }: { doc: Text; hash: string }) => write(doc.toString(), hash),
    onSuccess: (written, { doc }) => settled(written, doc),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409 && error.code === 'changed')
        setChanged(true);
    },
  });
  const save = useEffectEvent((hash?: string) => {
    const now = view.current?.state.doc;
    if (now && !writing.isPending) writing.mutate({ doc: now, hash: hash ?? saved.current.hash });
  });
  const overwrite = useMutation({
    mutationFn: read,
    onSuccess: (now) => {
      if (now.hash) save(now.hash);
    },
  });
  const replaced = useEffectEvent((now: Opened, force = false) => {
    const editor = view.current;
    if (!editor || now.text === null || (!force && now.hash === saved.current.hash)) return;
    editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: now.text } });
    saved.current = { doc: editor.state.doc, hash: now.hash! };
    setChanged(false);
    marked(false);
  });
  const reload = useMutation({
    mutationFn: read,
    onSuccess: (now) => {
      writing.reset();
      replaced(now, true);
      onRead(now);
    },
  });

  useEffect(() => {
    const language = new Compartment();
    const editor = new EditorView({
      parent: host.current!,
      state: EditorState.create({
        doc: opened.text ?? '',
        extensions: [
          lineNumbers(),
          highlightSpecialChars(),
          history(),
          drawSelection(),
          highlightSelectionMatches(),
          search({ top: true }),
          keymap.of([
            {
              key: 'Mod-s',
              preventDefault: true,
              run: () => {
                save();
                return true;
              },
            },
            ...searchKeymap,
            ...historyKeymap,
            ...defaultKeymap,
          ]),
          EditorState.phrases.of(
            Object.fromEntries(Object.entries(PHRASES).map(([phrase, key]) => [phrase, t(key)])),
          ),
          syntaxHighlighting(style),
          look,
          language.of([]),
          EditorState.readOnly.of(readOnly),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) marked(!update.state.doc.eq(saved.current.doc!));
          }),
        ],
      }),
    });
    saved.current = { doc: editor.state.doc, hash: opened.hash! };
    view.current = editor;
    let gone = false;
    void LanguageDescription.matchFilename(languages, path.split('/').pop() ?? path)
      ?.load()
      .then((support) => {
        if (!gone) editor.dispatch({ effects: language.reconfigure(support) });
      });
    return () => {
      gone = true;
      view.current = null;
      editor.destroy();
      marked(false);
    };
  }, [source, path, t, readOnly]);

  useEffect(() => {
    if (!dirty) replaced(opened);
  }, [opened, dirty]);

  const failure = writing.error ?? overwrite.error ?? reload.error;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-2 py-1">
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted">{path}</span>
        <span className="text-xs text-muted">
          {dirty
            ? t('workspace.files.unsaved')
            : writing.isSuccess
              ? t('workspace.files.saved')
              : ''}
        </span>
        <button
          type="button"
          disabled={!dirty || writing.isPending}
          onClick={() => save()}
          className={primaryButton}
        >
          <Save size={14} aria-hidden />
          {t('workspace.files.save')}
        </button>
      </div>
      {changed ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 bg-panel px-2 py-1 text-sm">
          <span className="text-danger">{t('workspace.files.changed')}</span>
          <button type="button" onClick={() => reload.mutate()} className={button}>
            <RotateCcw size={14} aria-hidden />
            {t('workspace.files.reload')}
          </button>
          <button type="button" onClick={() => overwrite.mutate()} className={button}>
            <Save size={14} aria-hidden />
            {t('workspace.files.overwrite')}
          </button>
        </div>
      ) : (
        failure && (
          <p role="alert" className="bg-panel px-2 py-1 text-sm text-danger">
            {errorMessage(failure, t)}
          </p>
        )
      )}
      <div ref={host} className="min-h-[50dvh] flex-1 overflow-hidden" />
    </div>
  );
}
