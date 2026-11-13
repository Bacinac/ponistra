import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pencil, RotateCcw, Trash2 } from 'lucide-react';
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type MouseEvent,
} from 'react';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { useSession, type User } from './auth';
import { ConfirmDialog } from './dialogs';
import { Loading, Panel } from './frame';
import { useI18n } from './i18n';
import { ActionsMenu, MenuItem, MenuSeparator } from './menu';
import { button, field, primaryButton } from './styles';
import { covers, errorMessage, type Role, type TreeNode } from './tree';

/** A stretch of a tab's text: the JSON of the Yjs relative positions of its first character
 * and of its end, after its last one. */
export interface Anchor {
  from: object;
  to: object;
}

/** Left, bottom, right and top in the page's own coordinates, as the file draws it. */
export type PageRect = [number, number, number, number];

/** The text chosen on a file's page, or a point there. */
export type PageAnchor =
  { page: number; rects: PageRect[] } | { page: number; at: [number, number] };

export interface ThreadComment {
  id: string;
  author: User | null;
  outside_author: string;
  body: string;
  created_at: string;
  edited_at: string | null;
}

export interface Thread {
  id: string;
  tab: string | null;
  anchor: Anchor | PageAnchor;
  quote: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: User | null;
  comments: ThreadComment[];
}

/** A thread being written, on the text selected when it was started. */
export interface Draft {
  tab: string | null;
  anchor: Anchor | PageAnchor;
  quote: string;
}

export function threadsKey(document: string) {
  return ['threads', document] as const;
}

export function useThreads(document: string) {
  return useQuery({
    queryKey: threadsKey(document),
    queryFn: () => getJson<{ threads: Thread[] }>(`/api/nodes/${document}/threads`),
    select: (data) => data.threads,
  });
}

/** The tab's threads as its text has them. */
export interface InText {
  order: readonly string[];
  lost: readonly string[];
}

/** What a document's page and its editor share about comments. */
export interface Desk {
  /** The thread the text and the panel point at, from the address. */
  active: string | null;
  /** Counts each time a thread is asked to be shown, so asking again shows it again. */
  shown: number;
  draft: Draft | null;
  /** Known once the tab's text is in. */
  inText: InText | null;
  start: (draft: Draft) => void;
  show: (thread: string | null) => void;
  drop: () => void;
  place: (inText: InText | null) => void;
}

export const DeskContext = createContext<Desk | null>(null);

export function useDesk(): Desk | null {
  return useContext(DeskContext);
}

export function useDeskState(
  active: string | null,
  open: (thread: string | null, replace: boolean) => void,
): Desk {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [inText, setInText] = useState<InText | null>(null);
  const [shown, setShown] = useState(0);
  return {
    active,
    shown,
    draft,
    inText,
    start: (next) => {
      setDraft(next);
      open(null, false);
    },
    show: (thread) => {
      setShown((count) => count + 1);
      open(thread, true);
    },
    drop: () => setDraft(null),
    place: setInText,
  };
}

/** What a thread is about as its card names it: the text it quotes, or the page of its point. */
function useAbout(): (about: Pick<Draft, 'anchor' | 'quote'>) => string {
  const { t, formatNumber } = useI18n();
  return ({ anchor, quote }) =>
    quote || ('page' in anchor ? `${t('pdf.page')} ${formatNumber(anchor.page)}` : '');
}

function Composer({
  label,
  placeholder,
  initial = '',
  focused = false,
  pending,
  onSubmit,
  onCancel,
}: {
  label: string;
  placeholder: string;
  initial?: string;
  focused?: boolean;
  pending: boolean;
  onSubmit: (text: string) => void;
  onCancel?: () => void;
}) {
  const { t } = useI18n();
  const [text, setText] = useState(initial);
  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (text.trim() && !pending) onSubmit(text);
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <textarea
        autoFocus={focused}
        value={text}
        rows={3}
        placeholder={placeholder}
        aria-label={placeholder}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) submit();
          else if (event.key === 'Escape' && onCancel) {
            event.preventDefault();
            onCancel();
          }
        }}
        className={`${field} resize-y text-sm`}
      />
      <div className="flex justify-end gap-2">
        {onCancel && (
          <button type="button" onClick={onCancel} className={button}>
            {t('tree.cancel')}
          </button>
        )}
        <button type="submit" disabled={!text.trim() || pending} className={primaryButton}>
          {label}
        </button>
      </div>
    </form>
  );
}

