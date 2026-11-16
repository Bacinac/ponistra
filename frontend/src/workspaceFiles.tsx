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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Download,
  File,
  Folder,
  Link2Off,
  RotateCcw,
  Save,
  X,
} from 'lucide-react';
import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { ApiError, getJson, postJson } from './api';
import { ConfirmDialog } from './dialogs';
import { formatSize } from './explorer';
import { Loading, useWide } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { useHeldRelease } from './release';
import { button, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';
import { look, PHRASES, style } from './TextView';

type Kind = 'folder' | 'file' | 'outside' | 'broken' | 'other';

interface Entry {
  name: string;
  kind: Kind;
  size: number | null;
  modified: string | null;
}

interface Listed {
  path: string;
  entries: Entry[];
}

interface Opened {
  path: string;
  size: number;
  modified: string;
  kind: 'text' | 'binary' | 'large';
  text: string | null;
  hash: string | null;
}

interface Written {
  path: string;
  size: number;
  modified: string;
  hash: string;
}

const UNOPENED: Partial<Record<Kind, MessageKey>> = {
  outside: 'workspace.files.outside',
  broken: 'workspace.files.broken',
  other: 'workspace.files.other',
};

const placeOf = (folder: string, path: string) => new URLSearchParams({ folder, path }).toString();

const listKey = (folder: string, path: string) => ['workspace', 'files', folder, path];
const fileKey = (folder: string, path: string) => ['workspace', 'file', folder, path];

const within = (parent: string, name: string) => (parent ? `${parent}/${name}` : name);

/** One folder's entries, each folder opening its own below it. */
function Entries({
  folder,
  path,
  depth,
  open,
  chosen,
  onToggle,
  onChoose,
}: {
  folder: string;
  path: string;
  depth: number;
  open: Set<string>;
  chosen: string | null;
  onToggle: (path: string) => void;
  onChoose: (path: string) => void;
}) {
  const { t } = useI18n();
  const listed = useQuery({
    queryKey: listKey(folder, path),
    queryFn: () => getJson<Listed>(`/api/workspace/files?${placeOf(folder, path)}`),
  });
  const indent = { paddingLeft: `${depth * 0.75 + 0.25}rem` };
  if (listed.isPending)
    return (
      <p style={indent} className="py-1 text-sm text-muted">
        {t('tree.loading')}
      </p>
    );
  if (listed.isError)
    return (
      <p style={indent} className="py-1 text-sm text-danger">
        {errorMessage(listed.error, t)}
      </p>
    );
  if (!listed.data.entries.length)
    return (
      <p style={indent} className="py-1 text-sm text-muted">
        {t('workspace.files.empty')}
      </p>
    );
  return (
    <ul role={depth ? 'group' : 'tree'} aria-label={depth ? undefined : t('workspace.view.files')}>
      {listed.data.entries.map((entry) => {
        const at = within(path, entry.name);
        const unopened = UNOPENED[entry.kind];
        const expanded = entry.kind === 'folder' && open.has(at);
        const Icon =
          entry.kind === 'folder'
            ? expanded
              ? ChevronDown
              : ChevronRight
            : unopened
              ? Link2Off
              : File;
        return (
          <li
            key={entry.name}
            role="treeitem"
            aria-expanded={entry.kind === 'folder' ? expanded : undefined}
            aria-selected={chosen === at}
          >
            <button
              type="button"
              disabled={Boolean(unopened)}
              title={unopened ? t(unopened) : entry.name}
              onClick={() => (entry.kind === 'folder' ? onToggle(at) : onChoose(at))}
              style={indent}
              className={`flex w-full min-w-0 items-center gap-1.5 rounded py-1 pr-2 text-left text-sm hover:bg-hover disabled:text-muted disabled:hover:bg-transparent ${chosen === at ? 'bg-selected' : ''}`}
            >
              <Icon size={14} aria-hidden className="shrink-0 text-muted" />
              {entry.kind === 'folder' && (
                <Folder size={14} aria-hidden className="shrink-0 text-muted" />
              )}
              <span className="truncate">{entry.name}</span>
            </button>
            {expanded && (
              <Entries
                folder={folder}
                path={at}
                depth={depth + 1}
                open={open}
                chosen={chosen}
                onToggle={onToggle}
                onChoose={onChoose}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** A text file in CodeMirror as Ponistra shows code, written back with Ctrl+S or Save while the
 * disk still holds what was read. */
function Editor({
  folder,
  path,
  opened,
  onDirty,
}: {
  folder: string;
  path: string;
  opened: Opened;
  onDirty: (dirty: boolean) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
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
    queryClient.setQueryData<Opened>(fileKey(folder, path), (before) =>
      before ? { ...before, ...written, text: doc.toString() } : before,
    );
    void queryClient.invalidateQueries({
      queryKey: listKey(folder, path.replace(/\/?[^/]*$/, '')),
    });
  };
  const writing = useMutation({
    mutationFn: ({ doc, hash }: { doc: Text; hash: string }) =>
      postJson<Written>('/api/workspace/file', { folder, path, text: doc.toString(), hash }),
    onSuccess: (written, { doc }) => settled(written, doc),
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) setChanged(true);
    },
  });
  const save = useEffectEvent((hash?: string) => {
    const now = view.current?.state.doc;
    if (now && !writing.isPending) writing.mutate({ doc: now, hash: hash ?? saved.current.hash });
  });
  const overwrite = useMutation({
    mutationFn: () => getJson<Opened>(`/api/workspace/file?${placeOf(folder, path)}`),
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
    mutationFn: () => getJson<Opened>(`/api/workspace/file?${placeOf(folder, path)}`),
    onSuccess: (now) => {
      writing.reset();
      replaced(now, true);
      queryClient.setQueryData(fileKey(folder, path), now);
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
  }, [folder, path, t]);

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

/** A file chosen in the tree: its text to edit, or what it is and a download. */
function FileView({
  folder,
  path,
  onDirty,
}: {
  folder: string;
  path: string;
  onDirty: (dirty: boolean) => void;
}) {
  const { t, formatNumber } = useI18n();
  const opened = useQuery({
    queryKey: fileKey(folder, path),
    queryFn: () => getJson<Opened>(`/api/workspace/file?${placeOf(folder, path)}`),
  });
  if (opened.isPending) return <Loading />;
  if (opened.isError)
    return <p className="p-2 text-sm text-danger">{errorMessage(opened.error, t)}</p>;
  if (opened.data.kind === 'text')
    return <Editor folder={folder} path={path} opened={opened.data} onDirty={onDirty} />;
  return (
    <div className="flex flex-col items-start gap-3 p-4 text-sm">
      <p className="font-mono text-xs text-muted">{path}</p>
      <p>
        {t(opened.data.kind === 'large' ? 'workspace.files.large' : 'workspace.files.binary')}{' '}
        <span className="text-muted">{formatSize(opened.data.size, formatNumber)}</span>
      </p>
      <a
        href={`/api/workspace/file/raw?${placeOf(folder, path)}`}
        download={path.split('/').pop()}
        className={button}
      >
        <Download size={14} aria-hidden />
        {t('workspace.files.download')}
      </a>
    </div>
  );
}

/** The files of a project of the workspace (PJ6): its tree beside the file chosen in it, or one
 * after the other on a narrow screen. */
export function FilesPanel({
  folder,
  name,
  onDirty,
  onClose,
}: {
  folder: string;
  name: string;
  onDirty: (dirty: boolean) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const wide = useWide();
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [chosen, setChosen] = useState<string | null>(null);
  const [dirty, setDirtyHere] = useState(false);
  const setDirty = (now: boolean) => {
    setDirtyHere(now);
    onDirty(now);
  };
  const [leaving, setLeaving] = useState<(() => void) | null>(null);
  useHeldRelease(dirty);
  const unsaved = (then: () => void) => (dirty ? setLeaving(() => then) : then());
  const toggle = (path: string) =>
    setOpen((now) => {
      const next = new Set(now);
      if (!next.delete(path)) next.add(path);
      return next;
    });
  const choose = (path: string) => {
    if (path !== chosen) unsaved(() => setChosen(path));
  };
  const tree = (
    <div className="min-h-0 overflow-y-auto">
      <Entries
        folder={folder}
        path=""
        depth={0}
        open={open}
        chosen={chosen}
        onToggle={toggle}
        onChoose={choose}
      />
    </div>
  );
  const file = chosen ? (
    <FileView key={chosen} folder={folder} path={chosen} onDirty={setDirty} />
  ) : (
    <p className="p-4 text-sm text-muted">{t('workspace.files.none')}</p>
  );
  return (
    <section
      aria-label={t('workspace.view.files')}
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <div className="mb-2 flex items-center gap-2">
        {!wide && chosen && (
          <button
            type="button"
            aria-label={t('workspace.files.back')}
            title={t('workspace.files.back')}
            onClick={() => unsaved(() => setChosen(null))}
            className={iconButton}
          >
            <ArrowLeft size={16} aria-hidden />
          </button>
        )}
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">{name}</h2>
        <button
          type="button"
          aria-label={t('workspace.files.close')}
          title={t('workspace.files.close')}
          onClick={() => unsaved(onClose)}
          className={iconButton}
        >
          <X size={16} aria-hidden />
        </button>
      </div>
      {wide ? (
        <div className="grid min-h-[60dvh] flex-1 grid-cols-[minmax(12rem,18rem)_1fr] overflow-hidden rounded border border-line">
          <div className="flex min-h-0 flex-col border-r border-line p-1">{tree}</div>
          <div className="flex min-h-0 min-w-0 flex-col">{file}</div>
        </div>
      ) : (
        <div className="flex min-h-[60dvh] flex-1 flex-col overflow-hidden rounded border border-line">
          {chosen ? file : <div className="p-1">{tree}</div>}
        </div>
      )}
      {leaving && (
        <ConfirmDialog
          heading={t('workspace.files.discard')}
          confirmLabel={t('workspace.files.discardConfirm')}
          onConfirm={() => {
            setDirty(false);
            leaving();
            setLeaving(null);
          }}
          onClose={() => setLeaving(null)}
        >
          {t('workspace.files.discardBody')}
        </ConfirmDialog>
      )}
    </section>
  );
}
