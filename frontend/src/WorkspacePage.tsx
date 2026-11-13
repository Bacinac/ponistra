import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Archive,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  ArrowDownToLine,
  ArrowUpToLine,
  ClipboardList,
  ExternalLink,
  ImagePlus,
  Pencil,
  FileDiff,
  FolderInput,
  GitMerge,
  MessageSquarePlus,
  Monitor,
  PictureInPicture2,
  Play,
  RotateCw,
  Send,
  Square,
  SquareTerminal,
  Upload,
  UsersRound,
  X,
} from 'lucide-react';
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent,
  type ComponentProps,
  type DragEvent,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
  Suspense,
} from 'react';
import Markdown, { type Components } from 'react-markdown';
import { useLocation, useNavigate, useSearchParams } from 'react-router';
import remarkGfm from 'remark-gfm';
import { getJson, postJson, upload } from './api';
import { clipboardHeld, typedInto } from './clipboard';
import { ConfirmDialog, NameDialog } from './dialogs';
import { Frame, FOLDERS, Loaded, Loading, SIDE_SEPARATOR, useWide } from './frame';
import { Splitter, useWidth } from './split';
import { useI18n } from './i18n';
import { Memory, useMemoryWaiting } from './memory';
import { type Host, Limits, Machine, type Usage } from './workspaceLimits';
import type { MessageKey } from './i18n/hr';
import { ContextMenuArea, Menu, MenuChoices, MenuItem, MenuSub } from './menu';
import { useMenuPress } from './press';
import { button, field, iconButton, primaryButton } from './styles';
import { codeText, errorMessage, Failure } from './tree';
import { useHeldRelease } from './release';
import { useFilePicker } from './upload';
import { DictateButton } from './voice';
import { setAside, useOpenWorkspace } from './workspace';
import { hasScreens, toNextScreen } from './meetingWindow';
import { useThemeOf } from './theme';
import { useFollowed } from './followed';
import { useTitle } from './title';
import { lazily } from './lazily';

/** Above this a chat's next turn costs several times one of a fresh chat. */
const LARGE_CONTEXT = 300_000;
const WATCHED = 5_000;

interface Changes {
  files: number;
  added: number;
  removed: number;
}

type State = 'new' | 'working' | 'background' | 'waiting' | 'idle' | 'closed';

interface Chat {
  id: string;
  title: string;
  at: string;
  open: boolean;
  hosted: boolean;
  state: State;
  waitingFor: string | null;
  context: number | null;
  model: string | null;
  changes: Changes | null;
  coordinator: string | null;
}

/** A model a chat may run on: Claude Code's short name for it, its name and the model it means. */
interface Model {
  value: string;
  name: string;
  resolved: string;
}

/** What a chat last said through its hooks: that it answered, or that it waits on its owner. */
interface Heard {
  event: 'stop' | 'notification';
  at: string;
  message: string | null;
  said: string | null;
}

/** A chat of a round, which has no session until its first message is sent. */
interface Member {
  id: string | null;
  name: string | null;
  title: string;
  task: string | null;
  state: State;
  hosted: boolean;
  waitingFor: string | null;
  at: string | null;
  context: number | null;
  model: string | null;
  changes: Changes | null;
  heard: Heard | null;
}

interface Round {
  id: string;
  created: string | null;
  started: string | null;
  auto: boolean;
  asked: string | null;
  coordinator: Member;
  chats: Member[];
}

interface Run {
  tree: string;
  outcome: 'passed' | 'failed';
  at: string;
  pushed: boolean;
}

interface Gate {
  checked: { tree: string; at: string } | null;
  pushed: { commit: string; tree: string; at: string } | null;
  browser: Run | null;
  night: (Run & { failed: number | null }) | null;
  running: ('browser' | 'night')[];
}

interface Plan {
  title: string;
  path: string;
}

interface Project {
  name: string | null;
  path: string;
  gate: Gate | null;
  plan: Plan | null;
  chats: Chat[];
  rounds: Round[];
  aside: boolean;
}

interface Restart {
  sessions: number;
  working: { id: string; name: string | null; state: State; title: string | null }[];
  scripts: { script: 'check-full' | 'release'; kind: string; project: string | null }[];
}

interface Listed {
  projects: Project[];
  restart: Restart | null;
  usage: Usage | null;
  models: Model[];
  host: Host | null;
}

type Kind =
  | 'chat'
  | 'start'
  | 'consolidate'
  | 'push'
  | 'auto'
  | 'say'
  | 'answer'
  | 'rename'
  | 'model'
  | 'close'
  | 'open'
  | 'archive'
  | 'restart'
  | 'stop'
  | 'move';

type Progress = 'sent' | 'taken' | 'done' | 'failed';

/** What the owner asked of the workspace from here, and how far it got (D52). */
interface Command {
  id: number;
  kind: Kind;
  folder: string | null;
  round: string | null;
  session: string | null;
  text: string | null;
  images: number;
  auto: boolean;
  state: Progress;
  error: string | null;
  created_at: string;
  changed_at: string;
}

interface Asked {
  kind: Kind;
  folder?: string;
  round?: string;
  session?: string;
  text?: string;
  images?: string[];
}

type Said =
  | { role: 'user' | 'assistant' | 'tool'; text: string; at: string | null; images?: number }
  | { role: 'harness'; kind: Harness; text: string; at: string | null };

/** What the harness told the agent in the owner's place: a background task's notice, another
    session's message, the conversation compacted. */
type Harness = 'task' | 'peer' | 'compacted';

const HARNESS: Record<Harness, MessageKey> = {
  task: 'workspace.harness.task',
  peer: 'workspace.harness.peer',
  compacted: 'workspace.harness.compacted',
};

interface Transcript {
  id: string;
  title: string | null;
  state: State;
  waitingFor: string | null;
  said: Said[];
  /** Where in the chat's transcript this page begins, null at its start. */
  earlier: number | null;
}

/** The pages of a chat read before its latest one, and where its latest one begins. */
interface Older {
  id: string;
  said: Said[];
  earlier: number | null;
  boundary: number;
}

/** A chat of the workspace as the page knows it, wherever it is listed. */
interface Known {
  id: string;
  title: string;
  project: Project;
  state: State;
  hosted: boolean;
  waitingFor: string | null;
  model: string | null;
}

const STATES: Record<State, { label: MessageKey; look: string }> = {
  new: { label: 'workspace.state.new', look: 'text-muted' },
  working: { label: 'workspace.state.working', look: 'text-accent' },
  background: { label: 'workspace.state.background', look: 'text-accent' },
  waiting: { label: 'workspace.state.waiting', look: 'font-semibold text-danger' },
  idle: { label: 'workspace.state.idle', look: 'text-ink' },
  closed: { label: 'workspace.state.closed', look: 'text-muted' },
};

const COMMANDS = ['workspace', 'commands'];

const PROGRESS: Record<Progress, { label: MessageKey; look: string }> = {
  sent: { label: 'workspace.progress.sent', look: 'text-muted' },
  taken: { label: 'workspace.progress.taken', look: 'text-accent' },
  done: { label: 'workspace.progress.done', look: 'text-ink' },
  failed: { label: 'workspace.progress.failed', look: 'font-semibold text-danger' },
};

/** What the owner keeps saying to a chat, sent at a press. */
const QUICK: { label: MessageKey; text: string }[] = [
  { label: 'workspace.quick.catchup', text: 'catchup' },
  { label: 'workspace.quick.continue', text: 'nastavi' },
  { label: 'workspace.quick.handoff', text: 'handoff' },
];

function useCommands() {
  return useQuery({
    queryKey: COMMANDS,
    queryFn: () => getJson<{ commands: Command[] }>('/api/workspace/commands'),
    retry: false,
  });
}

function useCommand() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (asked: Asked) => postJson<Command>('/api/workspace/commands', asked),
    onSettled: () => client.invalidateQueries({ queryKey: COMMANDS }),
  });
}

const PROJECTS = ['workspace', 'projects'];

function useAside() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (moved: { name: string; aside: boolean }) =>
      postJson<void>('/api/workspace/projects', moved),
    onSettled: () => client.invalidateQueries({ queryKey: PROJECTS }),
  });
}

function tabOf(project: Project): string {
  return `ponistra-code-${project.name ?? 'general'}`;
}

function queryOf(path: string, chat: string): string {
  return `?${new URLSearchParams({ folder: path, chat })}`;
}

/** What a chat's model reads as a picture: no more than four, each fitted to the longest side the
    model reads whole and to the size the workspace takes. */
const PICTURE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
const PICTURES = 4;
const PICTURE_SIDE = 1568;
const PICTURE_SIZE = 3_750_000;

class PictureRefused extends Error {}

async function encoded(canvas: HTMLCanvasElement, type: string): Promise<Blob> {
  const blob = await new Promise<Blob | null>((done) => canvas.toBlob(done, type, 0.9));
  if (!blob) throw new PictureRefused('image_unread');
  return blob;
}