function ThreadCard({
  thread,
  active,
  shown,
  lost,
  writable,
  me,
  onShow,
  onLeave,
  onChange,
  pending,
}: {
  thread: Thread;
  active: boolean;
  shown: number;
  lost: boolean;
  writable: boolean;
  me: number | undefined;
  onShow: () => void;
  onLeave: () => void;
  onChange: (request: () => Promise<unknown>) => void;
  pending: boolean;
}) {
  const { t, formatDate } = useI18n();
  const about = useAbout()(thread);
  const [editing, setEditing] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<ThreadComment | null>(null);
  const card = useRef<HTMLElement>(null);
  const resolved = thread.resolved_at !== null;
  const resolve = (resolved: boolean) =>
    onChange(() => patchJson(`/api/threads/${thread.id}`, { resolved }));

  useEffect(() => {
    if (active) card.current?.scrollIntoView({ block: 'nearest' });
  }, [active, shown]);

  const activate = (event: MouseEvent) => {
    if (!active && !(event.target as Element).closest('button, a, textarea, [role="menu"]'))
      onShow();
  };

  return (
    <article
      ref={card}
      aria-label={about}
      aria-current={active || undefined}
      onClick={activate}
      className={`flex flex-col gap-2 rounded-lg border p-2 ${active ? 'border-focus bg-raised' : 'border-line'}`}
    >
      <button
        type="button"
        onClick={onShow}
        className="line-clamp-3 border-l-2 border-comment-active pl-2 text-left text-sm text-muted hover:text-ink"
      >
        {about}
      </button>
      {lost && <p className="text-xs text-muted">{t('comment.lost')}</p>}
      <ol className="flex flex-col gap-2">
        {thread.comments.map((comment) => (
          <li key={comment.id} className="flex flex-col gap-0.5">
            <div className="flex items-center gap-1">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">
                  {comment.author?.name ?? (comment.outside_author || t('comment.formerUser'))}
                </p>
                <p className="text-xs text-muted">
                  {formatDate(comment.created_at)}
                  {comment.outside_author && ` · ${t('comment.imported')}`}
                  {comment.edited_at && ` · ${t('comment.edited')}`}
                </p>
              </div>
              {comment.author?.id === me && (
                <ActionsMenu>
                  <MenuItem
                    icon={Pencil}
                    label={t('comment.edit')}
                    onSelect={() => setEditing(comment.id)}
                  />
                  <MenuSeparator />
                  <MenuItem
                    icon={Trash2}
                    label={t('comment.delete')}
                    onSelect={() => setDeleting(comment)}
                  />
                </ActionsMenu>
              )}
            </div>
            {editing === comment.id ? (
              <Composer
                label={t('tree.save')}
                placeholder={t('comment.placeholder')}
                initial={comment.body}
                focused
                pending={pending}
                onSubmit={(body) => {
                  onChange(() => patchJson(`/api/comments/${comment.id}`, { body }));
                  setEditing(null);
                }}
                onCancel={() => setEditing(null)}
              />
            ) : (
              <p className="text-sm break-words whitespace-pre-wrap">{comment.body}</p>
            )}
          </li>
        ))}
      </ol>
      {resolved ? (
        <div className="flex items-center gap-2">
          <p className="min-w-0 flex-1 text-xs text-muted">
            {t('comment.resolved')} · {thread.resolved_by?.name ?? t('comment.formerUser')} ·{' '}
            {formatDate(thread.resolved_at!)}
          </p>
          <button
            type="button"
            disabled={!writable}
            onClick={() => resolve(false)}
            className={button}
          >
            <RotateCcw size={14} aria-hidden />
            {t('comment.reopen')}
          </button>
        </div>
      ) : (
        <>
          {active && (
            <Composer
              key={thread.comments.length}
              label={t('comment.reply')}
              placeholder={t('comment.replyPlaceholder')}
              pending={pending}
              onSubmit={(body) =>
                onChange(() => postJson(`/api/threads/${thread.id}/comments`, { body }))
              }
            />
          )}
          <div className="flex justify-end">
            <button
              type="button"
              disabled={!writable}
              onClick={() => {
                resolve(true);
                if (active) onLeave();
              }}
              className={button}
            >
              <Check size={14} aria-hidden />
              {t('comment.resolve')}
            </button>
          </div>
        </>
      )}
      {deleting && (
        <ConfirmDialog
          heading={t('comment.deleteTitle')}
          confirmLabel={t('comment.delete')}
          onConfirm={() => onChange(() => deleteJson(`/api/comments/${deleting.id}`))}
          onClose={() => setDeleting(null)}
        >
          {t('comment.deleteWarning')}
        </ConfirmDialog>
      )}
    </article>
  );
}