async function fitted(file: File): Promise<Blob> {
  if (!PICTURE_TYPES.includes(file.type)) throw new PictureRefused('image_type');
  if (file.type === 'image/gif') {
    if (file.size > PICTURE_SIZE) throw new PictureRefused('image_too_large');
    return file;
  }
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  const scale = Math.min(1, PICTURE_SIDE / Math.max(bitmap.width, bitmap.height));
  if (scale === 1 && file.size <= PICTURE_SIZE) {
    bitmap.close();
    return file;
  }
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  let blob = await encoded(canvas, file.type);
  if (blob.size > PICTURE_SIZE && file.type === 'image/png')
    blob = await encoded(canvas, 'image/jpeg');
  if (blob.size > PICTURE_SIZE) throw new PictureRefused('image_too_large');
  return blob;
}

interface Picture {
  key: number;
  url: string | null;
  sha256: string | null;
  failure: Error | null;
}

let pictureKeys = 0;

/** The images of a message being written, each fitted and uploaded the moment it is added. */
function usePictures() {
  const [items, setItems] = useState<Picture[]>([]);
  const [refused, setRefused] = useState<string | null>(null);
  const change = (key: number, part: Partial<Picture>) =>
    setItems((all) => all.map((each) => (each.key === key ? { ...each, ...part } : each)));
  const add = (files: File[]) => {
    const pictures = files.filter((file) => file.type.startsWith('image/'));
    setRefused(items.length + pictures.length > PICTURES ? 'too_many_images' : null);
    const taken = pictures
      .slice(0, Math.max(0, PICTURES - items.length))
      .map((file) => ({ file, key: ++pictureKeys }));
    setItems((all) => [
      ...all,
      ...taken.map(({ key }) => ({ key, url: null, sha256: null, failure: null })),
    ]);
    for (const { file, key } of taken)
      fitted(file)
        .then(async (blob) => {
          change(key, { url: URL.createObjectURL(blob) });
          change(key, { sha256: (await upload(blob)).sha256 });
        })
        .catch((failure: Error) => change(key, { failure }));
  };
  useHeldRelease(items.some((each) => !each.sha256 && !each.failure));
  const held = useRef(items);
  useEffect(() => {
    held.current = items;
  }, [items]);
  useEffect(
    () => () => {
      for (const each of held.current) if (each.url) URL.revokeObjectURL(each.url);
    },
    [],
  );
  const drop = (key: number) =>
    setItems((all) =>
      all.filter((each) => {
        if (each.key === key && each.url) URL.revokeObjectURL(each.url);
        return each.key !== key;
      }),
    );
  return {
    items,
    refused,
    refuse: setRefused,
    add,
    drop,
    ready: items.every((each) => each.sha256),
    given: () => items.map((each) => each.sha256!),
    clear: () => {
      for (const each of items) if (each.url) URL.revokeObjectURL(each.url);
      setItems([]);
      setRefused(null);
    },
  };
}

type Pictured = ReturnType<typeof usePictures>;

/** Pasting or dropping images into a field adds them to its message; words pasted stay words.
 * A right click pastes, as in a terminal. */
function picturing(pictures: Pictured) {
  const carries = (event: DragEvent) => event.dataTransfer.types.includes('Files');
  return {
    onContextMenu: (event: MouseEvent<HTMLTextAreaElement>) => {
      const field = event.currentTarget;
      event.preventDefault();
      clipboardHeld().then(
        ({ text, files }) => {
          pictures.refuse(null);
          if (text) typedInto(field, text);
          else pictures.add(files);
        },
        () => pictures.refuse('clipboard_refused'),
      );
    },
    onPaste: (event: ClipboardEvent) => {
      const files = [...event.clipboardData.files];
      if (files.length === 0 || event.clipboardData.getData('text/plain')) return;
      event.preventDefault();
      pictures.add(files);
    },
    onDragOver: (event: DragEvent) => {
      if (carries(event)) event.preventDefault();
    },
    onDrop: (event: DragEvent) => {
      if (!carries(event)) return;
      event.preventDefault();
      pictures.add([...event.dataTransfer.files]);
    },
  };
}

function PictureButton({ pictures }: { pictures: Pictured }) {
  const { t } = useI18n();
  const picker = useFilePicker(pictures.add, { accept: PICTURE_TYPES.join(',') });
  return (
    <>
      {picker.element}
      <button
        type="button"
        aria-label={t('workspace.addImage')}
        title={t('workspace.addImage')}
        disabled={pictures.items.length >= PICTURES}
        onClick={() => picker.open()}
        className={iconButton}
      >
        <ImagePlus size={18} aria-hidden />
      </button>
    </>
  );
}