function inTextOrder(threads: Thread[], inText: InText | null): Thread[] {
  const at = (thread: Thread) => {
    const index = inText?.order.indexOf(thread.id) ?? -1;
    return index < 0 ? Infinity : index;
  };
  return threads.toSorted((a, b) => at(a) - at(b) || a.created_at.localeCompare(b.created_at));
}

export function CommentsPanel({
  document,
  tab,
  role,
  onClose,
}: {
  document: TreeNode;
  tab: string | null;
  role: Role;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const about = useAbout();
  const queryClient = useQueryClient();
  const desk = useDesk()!;
  const me = useSession().data?.user?.id;
  const threads = useThreads(document.id);
  const [resolvedShown, setResolvedShown] = useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: threadsKey(document.id) });
  const change = useMutation({
    mutationFn: (request: () => Promise<unknown>) => request(),
    onSettled: refresh,
  });
  const create = useMutation({
    mutationFn: ({ draft, body }: { draft: Draft; body: string }) =>
      postJson<Thread>(`/api/nodes/${document.id}/threads`, { ...draft, body }),
    onSuccess: (thread) => {
      desk.drop();
      desk.show(thread.id);
    },
    onSettled: refresh,
  });
  const writable = covers(role, 'edit');
  const draft = desk.draft?.tab === tab ? desk.draft : null;
  const here = threads.data?.filter((thread) => thread.tab === tab) ?? [];
  const open = inTextOrder(
    here.filter((thread) => !thread.resolved_at),
    desk.inText,
  );
  const resolved = here
    .filter((thread) => thread.resolved_at)
    .toSorted((a, b) => b.resolved_at!.localeCompare(a.resolved_at!));
  const failure = change.error ?? create.error;
  const activeResolved = resolved.some((thread) => thread.id === desk.active);

  useEffect(() => {
    if (activeResolved) setResolvedShown(true);
  }, [activeResolved]);

  const card = (thread: Thread) => (
    <ThreadCard
      key={thread.id}
      thread={thread}
      active={thread.id === desk.active}
      shown={desk.shown}
      lost={!thread.resolved_at && Boolean(desk.inText?.lost.includes(thread.id))}
      writable={writable}
      me={me}
      onShow={() => desk.show(thread.id)}
      onLeave={() => desk.show(null)}
      onChange={change.mutate}
      pending={change.isPending}
    />
  );

  return (
    <Panel title={t('comment.list')} onClose={onClose}>
      {draft && (
        <section
          aria-label={t('comment.new')}
          className="flex flex-col gap-2 rounded-lg border border-focus bg-raised p-2"
        >
          <p className="line-clamp-3 border-l-2 border-comment-active pl-2 text-sm text-muted">
            {about(draft)}
          </p>
          <Composer
            key={JSON.stringify(draft.anchor)}
            label={t('command.comment')}
            placeholder={t('comment.placeholder')}
            focused
            pending={create.isPending}
            onSubmit={(body) => create.mutate({ draft, body })}
            onCancel={desk.drop}
          />
        </section>
      )}
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {threads.isPending ? (
        <Loading />
      ) : threads.isError ? (
        <p className="text-sm text-danger">{errorMessage(threads.error, t)}</p>
      ) : (
        <>
          {open.length === 0 && !draft && (
            <p className="text-sm text-muted">{t('comment.empty')}</p>
          )}
          {open.map(card)}
          {resolved.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-muted">
              <input
                type="checkbox"
                checked={resolvedShown}
                onChange={(event) => setResolvedShown(event.target.checked)}
              />
              {t('comment.showResolved')} ({formatNumber(resolved.length)})
            </label>
          )}
          {resolvedShown && resolved.map(card)}
        </>
      )}
    </Panel>
  );
}