function Pictures({ pictures }: { pictures: Pictured }) {
  const { t } = useI18n();
  if (!pictures.items.length && !pictures.refused) return null;
  return (
    <>
      {pictures.items.length > 0 && (
        <ul aria-label={t('workspace.images')} className="flex flex-wrap gap-2">
          {pictures.items.map((each) => (
            <li key={each.key} className="relative">
              {each.url ? (
                <img
                  src={each.url}
                  alt=""
                  className={`size-14 rounded border border-line object-cover ${each.sha256 ? '' : 'opacity-60'}`}
                />
              ) : (
                <span className="block size-14 rounded border border-line bg-surface" />
              )}
              {each.failure && (
                <span className="block max-w-28 text-xs text-danger">
                  {each.failure instanceof PictureRefused
                    ? codeText(each.failure.message, t)
                    : errorMessage(each.failure, t)}
                </span>
              )}
              <button
                type="button"
                aria-label={t('workspace.removeImage')}
                title={t('workspace.removeImage')}
                onClick={() => pictures.drop(each.key)}
                className="absolute -top-1.5 -right-1.5 rounded-full border border-line bg-raised p-0.5 text-muted hover:text-ink"
              >
                <X size={12} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      {pictures.refused && <p className="text-sm text-danger">{codeText(pictures.refused, t)}</p>}
    </>
  );
}

function useWhen() {
  const { formatDay, formatShortDay, formatTime } = useI18n();
  const today = formatDay(new Date());
  return (when: string) => {
    const at = new Date(when);
    return formatDay(at) === today ? formatTime(at) : formatShortDay(at);
  };
}

/** How much a chat holds and what it changed in the tree, beside its line. */
function Measures({ context, changes }: { context: number | null; changes: Changes | null }) {
  const { t, formatNumber } = useI18n();
  const large = context !== null && context > LARGE_CONTEXT;
  return (
    <>
      {changes && changes.files > 0 && (
        <span
          className="flex shrink-0 items-center gap-1 text-xs text-muted tabular-nums"
          title={t('workspace.changes')}
        >
          <FileDiff size={12} aria-hidden />
          {formatNumber(changes.files)}
          <span>+{formatNumber(changes.added)}</span>
          <span>−{formatNumber(changes.removed)}</span>
        </span>
      )}
      {context !== null && (
        <span
          className={`shrink-0 text-xs tabular-nums ${large ? 'font-semibold text-danger' : 'text-muted'}`}
          title={t(large ? 'workspace.contextLarge' : 'workspace.context')}
        >
          {formatNumber(Math.round(context / 1000))}k
        </span>
      )}
    </>
  );
}

/** A run of the gate as words: running, or how it went, when, and whether on the latest push. */
function useRunText() {
  const { t, formatNumber } = useI18n();
  const when = useWhen();
  return (label: MessageKey, run: Run | null, running: boolean): string | null => {
    if (running) return `${t(label)} ${t('workspace.gate.running')}`;
    if (!run) return null;
    const failed = 'failed' in run && typeof run.failed === 'number' ? run.failed : null;
    return [
      t(label),
      t(run.outcome === 'passed' ? 'workspace.gate.passed' : 'workspace.gate.failed'),
      failed !== null && `(${formatNumber(failed)})`,
      when(run.at),
      !run.pushed && `· ${t('workspace.gate.older')}`,
    ]
      .filter(Boolean)
      .join(' ');
  };
}

type Status = { text: string; failed?: boolean };

/** How the project's gate last went, the rest folded beneath the first until asked for. */
function StatusLine({ project }: { project: Project }) {
  const { t, formatNumber } = useI18n();
  const when = useWhen();
  const runText = useRunText();
  const [open, setOpen] = useState(false);
  const { gate } = project;
  const parts: Status[] = [];
  if (gate?.checked)
    parts.push({ text: `${t('workspace.gate.checked')} ${when(gate.checked.at)}` });
  for (const [label, key] of [
    ['workspace.gate.browser', 'browser'],
    ['workspace.gate.night', 'night'],
  ] as const) {
    const text = gate && runText(label, gate[key], gate.running.includes(key));
    if (text) parts.push({ text, failed: gate[key]?.outcome === 'failed' });
  }
  if (!parts.length) return null;
  const [first, ...rest] = parts;
  const failed = rest.some((part) => part.failed);
  const item = (part: Status) => <span className="truncate">{part.text}</span>;
  return (
    <ul className="mt-0.5 px-2 text-xs text-muted">
      <li className={`flex min-w-0 items-center gap-1 ${first.failed ? 'text-danger' : ''}`}>
        {item(first)}
        {rest.length > 0 && (
          <button
            type="button"
            aria-expanded={open}
            aria-label={t('workspace.gate')}
            title={t('workspace.gate')}
            onClick={() => setOpen(!open)}
            className={`flex shrink-0 items-center rounded hover:text-accent ${failed ? 'font-semibold text-danger' : ''}`}
          >
            <ChevronRight size={12} aria-hidden className={open ? 'rotate-90' : undefined} />
            {formatNumber(rest.length)}
          </button>
        )}
      </li>
      {open &&
        rest.map((part, at) => (
          <li key={at} className={`flex min-w-0 ${part.failed ? 'text-danger' : ''}`}>
            {item(part)}
          </li>
        ))}
    </ul>
  );
}

const ROW =
  'block w-full min-w-0 rounded px-2 py-1.5 text-left hover:bg-hover disabled:text-muted disabled:hover:bg-transparent';

/** A chat as two lines: its title with its state and time in columns of their own, which every
 * row keeps, and below it what else is known of it. */
function Line({
  title,
  state,
  at,
  meta,
}: {
  title: string;
  state?: { label: string; look: string; hint?: string };
  at: string | null;
  meta?: ReactNode;
}) {
  const when = useWhen();
  return (
    <>
      <span className="flex min-w-0 items-baseline gap-2">
        <span className="min-w-0 flex-1 truncate text-sm">{title}</span>
        <span
          className={`w-20 shrink-0 truncate text-right text-xs ${state?.look ?? ''}`}
          title={state?.hint}
        >
          {state?.label}
        </span>
        <span className="w-12 shrink-0 text-right text-xs whitespace-nowrap text-muted tabular-nums">
          {at && when(at)}
        </span>
      </span>
      {meta && (
        <span className="mt-0.5 flex min-w-0 items-center gap-2 text-xs text-muted">{meta}</span>
      )}
    </>
  );
}

/** The longest name a chat takes, as the workspace allows it. */
const TITLE = 100;

type Choose = (session: string) => void;

/** A chat the editor may not take over yet: the workspace's process is in the middle of a turn. */
const AT_WORK = new Set<State>(['working', 'waiting']);

/** A chat that has done its part. */
const FINISHED = new Set<State>(['idle', 'closed']);

/** A tree the gate found green that no push has carried yet. */
function pushable({ gate }: Project): boolean {
  const checked = gate?.checked;
  if (!checked) return false;
  const pushed = gate.pushed;
  return (
    !pushed || (checked.tree !== pushed.tree && Date.parse(checked.at) > Date.parse(pushed.at))
  );
}

const offered =
  'inline-flex items-center gap-1 rounded bg-accent px-2 py-1 text-xs font-medium text-on-accent hover:bg-accent-hover disabled:opacity-60';

/** The push the coordinator's row offers once its round is consolidated and green. */
function Offer({ disabled, onPress }: { disabled: boolean; onPress: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex justify-end px-2 pb-1">
      <button type="button" disabled={disabled} onClick={onPress} className={offered}>
        <Upload size={14} aria-hidden />
        {t('workspace.push')}
      </button>
    </div>
  );
}

/** The project whose chats the list shows, and its rounds, which a chat may be moved into. */
interface Moves {
  folder: string;
  rounds: Round[];
}

const Moving = createContext<Moves | null>(null);

/** The chat being dragged, which a round's drop target reads before the drop shows it. */
let carried: { session: string; folder: string } | null = null;

function joins(round: Round, session: string): boolean {
  return round.coordinator.id !== session && !round.chats.some((chat) => chat.id === session);
}

/** A chat's line; its menu opens, renames, moves under a round's coordinator, closes or archives
    the chat, and a mouse drags it onto a coordinator. */
function ChatRow({
  session,
  title,
  state,
  menu,
  children,
}: {
  session: string;
  title: string;
  state: State;
  menu?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const press = useMenuPress();
  const opened = useContext(Opening);
  const moves = useContext(Moving);
  const targets = moves?.rounds.filter((round) => joins(round, session)) ?? [];
  const archived = useCommand();
  const commands = useCommands();
  const [renaming, setRenaming] = useState(false);
  const failed = commands.data?.commands.find(
    (command) => command.id === archived.data?.id && command.state === 'failed',
  );
  if (!opened) throw new Error('ChatRow needs the Opening of the Pult');
  return (
    <>
      <ContextMenuArea
        items={
          <>
            <MenuItem
              icon={ExternalLink}
              label={t('workspace.openChat')}
              disabled={AT_WORK.has(state)}
              onSelect={() => opened(session)}
            />
            <MenuItem icon={Pencil} label={t('tree.rename')} onSelect={() => setRenaming(true)} />
            {targets.length > 0 && (
              <MenuSub icon={FolderInput} label={t('workspace.moveUnder')}>
                {targets.map((round) => (
                  <MenuItem
                    key={round.id}
                    icon={UsersRound}
                    label={round.coordinator.title}
                    onSelect={() => archived.mutate({ kind: 'move', session, round: round.id })}
                  />
                ))}
              </MenuSub>
            )}
            {menu}
            {state !== 'closed' && (
              <MenuItem
                icon={X}
                label={t('workspace.close')}
                onSelect={() => archived.mutate({ kind: 'close', session })}
              />
            )}
            <MenuItem
              icon={Archive}
              label={t('workspace.archive')}
              onSelect={() => archived.mutate({ kind: 'archive', session })}
            />
          </>
        }
      >
        <div
          {...press}
          draggable={Boolean(moves?.rounds.length) && matchMedia('(pointer: fine)').matches}
          onDragStart={(event) => {
            if (!moves) return;
            carried = { session, folder: moves.folder };
            event.dataTransfer.setData('text/plain', title);
            event.dataTransfer.effectAllowed = 'move';
          }}
          onDragEnd={() => {
            carried = null;
          }}
        >
          {children}
        </div>
      </ContextMenuArea>
      {archived.isError && (
        <p className="px-2 text-sm text-danger">{errorMessage(archived.error, t)}</p>
      )}
      {failed?.error && <p className="px-2 text-sm text-danger">{codeText(failed.error, t)}</p>}
      {renaming && (
        <NameDialog
          heading={t('tree.rename')}
          submitLabel={t('tree.save')}
          initial={title}
          maxLength={TITLE}
          onSubmit={(text) => archived.mutateAsync({ kind: 'rename', session, text })}
          onDone={() => setRenaming(false)}
          onClose={() => setRenaming(false)}
        />
      )}
    </>
  );
}

function MemberLine({
  member,
  coordinator,
  chosen,
  onChoose,
  menu,
}: {
  member: Member;
  coordinator: boolean;
  chosen: boolean;
  onChoose: Choose;
  menu?: ReactNode;
}) {
  const { t } = useI18n();
  const state = STATES[member.state];
  const name = member.name !== member.title ? member.name : null;
  const known = coordinator || name || member.context !== null || Boolean(member.changes?.files);
  const line = (
    <Line
      title={member.title}
      state={{ label: t(state.label), look: state.look, hint: member.waitingFor ?? undefined }}
      at={member.at}
      meta={
        known && (
          <>
            {coordinator && <span>{t('workspace.coordinator')}</span>}
            {name && <span>{name}</span>}
            <Measures context={member.context} changes={member.changes} />
          </>
        )
      }
    />
  );
  const id = member.id;
  if (!id) {
    return (
      <details className="rounded px-2 py-1.5">
        <summary className="block min-w-0 cursor-pointer">{line}</summary>
        {member.task && (
          <p className="mt-2 text-sm whitespace-pre-wrap text-muted">{member.task}</p>
        )}
      </details>
    );
  }
  return (
    <ChatRow session={id} title={member.title} state={member.state} menu={menu}>
      <button
        type="button"
        aria-current={chosen || undefined}
        onClick={() => onChoose(id)}
        className={`${ROW} ${chosen ? 'bg-selected' : ''}`}
      >
        {line}
      </button>
    </ChatRow>
  );
}

function RoundCard({
  round,
  green,
  chosen,
  onChoose,
}: {
  round: Round;
  green: boolean;
  chosen: string | null;
  onChoose: Choose;
}) {
  const { t } = useI18n();
  const command = useCommand();
  const commands = useCommands();
  const moves = useContext(Moving);
  const [over, setOver] = useState(false);
  const accepts = () =>
    carried !== null && carried.folder === moves?.folder && joins(round, carried.session);
  const title = t('workspace.round').replace('{name}', round.coordinator.title);
  const failed = commands.data?.commands.find(
    (each) => each.id === command.data?.id && each.state === 'failed',
  );
  const unsent = round.chats.some((chat) => !chat.id);
  const asking = command.isPending || Boolean(round.asked);
  const asked = (kind: Kind, text?: string) =>
    command.mutate({ kind, round: round.id, ...(text && { text }) });
  const lead = round.coordinator;
  const finished =
    Boolean(round.started) &&
    round.chats.length > 0 &&
    round.chats.every((chat) => FINISHED.has(chat.state));
  const consolidated = commands.data?.commands.some(
    (each) =>
      each.kind === 'consolidate' &&
      each.round === round.id &&
      each.state === 'done' &&
      lead.at !== null &&
      Date.parse(each.changed_at) < Date.parse(lead.at),
  );
  const pushable = finished && lead.state === 'idle' && !round.asked && consolidated && green;
  const [first, ...chats] = [lead, ...round.chats].map((member, index) => (
    <li key={member.id ?? `new-${index}`}>
      <MemberLine
        member={member}
        coordinator={index === 0}
        chosen={member.id !== null && member.id === chosen}
        onChoose={onChoose}
        menu={
          index === 0 && (
            <MenuItem
              icon={GitMerge}
              label={t('workspace.auto')}
              checked={round.auto}
              disabled={command.isPending}
              onSelect={() => asked('auto', round.auto ? 'off' : 'on')}
            />
          )
        }
      />
      {index === 0 && pushable && <Offer disabled={asking} onPress={() => asked('push')} />}
    </li>
  ));
  return (
    <section
      aria-label={title}
      onDragOver={(event) => {
        if (!accepts()) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        setOver(true);
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false);
      }}
      onDrop={(event) => {
        setOver(false);
        if (!accepts()) return;
        event.preventDefault();
        command.mutate({ kind: 'move', session: carried!.session, round: round.id });
        carried = null;
      }}
      className={`mt-2 rounded ${over ? 'outline-2 -outline-offset-2 outline-focus' : ''}`}
    >
      {!round.started && unsent && (
        <div className="mx-2 mt-1 flex flex-wrap items-center gap-2 rounded-lg border border-accent bg-selected px-3 py-2">
          <span className="min-w-0 flex-1 text-sm font-semibold">
            {t('workspace.startWaiting')}
          </span>
          <button
            type="button"
            disabled={command.isPending}
            onClick={() => asked('start')}
            className={primaryButton}
          >
            <Play size={16} aria-hidden />
            {t('workspace.start')}
          </button>
        </div>
      )}
      {round.asked && (
        <p className="mt-1 px-2 text-sm text-muted" role="status">
          {t('workspace.asked').replace('{word}', round.asked)}
        </p>
      )}
      {command.isError && (
        <p className="mt-1 px-2 text-sm text-danger">{errorMessage(command.error, t)}</p>
      )}
      {failed?.error && (
        <p className="mt-1 px-2 text-sm text-danger">{codeText(failed.error, t)}</p>
      )}
      <ul className="mt-0.5 flex flex-col gap-0.5">
        {first}
        {chats.length > 0 && (
          <li>
            <ul className="ml-4 flex flex-col gap-0.5 border-l border-line pl-1">{chats}</ul>
          </li>
        )}
      </ul>
    </section>
  );
}

/** Enter sends, as in Conversations; Shift+Enter starts a new line, and so does a phone's Enter,
    as its keyboard has no Shift to hold for one. */
function sends(event: KeyboardEvent<HTMLTextAreaElement>): boolean {
  return (
    event.key === 'Enter' &&
    !event.shiftKey &&
    !event.nativeEvent.isComposing &&
    matchMedia('(pointer: fine)').matches
  );
}

/** A new chat's first message, with its images; a new round's is said to its coordinator as
    `nastavi: …`, which it divides. */
function NewChat({
  folder,
  name,
  round,
  onStarted,
  onClose,
}: {
  folder: string;
  name: string;
  round: boolean;
  onStarted: (session: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [said, setSaid] = useState('');
  const typed = useRef<HTMLTextAreaElement>(null);
  useEffect(() => typed.current?.focus(), []);
  const pictures = usePictures();
  const started = useCommand();
  const failed = started.data?.state === 'failed' ? started.data.error : null;
  const start = () => {
    const text = said.trim();
    if (!round && !text) return;
    started.mutate(
      {
        kind: 'chat',
        folder,
        text: round ? (text ? `nastavi: ${text}` : 'nastavi') : text,
        ...(pictures.items.length && { images: pictures.given() }),
      },
      {
        onSuccess: (command) => {
          if (command.session) onStarted(command.session);
        },
      },
    );
  };
  const titled = t(round ? 'workspace.newRound' : 'workspace.newChat');
  return (
    <section aria-label={titled} className="flex min-w-0 flex-col gap-2">
      <h2 className="text-base font-semibold">
        {titled} <span className="font-normal text-muted">{name}</span>
      </h2>
      <form
        className="flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          start();
        }}
      >
        <textarea
          ref={typed}
          aria-label={t(round ? 'workspace.newRoundText' : 'workspace.newChatText')}
          placeholder={t(round ? 'workspace.newRoundText' : 'workspace.newChatText')}
          value={said}
          onChange={(event) => setSaid(event.target.value)}
          onKeyDown={(event) => {
            if (sends(event)) {
              event.preventDefault();
              start();
            }
          }}
          {...picturing(pictures)}
          rows={8}
          className={`${field} w-full`}
        />
        <Pictures pictures={pictures} />
        {started.isError && <p className="text-sm text-danger">{errorMessage(started.error, t)}</p>}
        {failed && <p className="text-sm text-danger">{codeText(failed, t)}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <DictateButton
            onText={(text) => setSaid((now) => (now.trim() ? `${now.trimEnd()} ${text}` : text))}
          />
          <PictureButton pictures={pictures} />
          <button type="button" onClick={onClose} className={`${button} ml-auto`}>
            {t('tree.cancel')}
          </button>
          <button
            type="submit"
            disabled={started.isPending || !pictures.ready || (!round && !said.trim())}
            className={primaryButton}
          >
            {round ? <UsersRound size={16} aria-hidden /> : <Send size={16} aria-hidden />}
            {t(round ? 'workspace.openRound' : 'workspace.startChat')}
          </button>
        </div>
      </form>
    </section>
  );
}

/** A project by the name its plan gives it (`Plan DIDA` → DIDA), else its folder's capitalised. */
function titled({ name, plan }: Project): string | null {
  if (name === null) return null;
  const planned = plan?.title.replace(/^Plan\s+/, '');
  if (planned?.toLowerCase() === name.toLowerCase()) return planned;
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** The chats each with those its coordinator led beside it; a chat whose coordinator is not
 * listed stands alone. */
function ledBy(chats: Chat[]): { chat: Chat; led: Chat[] }[] {
  const listed = new Set(chats.map((chat) => chat.id));
  return chats
    .filter((chat) => !chat.coordinator || !listed.has(chat.coordinator))
    .map((chat) => ({ chat, led: chats.filter((each) => each.coordinator === chat.id) }));
}

function ChatLine({
  chat,
  chosen,
  onChoose,
}: {
  chat: Chat;
  chosen: string | null;
  onChoose: Choose;
}) {
  const { t } = useI18n();
  const state = STATES[chat.state];
  const measured = chat.context !== null || Boolean(chat.changes?.files);
  return (
    <ChatRow session={chat.id} title={chat.title} state={chat.state}>
      <button
        type="button"
        aria-current={chat.id === chosen || undefined}
        onClick={() => onChoose(chat.id)}
        className={`${ROW} ${chat.id === chosen ? 'bg-selected' : ''}`}
      >
        <Line
          title={chat.title}
          state={
            chat.open
              ? {
                  label: t(chat.state === 'idle' ? 'workspace.inUse' : state.label),
                  look: state.look,
                }
              : undefined
          }
          at={chat.at}
          meta={measured && <Measures context={chat.context} changes={chat.changes} />}
        />
      </button>
    </ChatRow>
  );
}

const small =
  'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted hover:bg-hover hover:text-ink disabled:opacity-60';

function ProjectSection({
  project,
  chosen,
  onChoose,
  onTerminal,
  starting: asked,
  onStart,
}: {
  project: Project;
  chosen: string | null;
  onChoose: Choose;
  onTerminal: (folder: string, name: string) => void;
  starting: Starting | null;
  onStart: (starting: Starting) => void;
}) {
  const { t, formatNumber } = useI18n();
  const starting = asked?.folder === project.path ? (asked.round ? 'round' : 'chat') : null;
  const [archived, setArchived] = useState(false);
  const name = titled(project) ?? t('workspace.general');
  const pushed = useCommand();
  const moved = useAside();
  const folder = project.name;
  const press = useMenuPress();
  const navigate = useNavigate();
  const green = pushable(project);
  const closed = project.chats.filter((chat) => !chat.open).length;
  const due =
    green && !project.rounds.length
      ? ledBy(project.chats).find(({ led }) => led.length > 0)?.chat
      : undefined;
  const pushing = due && !AT_WORK.has(due.state) ? due.id : null;
  const chats = archived
    ? project.chats
    : project.chats.filter((chat) => chat.open || chat.id === pushing);
  return (
    <section aria-label={name} className="border-t border-line pt-3 first:border-t-0 first:pt-0">
      <ContextMenuArea
        items={
          (project.plan || folder !== null) && (
            <>
              {project.plan && (
                <MenuItem
                  icon={ClipboardList}
                  label={t('workspace.openPlan')}
                  onSelect={() => navigate(project.plan!.path)}
                />
              )}
              {folder !== null && (
                <MenuItem
                  icon={project.aside ? ArrowUpToLine : ArrowDownToLine}
                  label={t(project.aside ? 'workspace.others.back' : 'workspace.others.put')}
                  onSelect={() => moved.mutate({ name: folder, aside: !project.aside })}
                />
              )}
            </>
          )
        }
      >
        <div {...press} className="flex min-w-0 items-start gap-1">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-base font-semibold">
              {closed ? (
                <button
                  type="button"
                  aria-expanded={archived}
                  onClick={() => setArchived(!archived)}
                  className="flex min-w-0 items-center gap-1 rounded hover:text-accent"
                >
                  <span className="truncate">{name}</span>
                  <span className="text-xs font-normal text-muted">{formatNumber(closed)}</span>
                </button>
              ) : (
                name
              )}
            </h2>
          </div>
          <div className="flex h-6 shrink-0 items-center gap-1">
            <button
              type="button"
              aria-pressed={starting === 'round'}
              aria-label={t('workspace.newRound')}
              title={t('workspace.newRound')}
              onClick={() => onStart({ folder: project.path, name, round: true })}
              className={`${small} shrink-0`}
            >
              <UsersRound size={16} aria-hidden />
            </button>
            <button
              type="button"
              aria-pressed={starting === 'chat'}
              aria-label={t('workspace.newChat')}
              title={t('workspace.newChat')}
              onClick={() => onStart({ folder: project.path, name, round: false })}
              className={`${small} shrink-0`}
            >
              <MessageSquarePlus size={16} aria-hidden />
            </button>
            <button
              type="button"
              aria-label={t('workspace.terminal.open')}
              title={t('workspace.terminal.open')}
              onClick={() => onTerminal(project.path, name)}
              className={`${small} shrink-0`}
            >
              <SquareTerminal size={16} aria-hidden />
            </button>
          </div>
        </div>
      </ContextMenuArea>
      {moved.isError && <p className="px-2 text-sm text-danger">{errorMessage(moved.error, t)}</p>}
      <StatusLine project={project} />
      <Moving value={{ folder: project.path, rounds: project.rounds }}>
        {project.rounds.map((round) => (
          <RoundCard
            key={round.id}
            round={round}
            green={green}
            chosen={chosen}
            onChoose={onChoose}
          />
        ))}
        <ul className="mt-1 flex flex-col gap-0.5">
          {ledBy(chats).map(({ chat, led }) => (
            <li key={chat.id}>
              <ChatLine chat={chat} chosen={chosen} onChoose={onChoose} />
              {chat.id === pushing && (
                <>
                  <Offer
                    disabled={pushed.isPending}
                    onPress={() => pushed.mutate({ kind: 'push', session: chat.id })}
                  />
                  {pushed.isError && (
                    <p className="px-2 text-sm text-danger">{errorMessage(pushed.error, t)}</p>
                  )}
                </>
              )}
              {led.length > 0 && (
                <ul className="ml-4 flex flex-col gap-0.5 border-l border-line pl-1">
                  {led.map((each) => (
                    <li key={each.id}>
                      <ChatLine chat={each} chosen={chosen} onChoose={onChoose} />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </Moving>
    </section>
  );
}

/** Yes or No to what a waiting chat asks, pressed in its panel as the owner would. */
function Answers({ session }: { session: string }) {
  const { t } = useI18n();
  const answered = useCommand();
  const answer = (text: 'yes' | 'no') => answered.mutate({ kind: 'answer', session, text });
  return (
    <>
      <button
        type="button"
        disabled={answered.isPending}
        onClick={() => answer('yes')}
        className={primaryButton}
      >
        <Check size={16} aria-hidden />
        {t('workspace.yes')}
      </button>
      <button
        type="button"
        disabled={answered.isPending}
        onClick={() => answer('no')}
        className={button}
      >
        <X size={16} aria-hidden />
        {t('workspace.no')}
      </button>
      {answered.isError && (
        <span className="text-sm text-danger">{errorMessage(answered.error, t)}</span>
      )}
    </>
  );
}

function OpenChat({
  chat,
  onOpen,
  look = button,
}: {
  chat: Known;
  onOpen: (chat: Known) => void;
  look?: string;
}) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      disabled={AT_WORK.has(chat.state)}
      onClick={() => onOpen(chat)}
      className={look}
    >
      <ExternalLink size={look === button ? 16 : 14} aria-hidden />
      {t('workspace.openChat')}
    </button>
  );
}

type Shown = { tools: false; said: Said } | { tools: true; said: Said[] };

/** The transcript with each run of tool calls folded into one line. */
function grouped(said: Said[]): Shown[] {
  const shown: Shown[] = [];
  for (const each of said) {
    const last = shown.at(-1);
    if (each.role !== 'tool') shown.push({ tools: false, said: each });
    else if (last?.tools) last.said.push(each);
    else shown.push({ tools: true, said: [each] });
  }
  return shown;
}

/** GFM as React elements: HTML in the text stays text, links leave the page. */
/** Puts a text on the clipboard, saying for a moment that it did or that it could not. */
function CopyButton({ text, className = '' }: { text: () => string; className?: string }) {
  const { t } = useI18n();
  const [done, setDone] = useState<'copied' | 'failed' | null>(null);
  useEffect(() => {
    if (!done) return;
    const shown = setTimeout(() => setDone(null), 2000);
    return () => clearTimeout(shown);
  }, [done]);
  const label = t(
    done === 'copied'
      ? 'workspace.copied'
      : done === 'failed'
        ? 'workspace.copyFailed'
        : 'workspace.copy',
  );
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={() =>
        void navigator.clipboard.writeText(text()).then(
          () => setDone('copied'),
          () => setDone('failed'),
        )
      }
      className={`rounded p-1 hover:bg-hover hover:text-ink ${done === 'failed' ? 'text-danger' : 'text-muted'} ${className}`}
    >
      {done === 'copied' ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
    </button>
  );
}

function CodeBlock({ node: _, ...props }: ComponentProps<'pre'> & { node?: unknown }) {
  const shown = useRef<HTMLPreElement>(null);
  return (
    <div className="relative my-1">
      <pre
        ref={shown}
        {...props}
        className="overflow-x-auto rounded bg-surface p-2 pr-8 font-mono text-xs [&_code]:bg-transparent [&_code]:p-0"
      />
      <CopyButton
        text={() => shown.current?.textContent?.replace(/\n$/, '') ?? ''}
        className="absolute top-1 right-1"
      />
    </div>
  );
}

const MARKDOWN: Components = {
  a: ({ node: _, ...props }) => (
    <a {...props} target="_blank" rel="noreferrer" className="text-link underline" />
  ),
  p: ({ node: _, ...props }) => <p {...props} className="my-1 first:mt-0 last:mb-0" />,
  ul: ({ node: _, ...props }) => <ul {...props} className="my-1 list-disc pl-5" />,
  ol: ({ node: _, ...props }) => <ol {...props} className="my-1 list-decimal pl-5" />,
  h1: ({ node: _, ...props }) => <p {...props} className="my-1 font-semibold" />,
  h2: ({ node: _, ...props }) => <p {...props} className="my-1 font-semibold" />,
  h3: ({ node: _, ...props }) => <p {...props} className="my-1 font-semibold" />,
  h4: ({ node: _, ...props }) => <p {...props} className="my-1 font-semibold" />,
  blockquote: ({ node: _, ...props }) => (
    <blockquote {...props} className="my-1 border-l-2 border-line pl-2 text-muted" />
  ),
  code: ({ node: _, ...props }) => (
    <code {...props} className="rounded bg-surface px-1 font-mono text-[0.85em]" />
  ),
  pre: CodeBlock,
  table: ({ node: _, ...props }) => (
    <div className="my-1 overflow-x-auto">
      <table {...props} className="border-collapse text-xs" />
    </div>
  ),
  th: ({ node: _, ...props }) => (
    <th {...props} className="border border-line px-2 py-1 text-left font-semibold" />
  ),
  td: ({ node: _, ...props }) => <td {...props} className="border border-line px-2 py-1" />,
  hr: () => <hr className="my-2 border-line" />,
};

function Bubble({ said, pinned = false }: { said: Said; pinned?: boolean }) {
  const { t, formatNumber } = useI18n();
  if (said.role === 'harness')
    return (
      <li className="self-center text-center text-xs text-muted">
        {t(HARNESS[said.kind]).replace('{text}', said.text)}
      </li>
    );
  if (said.role === 'user')
    return (
      <li
        className={`max-w-[85%] self-end rounded-lg bg-accent px-3 py-2 text-sm break-words whitespace-pre-wrap text-on-accent ${pinned ? 'sticky top-0 z-10 max-h-[30%] shrink-0 overflow-y-auto shadow-md' : ''}`}
      >
        {said.images ? (
          <span className="flex items-center gap-1 text-xs opacity-80">
            <ImagePlus size={12} aria-hidden />
            {t('workspace.imagesSent').replace('{count}', formatNumber(said.images))}
          </span>
        ) : null}
        {said.text}
      </li>
    );
  return (
    <li className="max-w-[85%] min-w-0 self-start rounded-lg bg-raised px-3 py-2 text-sm break-words">
      <Markdown remarkPlugins={[remarkGfm]} components={MARKDOWN}>
        {said.text}
      </Markdown>
      <div className="-mr-1 -mb-1 flex justify-end">
        <CopyButton text={() => said.text} />
      </div>
    </li>
  );
}

const SENDING: Kind[] = [
  'say',
  'answer',
  'consolidate',
  'push',
  'rename',
  'model',
  'open',
  'close',
  'archive',
  'stop',
];

/** The clocks of the backend and the workspace may differ by this much. */
const SKEW = 60_000;

/** Whether the chat has read what the owner said: the transcript shows the same words since, or
    the words were sent before the part of it read here begins. */
const readIn = (command: Command, said: Said[]) => {
  const sent = Date.parse(command.created_at);
  const first = said.find((each) => each.at !== null)?.at;
  if (first && sent < Date.parse(first)) return true;
  const text = command.text?.trim();
  return said.some(
    (each) =>
      each.role === 'user' &&
      each.text === text &&
      each.at !== null &&
      Date.parse(each.at) >= sent - SKEW,
  );
};

/** One chat as the owner reads it here, with a field whose words its panel sends (D52). */
function Conversation({
  chat,
  commands,
  models,
  onOpen,
}: {
  chat: Known | null;
  commands: Command[];
  models: Model[];
  onOpen: (chat: Known) => void;
}) {
  const { t, formatNumber } = useI18n();
  const [text, setText] = useState('');
  const pictures = usePictures();
  const sent = useCommand();
  const id = chat?.id;
  const [loaded, setLoaded] = useState<Older | null>(null);
  const older = loaded?.id === id ? loaded : null;
  const transcript = useQuery({
    queryKey: ['workspace', 'chats', id, older?.boundary ?? null],
    queryFn: () =>
      getJson<Transcript>(`/api/workspace/chats/${id}${older ? `?from=${older.boundary}` : ''}`),
    enabled: Boolean(id),
    retry: false,
    refetchInterval: chat?.state === 'working' ? WATCHED : false,
    placeholderData: (previous, query) => (query?.queryKey[2] === id ? previous : undefined),
  });
  const reading = useMutation({
    mutationFn: (before: number) =>
      getJson<Transcript>(`/api/workspace/chats/${id}?before=${before}`),
  });
  const list = useRef<HTMLOListElement>(null);
  const atBottom = useRef(true);
  const heightBefore = useRef<number | null>(null);
  const said = useMemo(
    () => [...(older?.said ?? []), ...(transcript.data?.said ?? [])],
    [older, transcript.data],
  );
  const earlier = older ? older.earlier : (transcript.data?.earlier ?? null);
  useEffect(() => {
    atBottom.current = true;
  }, [id]);
  useLayoutEffect(() => {
    const shown = list.current;
    if (!shown) return;
    if (heightBefore.current !== null) {
      shown.scrollTop += shown.scrollHeight - heightBefore.current;
      heightBefore.current = null;
    } else if (atBottom.current) shown.scrollTop = shown.scrollHeight;
  }, [said]);
  const readEarlier = () => {
    const boundary = older?.boundary ?? transcript.data?.earlier;
    if (earlier === null || boundary == null || !id) return;
    reading.mutate(earlier, {
      onSuccess: (page) => {
        heightBefore.current = list.current?.scrollHeight ?? null;
        setLoaded({
          id,
          said: [...page.said, ...(older?.said ?? [])],
          earlier: page.earlier,
          boundary,
        });
      },
    });
  };
  const shownSaid = grouped(said);
  const pinned = shownSaid.findLastIndex((shown) => !shown.tools && shown.said.role === 'user');
  if (!chat) return <p className="text-sm text-muted">{t('workspace.noChat')}</p>;
  const say = (words: string, images: string[] = []) => {
    const saying = words.trim();
    if (!saying || !pictures.ready) return;
    sent.mutate(
      { kind: 'say', session: chat.id, text: saying, ...(images.length && { images }) },
      {
        onSuccess: () => {
          setText((now) => (now.trim() === saying ? '' : now));
          if (images.length) pictures.clear();
        },
      },
    );
  };
  const pending = commands
    .filter(
      (command) =>
        command.session === chat.id &&
        SENDING.includes(command.kind) &&
        (command.state !== 'done' || (command.kind === 'say' && !readIn(command, said))),
    )
    .reverse();
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex min-w-0 items-center gap-1">
        <h2 className="min-w-0 flex-1 truncate text-base font-semibold">
          {chat.title}
          <span className={`ml-2 text-xs font-normal ${STATES[chat.state].look}`}>
            {t(STATES[chat.state].label)}
          </span>
        </h2>
        <OpenChat chat={chat} onOpen={onOpen} look={`${small} shrink-0`} />
      </div>
      {transcript.isError && (
        <p className="text-sm text-danger">{errorMessage(transcript.error, t)}</p>
      )}
      {reading.isError && <p className="text-sm text-danger">{errorMessage(reading.error, t)}</p>}
      <ol
        ref={list}
        aria-label={chat.title}
        onScroll={(event) => {
          const shown = event.currentTarget;
          atBottom.current = shown.scrollTop + shown.clientHeight >= shown.scrollHeight - 8;
        }}
        className="flex max-h-[60dvh] min-h-0 flex-1 flex-col gap-2 overflow-y-auto md:max-h-none"
      >
        {earlier !== null && (
          <li className="self-center">
            <button
              type="button"
              className={small}
              disabled={reading.isPending}
              onClick={readEarlier}
            >
              {t('workspace.earlier')}
            </button>
          </li>
        )}
        {shownSaid.map((shown, index) =>
          shown.tools ? (
            <li key={index} className="self-start text-xs text-muted">
              <details>
                <summary className="cursor-pointer">
                  {t('workspace.tools').replace('{count}', formatNumber(shown.said.length))}
                </summary>
                <ul className="mt-1 flex flex-col gap-0.5 font-mono">
                  {shown.said.map((tool, at) => (
                    <li key={at} className="break-all">
                      {tool.text}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ) : (
            <Bubble key={index} said={shown.said} pinned={index === pinned} />
          ),
        )}
        {pending.map((command) =>
          command.kind === 'say' ? (
            <li
              key={command.id}
              className="max-w-[85%] self-end rounded-lg border border-dashed border-accent px-3 py-2 text-sm break-words whitespace-pre-wrap"
            >
              {command.images > 0 && (
                <span className="flex items-center gap-1 text-xs text-muted">
                  <ImagePlus size={12} aria-hidden />
                  {t('workspace.imagesSent').replace('{count}', formatNumber(command.images))}
                </span>
              )}
              {command.text}
              <span className={`mt-1 block text-xs ${PROGRESS[command.state].look}`}>
                {command.state === 'failed' && command.error
                  ? codeText(command.error, t)
                  : t(
                      command.state === 'done' ? 'workspace.unread' : PROGRESS[command.state].label,
                    )}
              </span>
            </li>
          ) : (
            <li key={command.id} className="self-end text-xs text-muted">
              {command.kind === 'answer'
                ? t(command.text === 'yes' ? 'workspace.yes' : 'workspace.no')
                : command.kind === 'close' || command.kind === 'archive' || command.kind === 'stop'
                  ? t(`workspace.${command.kind}`)
                  : command.kind === 'open'
                    ? t('workspace.openChat')
                    : command.kind === 'rename'
                      ? `${t('tree.rename')}: ${command.text}`
                      : command.kind === 'model'
                        ? `${t('workspace.model')}: ${models.find((model) => model.value === command.text)?.name ?? command.text}`
                        : command.text}{' '}
              <span className={PROGRESS[command.state].look}>
                {command.state === 'failed' && command.error
                  ? codeText(command.error, t)
                  : t(PROGRESS[command.state].label)}
              </span>
            </li>
          ),
        )}
      </ol>
      {chat.state === 'waiting' && (
        <div className="flex flex-wrap items-center gap-2 rounded border border-line p-2">
          {chat.waitingFor && <span className="min-w-0 flex-1 text-sm">{chat.waitingFor}</span>}
          <Answers session={chat.id} />
        </div>
      )}
      <form
        className="flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          say(text, pictures.given());
        }}
      >
        <textarea
          aria-label={t('workspace.say')}
          placeholder={t('workspace.say')}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (sends(event)) {
              event.preventDefault();
              say(text, pictures.given());
            }
          }}
          {...picturing(pictures)}
          rows={3}
          className={`${field} w-full`}
        />
        <Pictures pictures={pictures} />
        <div className="flex flex-wrap items-center gap-2">
          <DictateButton
            onText={(words) => setText((now) => (now.trim() ? `${now.trimEnd()} ${words}` : words))}
          />
          <PictureButton pictures={pictures} />
          {QUICK.map((quick) => (
            <button
              key={quick.text}
              type="button"
              disabled={sent.isPending}
              onClick={() => say(quick.text)}
              className={button}
            >
              {t(quick.label)}
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <ModelChoice chat={chat} models={models} />
            {AT_WORK.has(chat.state) && (
              <button
                type="button"
                disabled={!chat.hosted || sent.isPending}
                onClick={() => sent.mutate({ kind: 'stop', session: chat.id })}
                className={button}
              >
                <Square size={16} aria-hidden />
                {t('workspace.stop')}
              </button>
            )}
            <button
              type="submit"
              disabled={sent.isPending || !text.trim() || !pictures.ready}
              className={primaryButton}
            >
              <Send size={16} aria-hidden />
              {t('workspace.send')}
            </button>
          </div>
        </div>
        {sent.isError && <p className="text-sm text-danger">{errorMessage(sent.error, t)}</p>}
      </form>
    </div>
  );
}

/** The model the chat runs on, which a click changes for its next answer. */
function ModelChoice({ chat, models }: { chat: Known; models: Model[] }) {
  const { t } = useI18n();
  const command = useCommand();
  const current = models.find((model) => model.resolved === chat.model);
  const name = current?.name ?? chat.model;
  if (!name && !models.length) return null;
  return (
    <Menu
      trigger={
        <button
          type="button"
          disabled={!models.length || command.isPending}
          aria-label={`${t('workspace.model')}: ${name ?? '–'}`}
          className={small}
        >
          {name ?? '–'}
          <ChevronDown size={12} aria-hidden />
        </button>
      }
    >
      <MenuChoices
        value={current?.value ?? ''}
        choices={models.map((model) => ({ value: model.value, label: model.name }))}
        onChange={(value) => command.mutate({ kind: 'model', session: chat.id, text: value })}
      />
    </Menu>
  );
}

/** The chats that wait on their owner, answered here; nothing while none waits. */
function Waiting({ known, onChoose }: { known: Map<string, Known>; onChoose: Choose }) {
  const { t } = useI18n();
  const waiting = [...known.values()].filter((chat) => chat.state === 'waiting');
  if (!waiting.length) return null;
  return (
    <section aria-label={t('workspace.waitingForYou')}>
      <h2 className="text-base font-semibold text-danger">{t('workspace.waitingForYou')}</h2>
      <ul className="mt-1 flex flex-col gap-2">
        {waiting.map((chat) => (
          <li key={chat.id} className="rounded border border-line p-2">
            <button
              type="button"
              onClick={() => onChoose(chat.id)}
              className="block w-full min-w-0 truncate text-left text-sm font-medium hover:text-accent"
            >
              {chat.title}
              <span className="ml-2 text-xs font-normal text-muted">
                {titled(chat.project) ?? t('workspace.general')}
              </span>
            </button>
            {chat.waitingFor && <p className="mt-1 text-sm">{chat.waitingFor}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Answers session={chat.id} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Every chat the page lists, a round's members first, each with its project and round. */
function knownOf(projects: Project[]): Map<string, Known> {
  const known = new Map<string, Known>();
  for (const project of projects) {
    for (const round of project.rounds) {
      for (const member of [round.coordinator, ...round.chats]) {
        if (!member.id || known.has(member.id)) continue;
        known.set(member.id, {
          id: member.id,
          title: member.title,
          project,
          state: member.state,
          hosted: member.hosted,
          waitingFor: member.waitingFor,
          model: member.model ?? null,
        });
      }
    }
    for (const chat of project.chats) {
      if (known.has(chat.id)) continue;
      known.set(chat.id, {
        id: chat.id,
        title: chat.title,
        project,
        state: chat.state,
        hosted: chat.hosted,
        waitingFor: chat.waitingFor,
        model: chat.model,
      });
    }
  }
  return known;
}

/** The projects their owner put under Others, folded at the bottom of the list. */
function Others({
  projects,
  chosen,
  onChoose,
  onTerminal,
  starting,
  onStart,
}: {
  projects: Project[];
  chosen: string | null;
  onChoose: Choose;
  onTerminal: (folder: string, name: string) => void;
  starting: Starting | null;
  onStart: (starting: Starting) => void;
}) {
  const { t, formatNumber } = useI18n();
  const [open, setOpen] = useState(false);
  if (!projects.length) return null;
  return (
    <section aria-label={t('workspace.others')} className="flex flex-col gap-6">
      <h2 className="text-sm font-semibold text-muted">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1 rounded hover:text-accent"
        >
          {t('workspace.others')}
          <span className="text-xs font-normal">{formatNumber(projects.length)}</span>
        </button>
      </h2>
      {open &&
        projects.map((project) => (
          <ProjectSection
            key={project.path}
            project={project}
            chosen={chosen}
            onChoose={onChoose}
            onTerminal={onTerminal}
            starting={starting}
            onStart={onStart}
          />
        ))}
    </section>
  );
}

/** The coordinator of the latest round, the chat the page shows until the owner picks another. */
function latest(projects: Project[]): string | null {
  const rounds = projects
    .flatMap((project) => project.rounds)
    .filter((round) => round.coordinator.id)
    .sort((one, other) => (other.created ?? '').localeCompare(one.created ?? ''));
  return rounds[0]?.coordinator.id ?? null;
}

type Tab = 'overview' | 'chat' | 'memory' | 'terminal';

type View = Tab | 'start';

/** A new chat or round asked for in a project's line, written in the page's place. */
interface Starting {
  folder: string;
  name: string;
  round: boolean;
}

const VIEWS: Record<Tab, MessageKey> = {
  overview: 'workspace.view.overview',
  chat: 'workspace.view.chat',
  terminal: 'workspace.view.terminal',
  memory: 'workspace.view.memory',
};

const TerminalPanel = lazily(() => import('./Terminal'), 'TerminalPanel');

/** Opens a chat in the editor by its session, for the menu of every chat's line. */
const Opening = createContext<((session: string) => void) | null>(null);

function Pult({
  projects,
  restart,
  usage,
  models,
  host,
  beside = false,
}: {
  projects: Project[];
  restart: Restart | null;
  usage: Usage | null;
  models: Model[];
  host: Host | null;
  beside?: boolean;
}) {
  const { t, formatNumber } = useI18n();
  useThemeOf('projects');
  const wide = useWide();
  const [folders, setFolders, foldersStyle] = useWidth(FOLDERS);
  const queryClient = useQueryClient();
  const measured = useMutation({
    mutationFn: () => read(true),
    onSuccess: (data) => queryClient.setQueryData(['workspace', 'projects'], data),
  });
  const moving = useMutation({ mutationFn: toNextScreen });
  const reread = useMutation({
    mutationFn: () => read(),
    onSuccess: (data) => queryClient.setQueryData(['workspace', 'projects'], data),
  });
  const arrived = useLocation().state as { blocked?: boolean } | null;
  const [blocked, setBlocked] = useState(Boolean(arrived?.blocked));
  const workspace = useOpenWorkspace();
  const released = useCommand();
  const names = useMemo(
    () =>
      new Map(
        projects.flatMap((project) => {
          const name = titled(project);
          return name === null ? [] : [[project.path, name] as const];
        }),
      ),
    [projects],
  );
  const commands = useCommands();
  const [asked] = useSearchParams();
  const [view, setView] = useState<View>(asked.get('view') === 'memory' ? 'memory' : 'overview');
  const askedView = asked.get('view');
  useEffect(() => {
    if (askedView === 'memory') setView('memory');
  }, [askedView]);
  const [picked, setPicked] = useState<string | null>(null);
  const [terminal, setTerminal] = useState<{ folder: string; name: string } | null>(null);
  const [starting, setStarting] = useState<Starting | null>(null);
  // Wide, the list stands beside the page, which shows the chat in its place.
  const shown = wide && view === 'overview' ? 'chat' : view;
  const known = knownOf(projects);
  const chosen = known.get(picked ?? latest(projects) ?? '') ?? null;
  const waiting = [...known.values()].filter((chat) => chat.state === 'waiting').length;
  const listed = commands.data?.commands ?? [];
  const proposals = useMemoryWaiting();
  const choose = (session: string) => {
    setPicked(session);
    setView('chat');
  };
  const openTerminal = (folder: string, name: string) => {
    setTerminal({ folder, name });
    setView('terminal');
  };
  const start = (asked: Starting) => {
    setStarting(asked);
    setView('start');
  };
  const closeStart = () => {
    setStarting(null);
    setView(wide ? 'chat' : 'overview');
  };
  const begun = shown === 'start' ? starting : null;
  const closeTerminal = () => {
    setTerminal(null);
    setView(wide ? 'chat' : 'overview');
  };
  // The workspace lets the chat's process go first, as a session never runs in two.
  const open = (chat: Known) =>
    released.mutate(
      { kind: 'open', session: chat.id },
      {
        onSuccess: (command) => {
          if (command.state !== 'failed')
            workspace.open({
              query: queryOf(chat.project.path, chat.id),
              name: tabOf(chat.project),
            });
        },
      },
    );
  const opening = (session: string) => {
    const chat = known.get(session);
    if (chat) open(chat);
  };
  const list = (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-col gap-4">
        <Machine host={host} onMeasure={() => reread.mutate()} measuring={reread.isPending} />
        <Limits usage={usage} onMeasure={() => measured.mutate()} measuring={measured.isPending} />
      </div>
      <Waiting known={known} onChoose={choose} />
      {projects
        .filter((project) => !project.aside)
        .map((project) => (
          <ProjectSection
            key={project.path}
            project={project}
            chosen={chosen?.id ?? null}
            onChoose={choose}
            onTerminal={openTerminal}
            starting={begun}
            onStart={start}
          />
        ))}
      <Others
        projects={projects.filter((project) => project.aside)}
        chosen={chosen?.id ?? null}
        onChoose={choose}
        onTerminal={openTerminal}
        starting={begun}
        onStart={start}
      />
    </div>
  );
  const page = (
    <div className={`flex flex-col ${wide ? 'h-full' : ''}`}>
      <div role="group" aria-label={t('rail.projects')} className="mb-4 flex gap-2">
        {(Object.keys(VIEWS) as Tab[])
          .filter((each) => (!wide || each !== 'overview') && (terminal || each !== 'terminal'))
          .map((each) => (
            <button
              key={each}
              type="button"
              aria-pressed={shown === each}
              onClick={() => setView(each)}
              className={`${button} ${shown === each ? 'bg-selected' : ''} ${each === 'memory' ? 'ml-auto' : ''}`}
            >
              {t(VIEWS[each])}
              {each === 'overview' && waiting > 0 && (
                <span className="text-danger tabular-nums">{formatNumber(waiting)}</span>
              )}
              {each === 'memory' && proposals > 0 && (
                <span className="text-danger tabular-nums">{formatNumber(proposals)}</span>
              )}
            </button>
          ))}
      </div>
      {(released.isError || commands.isError || measured.isError) && (
        <p className="mb-2 text-sm text-danger">
          {errorMessage((released.error ?? commands.error ?? measured.error) as Error, t)}
        </p>
      )}
      {blocked && (
        <p role="alert" className="mb-2 text-sm text-danger">
          {t('workspace.beside.blocked')}
        </p>
      )}
      {released.data?.state === 'failed' && released.data.error && (
        <p className="mb-2 text-sm text-danger">{codeText(released.data.error, t)}</p>
      )}
      {terminal && (
        <div className={shown === 'terminal' ? 'flex min-h-0 min-w-0 flex-1 flex-col' : 'hidden'}>
          <Suspense fallback={<Loading />}>
            <TerminalPanel
              key={terminal.folder}
              folder={terminal.folder}
              name={terminal.name}
              onClose={closeTerminal}
            />
          </Suspense>
        </div>
      )}
      {shown === 'terminal' ? null : shown === 'memory' ? (
        <Memory names={names} />
      ) : begun ? (
        <NewChat
          key={`${begun.folder} ${begun.round}`}
          folder={begun.folder}
          name={begun.name}
          round={begun.round}
          onStarted={(session) => {
            setStarting(null);
            choose(session);
          }}
          onClose={closeStart}
        />
      ) : shown === 'chat' ? (
        <section
          aria-label={t('workspace.view.chat')}
          className="flex min-h-0 min-w-0 flex-1 flex-col"
        >
          <Conversation chat={chosen} commands={listed} models={models} onOpen={open} />
        </section>
      ) : (
        list
      )}
    </div>
  );
  return (
    <Opening value={opening}>
      {beside ? (
        <div className="flex h-dvh flex-col bg-surface text-ink">
          <header className="flex items-center gap-2 border-b border-line px-4 py-2">
            <h1 className="flex-1 truncate text-base font-semibold">{t('rail.projects')}</h1>
            {hasScreens() && (
              <button
                type="button"
                onClick={() => moving.mutate()}
                title={t('meeting.nextScreen')}
                className={button}
              >
                <Monitor size={16} aria-hidden />
                <span className="sr-only sm:not-sr-only">{t('meeting.nextScreen')}</span>
              </button>
            )}
            {restart && <RestartButton restart={restart} />}
          </header>
          {moving.error && (
            <p role="alert" className="bg-panel px-4 py-1 text-sm text-danger">
              {errorMessage(moving.error, t)}
            </p>
          )}
          <div className="flex min-h-0 flex-1 p-4">
            {wide && (
              <>
                <aside
                  style={foldersStyle}
                  className="w-(--folders) max-w-[30%] shrink-0 overflow-y-auto"
                >
                  {list}
                </aside>
                <Splitter
                  column={FOLDERS}
                  width={folders}
                  onWidth={setFolders}
                  className={`mx-1 flex ${SIDE_SEPARATOR}`}
                />
              </>
            )}
            <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto">{page}</main>
          </div>
        </div>
      ) : (
        <Frame
          title={t('rail.projects')}
          folders={false}
          actions={
            <>
              {restart && <RestartButton restart={restart} />}
              {matchMedia('(pointer: fine)').matches && (
                <button
                  type="button"
                  aria-label={t('workspace.beside')}
                  title={t('workspace.beside')}
                  onClick={() => setBlocked(!setAside())}
                  className={iconButton}
                >
                  <PictureInPicture2 size={16} aria-hidden />
                </button>
              )}
            </>
          }
          side={wide ? list : undefined}
        >
          {page}
        </Frame>
      )}
    </Opening>
  );
}

/** Why the workspace cannot be restarted now: chats at work, checks or releases running in it. */
function busyWith(restart: Restart, t: (key: MessageKey) => string): string[] {
  return [
    ...restart.working.map(
      (session) =>
        `${t(STATES[session.state].label)}: ${session.title ?? session.name ?? session.id}`,
    ),
    ...restart.scripts.map(
      (script) =>
        `${t(script.script === 'release' ? 'workspace.release' : 'workspace.check')}${
          script.project ? ` (${script.project})` : ''
        }`,
    ),
  ];
}

function RestartButton({ restart }: { restart: Restart }) {
  const { t, formatNumber } = useI18n();
  const [asking, setAsking] = useState(false);
  const restarted = useCommand();
  const busy = busyWith(restart, t);
  const failed = restarted.data?.state === 'failed' ? restarted.data.error : null;
  const going = restarted.isSuccess && !failed;
  return (
    <>
      <button
        type="button"
        disabled={busy.length > 0 || restarted.isPending || going}
        title={busy.length ? busy.join('\n') : undefined}
        onClick={() => setAsking(true)}
        className={button}
      >
        <RotateCw size={16} aria-hidden />
        {t(going ? 'workspace.restarting' : 'workspace.restart')}
      </button>
      {restarted.isError && (
        <span className="text-sm text-danger">{errorMessage(restarted.error, t)}</span>
      )}
      {failed && <span className="text-sm text-danger">{codeText(failed, t)}</span>}
      {asking && (
        <ConfirmDialog
          heading={t('workspace.restartTitle')}
          confirmLabel={t('workspace.restart')}
          onConfirm={() => restarted.mutate({ kind: 'restart' })}
          onClose={() => setAsking(false)}
        >
          {t('workspace.restartBody').replace('{count}', formatNumber(restart.sessions))}
        </ConfirmDialog>
      )}
    </>
  );
}

/** The workspace's answer with what an older workspace image leaves out made empty. */
function listed(given: Listed): Listed {
  return {
    restart: given.restart ?? null,
    usage: given.usage ?? null,
    models: given.models ?? [],
    host: given.host ?? null,
    projects: given.projects.map((project) => ({
      ...project,
      gate: project.gate ?? null,
      plan: project.plan ?? null,
      rounds: (project.rounds ?? []).map((round) => ({ ...round, auto: round.auto ?? true })),
      chats: (project.chats ?? []).map((chat) => ({
        ...chat,
        state: chat.state ?? (chat.open ? 'idle' : 'closed'),
        waitingFor: chat.waitingFor ?? null,
        context: chat.context ?? null,
        model: chat.model ?? null,
        changes: chat.changes ?? null,
      })),
    })),
  };
}

/** The projects as the workspace lists them; measured, after it measures the plan's limits. */
function read(measured = false): Promise<Listed> {
  return getJson<Listed>(`/api/workspace/projects${measured ? '?measured' : ''}`).then(listed);
}

function useProjects() {
  return useQuery({
    queryKey: PROJECTS,
    queryFn: () => read(),
    retry: false,
    refetchOnWindowFocus: 'always',
    staleTime: 0,
  });
}

/** The Projects page alone in a window beside the app, without the app's shell. */
export function WorkspaceBeside() {
  useFollowed();
  useTitle(useI18n().t('rail.projects'));
  const query = useProjects();
  if (query.isPending) return <Loading />;
  if (query.isError) return <Failure error={query.error} />;
  return <Pult {...query.data} beside />;
}

export function WorkspacePage() {
  const query = useProjects();
  return <Loaded query={query}>{(listed) => <Pult {...listed} />}</Loaded>;
}
