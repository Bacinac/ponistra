import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Check,
  Ellipsis,
  Hash,
  Lock,
  LogOut,
  MessagesSquare,
  Pencil,
  SendHorizontal,
  SmilePlus,
  Trash2,
  Undo2,
  UserPlus,
  Video,
  X,
} from 'lucide-react';
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router';
import { deleteJson, getJson, patchJson, postJson, putJson } from './api';
import { AwayNote } from './away';
import {
  AttachButton,
  AttachedChips,
  CarriedFiles,
  dropTarget,
  FileView,
  takeHanded,
  useAttachments,
  type Attachments,
  type Carried,
} from './chatFiles';
import { Cancel, ConfirmDialog, Labelled, Modal, NameDialog } from './dialogs';
import { Loading, PrimaryAction, useWide } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { useLive, waitingIn, type Summary } from './live';
import { MeetingLink, type Meeting } from './meeting';
import { useMeetingWindow, type MeetingWindow } from './meetingWindow';
import { ActionsMenu, ContextMenuArea, Menu, MenuItem, MenuSeparator } from './menu';
import { useMenuPress } from './press';
import { EmojiDialog, ReactionItems, Reactions, type Reaction } from './reactions';
import { Recipients } from './recipients';
import { button, field, iconButton, primaryButton, sideRow } from './styles';
import { errorMessage, type ListedNode } from './tree';
import type { Person } from './mailData';

interface Message {
  id: number;
  by: string;
  /** Written by a guest in a call of the conversation's meeting. */
  guest: boolean;
  mine: boolean;
  text: string;
  at: string;
  edited: boolean;
  reactions: Reaction[];
  mentions: { id: number; name: string; mine: boolean }[];
  /** Names everyone in the channel. */
  everyone: boolean;
  thread: { replies: number; unread: number };
  /** The meeting this message announces, which has no words of its own. */
  meeting: string | null;
  /** Why it may not be taken back: a legal hold, which keeps it as written, or a rule's term. */
  kept: 'held' | 'retained' | null;
  files: Carried[];
  /** Items of PONISTRA its text links to, as far as the reader may see them. */
  items: ListedNode[];
}

interface Page {
  messages: Message[];
  more: boolean;
  /** How far each of the others has read; only in the conversation's own page. */
  readers?: { name: string; read: number }[];
}

interface Shown {
  id: string;
  kind: Summary['kind'];
  title: string;
  private: boolean;
  people: string[];
  joined: boolean;
  removable: boolean;
  meeting: string | null;
}

interface Mentionable {
  people: { id: number; name: string }[];
  everyone: boolean;
}

interface OpenChannel {
  id: string;
  title: string;
  count: number;
  joined: boolean;
}

// How close to the end of the messages still counts as reading the latest of them.
const AT_END = 48;
// Messages of one person this close together share their name and time.
const TOGETHER = 5 * 60_000;
// Where the colleagues a conversation is started with are found.
const COLLEAGUES = '/api/conversations/people';
const LAST = 'ponistra.conversation';
// How many people the field offers at once after an @.
const OFFERED = 8;
// How a message names everyone in a channel, in any of the interface's languages.
const EVERYONE = /@svi|@all/;
// An address in a message, without the punctuation of the sentence it ends.
const ADDRESS = /(https?:\/\/[^\s<>"]*[^\s<>".,;:!?)\]}'])/;

/** The conversation the user was last in on this browser, which a wide screen opens again. */
export function lastConversation(): string | null {
  try {
    return localStorage.getItem(LAST);
  } catch {
    return null;
  }
}

function keepLast(id: string | null) {
  try {
    if (id) localStorage.setItem(LAST, id);
    else localStorage.removeItem(LAST);
  } catch {
    // Blocked storage only costs opening the last conversation again.
  }
}

/** Where a conversation is read and written, and how far it has moved: as one of its members,
    or as a guest in a call of its meeting (S2-2). */
export interface Talk {
  /** The messages are under `${at}/messages`, the reading under `${at}/read`. */
  at: string;
  changed: string | undefined;
  unread: number;
  /** Where those the user may name are found; a guest names nobody. */
  people?: string;
  /** An open channel read by someone not in it, which the live state does not carry. */
  peek?: boolean;
}

export function useSummary(id: string): Summary | undefined {
  return useLive().conversations.find((each) => each.id === id);
}

export function useMemberTalk(id: string): Talk {
  const summary = useSummary(id);
  return {
    at: `/api/conversations/${id}`,
    people: `/api/conversations/${id}/people`,
    changed: summary?.changed,
    unread: summary?.unread ?? 0,
  };
}

export function useShown(id: string, enabled = true) {
  return useQuery({
    queryKey: ['conversations', id],
    queryFn: () => getJson<Shown | null>(`/api/conversations/${id}`),
    enabled,
  });
}

export function nameOf(summary: Summary, t: (key: MessageKey) => string): string {
  return summary.title || summary.people.join(', ') || t('meeting.untitled');
}

/** A conversation's messages, the latest page first and earlier ones on asking; whenever the
    conversation moves, written to, edited or a message taken back, the latest come in again. */
function useMessages({ at, changed, peek }: Talk, thread?: number) {
  const pages = useInfiniteQuery({
    queryKey: [peek ? 'peek' : 'talk', at, thread],
    queryFn: ({ pageParam }) =>
      getJson<Page>(
        `${at}/messages${thread ? `/${thread}/replies` : ''}${pageParam ? `?before=${pageParam}` : ''}`,
      ),
    initialPageParam: 0,
    getNextPageParam: (page) => (page.more ? page.messages[0].id : undefined),
  });
  const seen = useRef(changed);
  const { refetch, isFetching } = pages;
  useEffect(() => {
    // A conversation that drops out of the list was left: its messages are no longer the user's.
    if (changed !== undefined && changed !== seen.current && !isFetching) {
      seen.current = changed;
      void refetch();
    }
  }, [changed, isFetching, refetch]);
  return pages;
}

type Messaged = ReturnType<typeof useMessages>;

/** Brings up a message a link asked for, reading earlier pages until it is there. */
function useSought(wanted: number | null, pages: Messaged, messages: Message[]) {
  const found = messages.some((each) => each.id === wanted);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = pages;
  useEffect(() => {
    if (wanted && !found && hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [wanted, found, hasNextPage, isFetchingNextPage, fetchNextPage]);
  useEffect(() => {
    if (found) document.getElementById(`message-${wanted}`)?.scrollIntoView({ block: 'center' });
  }, [wanted, found]);
}

/** Tells the server the user has read up to the newest message, while the page is in sight. */
function useRead({ at, unread }: Talk, newest: number | undefined) {
  useEffect(() => {
    if (newest === undefined || unread === 0) return;
    const read = () => {
      if (document.visibilityState === 'visible') void postJson(`${at}/read`, { message: newest });
    };
    read();
    document.addEventListener('visibilitychange', read);
    return () => document.removeEventListener('visibilitychange', read);
  }, [at, newest, unread]);
}

/** A conversation's messages and the field to write to it: on its page, or beside a call. */
export function Conversation({
  talk,
  instead,
  thread,
  onThread,
}: {
  talk: Talk;
  instead?: ReactNode;
  /** The message whose thread stands open, in a channel. */
  thread?: number | null;
  onThread?: (message: number | null) => void;
}) {
  const { t } = useI18n();
  const wide = useWide();
  const pages = useMessages(talk);
  const messages = (pages.data?.pages ?? []).toReversed().flatMap((page) => page.messages);
  useRead(talk, messages.at(-1)?.id);
  const [editing, setEditing] = useState<Message | null>(null);
  const attachments = useAttachments();
  const [params] = useSearchParams();
  const sought = Number(params.get('message')) || null;
  const reply = Number(params.get('reply')) || null;
  useSought(sought, pages, messages);
  const soughtThere = messages.some((each) => each.id === sought);
  useEffect(() => {
    if (reply && soughtThere) onThread?.(sought);
  }, [reply, soughtThere, sought, onThread]);
  const lastOfMine = messages.findLast((each) => each.mine && !each.meeting);
  const readBy = (pages.data?.pages[0]?.readers ?? [])
    .filter((each) => lastOfMine && each.read >= lastOfMine.id)
    .map((each) => each.name);

  const list = useRef<HTMLDivElement>(null);
  const atEnd = useRef(!sought);
  const height = useRef(0);
  const first = messages[0]?.id;
  const earliest = useRef(first);
  useLayoutEffect(() => {
    const shown = list.current;
    if (!shown) return;
    if (atEnd.current) shown.scrollTop = shown.scrollHeight;
    else if (first !== earliest.current) shown.scrollTop += shown.scrollHeight - height.current;
    earliest.current = first;
    height.current = shown.scrollHeight;
  });

  const root = messages.find((each) => each.id === thread);
  return (
    <div className="flex min-h-0 flex-1 gap-3">
      <div
        {...(talk.people && !instead ? dropTarget(attachments) : {})}
        className={`min-h-0 min-w-0 flex-1 flex-col ${root && !wide ? 'hidden' : 'flex'}`}
      >
        <div
          ref={list}
          onScroll={(event) => {
            const shown = event.currentTarget;
            atEnd.current = shown.scrollHeight - shown.scrollTop - shown.clientHeight < AT_END;
          }}
          className="min-h-0 flex-1 overflow-y-auto px-1 py-2"
        >
          {pages.isPending ? (
            <Loading />
          ) : pages.isError ? (
            <p className="text-sm text-danger">{errorMessage(pages.error, t)}</p>
          ) : (
            <>
              {pages.hasNextPage && (
                <button
                  type="button"
                  disabled={pages.isFetchingNextPage}
                  onClick={() => void pages.fetchNextPage()}
                  className={`${button} mx-auto mb-2 flex`}
                >
                  {t('chat.earlier')}
                </button>
              )}
              {messages.length === 0 ? (
                <p className="px-2 text-sm text-muted">{t('chat.empty')}</p>
              ) : (
                <Messages
                  at={talk.at}
                  messages={messages}
                  readOnly={talk.peek}
                  canSave={!!talk.people}
                  sought={sought}
                  seen={lastOfMine && { message: lastOfMine.id, names: readBy }}
                  onThread={onThread}
                  onEdit={setEditing}
                  onChanged={() => void pages.refetch()}
                />
              )}
            </>
          )}
        </div>
        {instead ?? (
          <Composer
            at={talk.at}
            people={talk.people}
            attachments={attachments}
            editing={editing}
            onDone={() => setEditing(null)}
            onSent={() => {
              atEnd.current = true;
              void pages.refetch();
            }}
          />
        )}
      </div>
      {root && (
        <Thread
          talk={talk}
          root={root}
          wide={wide}
          instead={instead}
          sought={reply}
          onClose={() => onThread?.(null)}
        />
      )}
    </div>
  );
}

/** A channel message's thread: the message and its replies, beside the channel or, narrow, in
    its place. */
function Thread({
  talk,
  root,
  wide,
  instead,
  sought,
  onClose,
}: {
  talk: Talk;
  root: Message;
  wide: boolean;
  instead?: ReactNode;
  sought: number | null;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const pages = useMessages(talk, root.id);
  const replies = (pages.data?.pages ?? []).toReversed().flatMap((page) => page.messages);
  useRead(
    { ...talk, at: `${talk.at}/messages/${root.id}`, unread: root.thread.unread },
    replies.at(-1)?.id,
  );
  const [editing, setEditing] = useState<Message | null>(null);
  const attachments = useAttachments();
  useSought(sought, pages, replies);
  const list = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (list.current && !sought) list.current.scrollTop = list.current.scrollHeight;
  }, [replies.length, sought]);
  const refreshed = () => void pages.refetch();
  return (
    <aside
      {...(talk.people && !instead ? dropTarget(attachments) : {})}
      aria-label={t('thread.thread')}
      className={`flex min-h-0 flex-col ${wide ? 'w-96 shrink-0 border-l border-line pl-3' : 'min-w-0 flex-1'}`}
    >
      <div className="flex items-center gap-2">
        <h2 className="flex-1 text-sm font-semibold">{t('thread.thread')}</h2>
        <button
          type="button"
          aria-label={t('frame.close')}
          onClick={onClose}
          className={iconButton}
        >
          <X size={16} aria-hidden />
        </button>
      </div>
      <div ref={list} className="min-h-0 flex-1 overflow-y-auto px-1 py-2">
        <Messages
          at={talk.at}
          messages={[root]}
          readOnly={talk.peek}
          canSave={!!talk.people}
          onEdit={setEditing}
          onChanged={refreshed}
        />
        <div className="my-2 h-px bg-line" />
        {pages.isError ? (
          <p className="text-sm text-danger">{errorMessage(pages.error, t)}</p>
        ) : (
          <Messages
            at={talk.at}
            messages={replies}
            readOnly={talk.peek}
            canSave={!!talk.people}
            sought={sought}
            label={t('thread.replies')}
            onEdit={setEditing}
            onChanged={refreshed}
          />
        )}
      </div>
      {!instead && (
        <Composer
          at={talk.at}
          people={talk.people}
          attachments={attachments}
          parent={root.id}
          editing={editing}
          onDone={() => setEditing(null)}
          onSent={refreshed}
        />
      )}
    </aside>
  );
}

/** A message's text with those it names marked, the reader most of all. */
function Linked({ text }: { text: string }) {
  return text.split(ADDRESS).map((part, index) =>
    index % 2 === 0 ? (
      part
    ) : (
      <a
        key={index}
        href={part}
        target="_blank"
        rel="noopener noreferrer"
        className="break-all text-link hover:underline"
      >
        {part}
      </a>
    ),
  );
}

function Said({ message }: { message: Message }) {
  const named = message.mentions.map((each) => `@${each.name}`);
  if (!named.length && !message.everyone) return <Linked text={message.text} />;
  const escaped = named.map((each) => each.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (message.everyone) escaped.push(EVERYONE.source);
  const parts = message.text.split(new RegExp(`(${escaped.join('|')})`));
  const mine = new Set(message.mentions.filter((each) => each.mine).map((each) => `@${each.name}`));
  return parts.map((part, index) => {
    if (index % 2 === 0) return <Linked key={index} text={part} />;
    const me = mine.has(part) || (message.everyone && EVERYONE.test(part));
    return (
      <mark
        key={index}
        className={`rounded px-0.5 font-semibold ${me ? 'bg-accent text-on-accent' : 'bg-transparent text-accent'}`}
      >
        {part}
      </mark>
    );
  });
}

/** What the author does to their own message: a hold keeps it as written, a rule's term only
    from being taken back. */
function OwnItems({
  message,
  onEdit,
  onTakeBack,
}: {
  message: Message;
  onEdit: (message: Message) => void;
  onTakeBack: (message: Message) => void;
}) {
  const { t } = useI18n();
  const hint = message.kept ? t(`retention.kept.${message.kept}`) : undefined;
  return (
    <>
      {!message.meeting && (
        <MenuItem
          icon={Pencil}
          label={t('chat.edit')}
          disabled={message.kept === 'held'}
          hint={message.kept === 'held' ? hint : undefined}
          onSelect={() => onEdit(message)}
        />
      )}
      <MenuItem
        icon={Undo2}
        label={t('chat.takeBack')}
        disabled={!!message.kept}
        hint={hint}
        onSelect={() => onTakeBack(message)}
      />
    </>
  );
}

function Messages({
  at,
  messages,
  readOnly,
  canSave,
  sought,
  seen,
  label,
  onThread,
  onEdit,
  onChanged,
}: {
  at: string;
  messages: Message[];
  readOnly?: boolean;
  /** Whether a file can be saved among the reader's documents, which a guest has none of. */
  canSave: boolean;
  /** The message a link asked for. */
  sought?: number | null;
  /** Who of the others has read this far. */
  seen?: { message: number; names: string[] };
  label?: string;
  onThread?: (message: number) => void;
  onEdit: (message: Message) => void;
  onChanged: () => void;
}) {
  const { t, formatDay, formatTime, formatNumber } = useI18n();
  const [taking, setTaking] = useState<Message | null>(null);
  const [choosing, setChoosing] = useState<Message | null>(null);
  const [viewing, setViewing] = useState<Carried | null>(null);
  const menuPress = useMenuPress();
  const takeBack = useMutation({
    mutationFn: (message: Message) => deleteJson(`${at}/messages/${message.id}`),
    onSuccess: onChanged,
  });
  const react = useMutation({
    mutationFn: ({ message, emoji, on }: { message: Message; emoji: string; on: boolean }) => {
      const path = `${at}/messages/${message.id}/reactions/${encodeURIComponent(emoji)}`;
      return on ? putJson<void>(path, {}) : deleteJson(path);
    },
    onSuccess: onChanged,
  });
  const give = (message: Message) => (emoji: string) => react.mutate({ message, emoji, on: true });
  const failure = takeBack.error ?? react.error;
  return (
    <ol aria-label={label ?? t('chat.messages')} className="flex flex-col">
      {messages.map((message, at) => {
        const when = new Date(message.at);
        const before = messages[at - 1];
        const day = !before || formatDay(new Date(before.at)) !== formatDay(when);
        const together =
          !day &&
          before.by === message.by &&
          before.mine === message.mine &&
          when.getTime() - new Date(before.at).getTime() < TOGETHER;
        const bubble = (
          <div
            {...menuPress}
            className={`group relative flex max-w-[85%] flex-col rounded-lg px-3 py-1.5 ${together ? 'mt-0.5' : 'mt-2'} ${message.mine ? 'self-end bg-selected' : 'self-start bg-raised'} ${message.id === sought ? 'ring-2 ring-accent' : ''}`}
          >
            {!together && (
              <p className="flex gap-2 text-xs text-muted">
                {!message.mine && (
                  <span className="font-semibold text-ink">
                    {message.by || t('comment.formerUser')}
                    {message.guest && ` (${t('meeting.guest')})`}
                  </span>
                )}
                <time dateTime={message.at}>{formatTime(when)}</time>
              </p>
            )}
            {message.meeting ? (
              <>
                <p className="text-sm">{t('chat.meetingOpened')}</p>
                <MeetingLink
                  path={`/meet/${message.meeting}`}
                  className={`${button} mt-1 self-start`}
                >
                  <Video size={16} aria-hidden />
                  {t('meeting.join')}
                </MeetingLink>
              </>
            ) : (
              (message.text || message.edited) && (
                <p className="text-sm break-words whitespace-pre-wrap">
                  <Said message={message} />
                  {message.edited && (
                    <span className="ml-2 text-xs text-muted">{t('chat.edited')}</span>
                  )}
                </p>
              )
            )}
            <CarriedFiles files={message.files} items={message.items} onOpen={setViewing} />
            {message.reactions.length > 0 && (
              <div className="mt-1">
                <Reactions
                  reactions={message.reactions}
                  onGive={give(message)}
                  onTake={(emoji) => react.mutate({ message, emoji, on: false })}
                  disabled={react.isPending || readOnly}
                />
              </div>
            )}
            {seen?.message === message.id && seen.names.length > 0 && (
              <p className="mt-0.5 self-end text-xs text-muted">
                {t('chat.readBy').replace('{names}', seen.names.join(', '))}
              </p>
            )}
            {onThread && message.thread.replies > 0 && (
              <button
                type="button"
                onClick={() => onThread(message.id)}
                className="mt-1 flex items-center gap-1.5 self-start text-xs font-medium text-accent hover:underline"
              >
                <MessagesSquare size={12} aria-hidden />
                {t('thread.count').replace('{count}', formatNumber(message.thread.replies))}
                {message.thread.unread > 0 && (
                  <span
                    aria-label={t('chat.unread')}
                    className="min-w-4 rounded-full bg-accent px-1 text-center leading-4 text-on-accent tabular-nums"
                  >
                    {formatNumber(message.thread.unread)}
                  </span>
                )}
              </button>
            )}
            {onThread && !readOnly && (
              <button
                type="button"
                aria-label={t('thread.reply')}
                title={t('thread.reply')}
                onClick={() => onThread(message.id)}
                className={`${iconButton} absolute top-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 [@media(pointer:coarse)]:hidden ${message.mine ? '-left-24' : '-right-16'}`}
              >
                <MessagesSquare size={16} aria-hidden />
              </button>
            )}
            {!readOnly && (
              <Menu
                align={message.mine ? 'end' : 'start'}
                trigger={
                  <button
                    type="button"
                    aria-label={t('reactions.react')}
                    title={t('reactions.react')}
                    className={`${iconButton} absolute top-0 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(pointer:coarse)]:hidden ${message.mine ? '-left-16' : '-right-8'}`}
                  >
                    <SmilePlus size={16} aria-hidden />
                  </button>
                }
              >
                <ReactionItems onPick={give(message)} onMore={() => setChoosing(message)} />
              </Menu>
            )}
            {message.mine && !readOnly && (
              <Menu
                align="end"
                trigger={
                  <button
                    type="button"
                    aria-label={t('chat.actions')}
                    className={`${iconButton} absolute top-0 -left-8 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 [@media(pointer:coarse)]:opacity-100`}
                  >
                    <Ellipsis size={16} aria-hidden />
                  </button>
                }
              >
                <OwnItems message={message} onEdit={onEdit} onTakeBack={setTaking} />
              </Menu>
            )}
          </div>
        );
        return (
          <li key={message.id} id={`message-${message.id}`} className="flex flex-col">
            {day && (
              <p className="my-2 text-center text-xs text-muted first-letter:uppercase">
                {formatDay(when)}
              </p>
            )}
            {readOnly ? (
              bubble
            ) : (
              <ContextMenuArea
                items={
                  <>
                    <ReactionItems onPick={give(message)} onMore={() => setChoosing(message)} />
                    {onThread && (
                      <MenuItem
                        icon={MessagesSquare}
                        label={t('thread.reply')}
                        onSelect={() => onThread(message.id)}
                      />
                    )}
                    {message.mine && (
                      <>
                        <MenuSeparator />
                        <OwnItems message={message} onEdit={onEdit} onTakeBack={setTaking} />
                      </>
                    )}
                  </>
                }
              >
                {bubble}
              </ContextMenuArea>
            )}
          </li>
        );
      })}
      {failure && <li className="px-2 text-sm text-danger">{errorMessage(failure, t)}</li>}
      {choosing && <EmojiDialog onPick={give(choosing)} onClose={() => setChoosing(null)} />}
      {viewing && <FileView file={viewing} canSave={canSave} onClose={() => setViewing(null)} />}
      {taking && (
        <ConfirmDialog
          heading={t('chat.takeBack')}
          confirmLabel={t('chat.takeBack')}
          onConfirm={() => {
            takeBack.mutate(taking);
            setTaking(null);
          }}
          onClose={() => setTaking(null)}
        >
          {t(taking.thread.replies > 0 ? 'thread.takeBackSure' : 'chat.takeBackSure')}
        </ConfirmDialog>
      )}
    </ol>
  );
}

/** The @ being typed where the caret stands, and where it starts. */
function typedMention(text: string, caret: number): { start: number; typed: string } | null {
  const found = /(?:^|\s)@([^\s@]*(?: [^\s@]*)?)$/u.exec(text.slice(0, caret));
  if (!found) return null;
  return { start: caret - found[1].length - 1, typed: found[1] };
}

function Composer({
  at,
  people,
  attachments,
  parent,
  editing,
  onDone,
  onSent,
}: {
  at: string;
  people?: string;
  attachments: Attachments;
  /** The message a new one answers, in its thread. */
  parent?: number;
  editing: Message | null;
  onDone: () => void;
  onSent: () => void;
}) {
  const { t } = useI18n();
  const [text, setText] = useState('');
  const box = useRef<HTMLTextAreaElement>(null);
  const picked = useRef(new Map<number, string>());
  const [caret, setCaret] = useState(0);
  const [active, setActive] = useState(0);
  const [dismissed, setDismissed] = useState<number | null>(null);
  useEffect(() => {
    const found = parent ? null : takeHanded(at);
    if (!found) return;
    setText(found.text);
    attachments.addFiles(found.files);
  }, [at]);
  useEffect(() => {
    if (editing) {
      setText(editing.text);
      picked.current = new Map(editing.mentions.map((each) => [each.id, each.name]));
      box.current?.focus();
    }
  }, [editing]);
  const mention = people ? typedMention(text, caret) : null;
  const asking = mention !== null && mention.start !== dismissed;
  const known = useQuery({
    queryKey: ['conversations', people, 'mentionable'],
    queryFn: () => getJson<Mentionable>(people!),
    enabled: asking,
  });
  const wanted = mention?.typed.toLocaleLowerCase() ?? '';
  const everyone = t('channel.everyone');
  const offered = asking
    ? [
        ...(known.data?.everyone && everyone.slice(1).startsWith(wanted)
          ? [{ id: 0, name: everyone.slice(1), label: t('channel.everyoneLabel') }]
          : []),
        ...(known.data?.people ?? [])
          .filter((each) => each.name.toLocaleLowerCase().includes(wanted))
          .map((each) => ({ ...each, label: each.name })),
      ].slice(0, OFFERED)
    : [];
  const choose = (choice: (typeof offered)[number]) => {
    if (!mention) return;
    if (choice.id) picked.current.set(choice.id, choice.name);
    const written = `@${choice.name} `;
    const next = text.slice(0, mention.start) + written + text.slice(caret);
    const after = mention.start + written.length;
    setText(next);
    setCaret(after);
    setActive(0);
    requestAnimationFrame(() => {
      box.current?.focus();
      box.current?.setSelectionRange(after, after);
    });
  };
  const send = useMutation({
    mutationFn: (body: string) => {
      const said = {
        body,
        mentions: [...picked.current]
          .filter(([, name]) => body.includes(`@${name}`))
          .map(([id]) => id),
        everyone: EVERYONE.test(body),
      };
      if (editing) return patchJson(`${at}/messages/${editing.id}`, said);
      return postJson(`${at}/messages`, {
        ...said,
        ...(parent ? { parent } : {}),
        ...(people ? { attachments: attachments.given() } : {}),
      });
    },
    onSuccess: (_, body) => {
      setText((typed) => (typed === body ? '' : typed));
      picked.current = new Map();
      if (editing) onDone();
      else attachments.clear();
      onSent();
    },
  });
  const sendable =
    !send.isPending &&
    (editing
      ? text.trim() || editing.files.length > 0
      : attachments.ready && (text.trim() || attachments.items.length > 0));
  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (sendable) send.mutate(text);
  };
  const cancel = () => {
    setText('');
    onDone();
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-1 border-t border-line pt-2">
      {send.isError && <p className="text-sm text-danger">{errorMessage(send.error, t)}</p>}
      {editing && (
        <p className="flex items-center gap-2 px-1 text-xs text-muted">
          <Pencil size={12} aria-hidden />
          <span className="flex-1">{t('chat.editing')}</span>
          <button type="button" onClick={cancel} className={button}>
            {t('tree.cancel')}
          </button>
        </p>
      )}
      <AttachedChips attachments={attachments} />
      <div className="relative flex items-end gap-2">
        {offered.length > 0 && (
          <div
            role="listbox"
            aria-label={t('channel.mention')}
            onMouseDown={(event) => event.preventDefault()}
            className="absolute right-10 bottom-full left-0 z-50 mb-1 max-h-60 overflow-y-auto rounded border border-line bg-raised p-1 shadow-lg"
          >
            {offered.map((each, index) => (
              <div
                key={each.id}
                role="option"
                aria-selected={index === Math.min(active, offered.length - 1)}
                onClick={() => choose(each)}
                className="cursor-pointer truncate rounded px-2 py-1.5 text-sm hover:bg-hover aria-selected:bg-selected"
              >
                {each.label}
              </div>
            ))}
          </div>
        )}
        {people && !editing && <AttachButton attachments={attachments} />}
        <textarea
          ref={box}
          value={text}
          rows={1}
          placeholder={t('chat.write')}
          aria-label={t('chat.write')}
          onChange={(event) => {
            setText(event.target.value);
            setCaret(event.target.selectionStart);
            setActive(0);
          }}
          onSelect={(event) => setCaret(event.currentTarget.selectionStart)}
          onPaste={(event) => {
            const files = [...event.clipboardData.files];
            // Cells copied from a spreadsheet arrive as words with a picture of them beside.
            if (people && files.length > 0 && !event.clipboardData.getData('text/plain')) {
              event.preventDefault();
              attachments.addFiles(files);
            }
          }}
          onKeyDown={(event) => {
            if (offered.length > 0 && !event.nativeEvent.isComposing) {
              const last = offered.length - 1;
              if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                const step = event.key === 'ArrowDown' ? 1 : -1;
                setActive((was) => (Math.min(was, last) + step + last + 1) % (last + 1));
                return;
              }
              if (event.key === 'Enter' || event.key === 'Tab') {
                event.preventDefault();
                choose(offered[Math.min(active, last)]);
                return;
              }
              if (event.key === 'Escape') {
                event.preventDefault();
                setDismissed(mention?.start ?? null);
                return;
              }
            }
            if (event.key === 'Escape' && editing) {
              event.preventDefault();
              cancel();
            }
            // A phone's Enter starts a new line, as its keyboard has no Shift to hold for one.
            if (
              event.key === 'Enter' &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing &&
              matchMedia('(pointer: fine)').matches
            ) {
              event.preventDefault();
              submit();
            }
          }}
          className={`${field} max-h-40 min-w-0 flex-1 resize-none text-sm field-sizing-content`}
        />
        <button
          type="submit"
          disabled={!sendable}
          aria-label={editing ? t('tree.save') : t('chat.send')}
          title={editing ? t('tree.save') : t('chat.send')}
          className={iconButton}
        >
          <SendHorizontal size={18} aria-hidden />
        </button>
      </div>
    </form>
  );
}

/** Colleagues chosen for a conversation: the ones it starts with, a group under a title where
    one is given, or the ones brought into it. */
function PeopleDialog({
  heading,
  submitLabel,
  titled,
  onSubmit,
  onClose,
}: {
  heading: string;
  submitLabel: string;
  titled?: boolean;
  onSubmit: (people: Person[], title: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [people, setPeople] = useState<Person[]>([]);
  const [title, setTitle] = useState('');
  const save = useMutation({ mutationFn: () => onSubmit(people, title.trim()) });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (people.length > 0) save.mutate();
  };
  return (
    <Modal heading={heading} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('chat.people')}>
          {(id) => (
            <Recipients
              id={id}
              people={people}
              onChange={setPeople}
              source={COLLEAGUES}
              autoFocus
            />
          )}
        </Labelled>
        {titled && (
          <Labelled label={t('chat.groupTitle')}>
            {(id) => (
              <input
                id={id}
                type="text"
                maxLength={200}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className={field}
              />
            )}
          </Labelled>
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="submit"
            disabled={people.length === 0 || save.isPending}
            className={primaryButton}
          >
            {submitLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Starts a conversation with colleagues: with one, the one the two have; with more, a group. */
export function NewConversation() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  return (
    <>
      <PrimaryAction icon={UserPlus} label={t('chat.new')} onClick={() => setOpen(true)} />
      {open && (
        <PeopleDialog
          heading={t('chat.new')}
          submitLabel={t('chat.start')}
          titled
          onSubmit={async (people, title) => {
            const made = await postJson<Shown>('/api/conversations', { people, title });
            setOpen(false);
            await navigate(`/chat/${made.id}`);
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

/** A channel founded by the user, open or private, with colleagues in it if they choose. */
function ChannelDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [closed, setClosed] = useState(false);
  const [people, setPeople] = useState<Person[]>([]);
  const save = useMutation({
    mutationFn: () =>
      postJson<Shown>('/api/channels', { title: title.trim(), private: closed, people }),
    onSuccess: async (made) => {
      onClose();
      await navigate(`/chat/${made.id}`);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (title.trim()) save.mutate();
  };
  return (
    <Modal heading={t('channel.new')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('channel.name')}>
          {(id) => (
            <input
              id={id}
              type="text"
              maxLength={200}
              autoFocus
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={closed}
            onChange={(event) => setClosed(event.target.checked)}
          />
          {t('channel.private')}
        </label>
        <Labelled label={t('channel.people')}>
          {(id) => <Recipients id={id} people={people} onChange={setPeople} source={COLLEAGUES} />}
        </Labelled>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="submit"
            disabled={!title.trim() || save.isPending}
            className={primaryButton}
          >
            {t('channel.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** The installation's open channels, found by name, each opened to read and join. */
function ChannelList({ onNew, onClose }: { onNew: () => void; onClose: () => void }) {
  const { t, formatNumber } = useI18n();
  const [typed, setTyped] = useState('');
  const found = useQuery({
    queryKey: ['channels'],
    queryFn: () => getJson<{ channels: OpenChannel[] }>('/api/channels'),
  });
  const wanted = typed.trim().toLocaleLowerCase();
  const shown = (found.data?.channels ?? []).filter((each) =>
    each.title.toLocaleLowerCase().includes(wanted),
  );
  return (
    <Modal heading={t('channel.channels')} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <div className="flex gap-2">
          <input
            type="search"
            autoFocus
            value={typed}
            aria-label={t('channel.filter')}
            placeholder={t('channel.filter')}
            onChange={(event) => setTyped(event.target.value)}
            className={`${field} min-w-0 flex-1`}
          />
          <button type="button" onClick={onNew} className={primaryButton}>
            {t('channel.new')}
          </button>
        </div>
        {found.isPending ? (
          <Loading />
        ) : found.isError ? (
          <p className="text-sm text-danger">{errorMessage(found.error, t)}</p>
        ) : shown.length === 0 ? (
          <p className="px-2 text-sm text-muted">{t('channel.none')}</p>
        ) : (
          <ul aria-label={t('channel.channels')} className="flex max-h-80 flex-col overflow-y-auto">
            {shown.map((each) => (
              <li key={each.id}>
                <Link
                  to={`/chat/${each.id}`}
                  onClick={onClose}
                  className="flex min-w-0 items-center gap-2 rounded px-2 py-2 text-sm hover:bg-hover"
                >
                  <Hash size={16} aria-hidden className="shrink-0 text-muted" />
                  <span className="min-w-0 flex-1 truncate">{each.title}</span>
                  {each.joined && (
                    <Check size={16} aria-label={t('channel.joined')} className="text-muted" />
                  )}
                  <span className="shrink-0 text-xs text-muted">
                    {t('channel.members').replace('{count}', formatNumber(each.count))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}

/** The row of the side column that opens the channels. */
export function Channels() {
  const { t } = useI18n();
  const [open, setOpen] = useState<'list' | 'new' | null>(null);
  return (
    <>
      <button type="button" onClick={() => setOpen('list')} className={sideRow}>
        <Hash size={16} aria-hidden className="shrink-0 text-muted" />
        {t('channel.channels')}
      </button>
      {open === 'list' && (
        <ChannelList onNew={() => setOpen('new')} onClose={() => setOpen(null)} />
      )}
      {open === 'new' && <ChannelDialog onClose={() => setOpen(null)} />}
    </>
  );
}

/** A conversation on its own page: who is in it, its meeting and its messages, with the group's
    people brought in, its name changed or the user out of it. */
type Asked = 'people' | 'rename' | 'leave' | 'remove';

export function ConversationPage({ id }: { id: string }) {
  const { t, formatNumber } = useI18n();
  const navigate = useNavigate();
  const queries = useQueryClient();
  const [dialog, setDialog] = useState<Asked | null>(null);
  const asked = (useLocation().state as { ask?: Asked } | null)?.ask;
  const [thread, setThread] = useState<number | null>(null);
  const wide = useWide();
  const talk = useMemberTalk(id);
  const shown = useShown(id);
  const refreshed = () => queries.invalidateQueries({ queryKey: ['conversations', id] });
  useEffect(() => keepLast(id), [id]);
  useEffect(() => {
    if (!asked) return;
    setDialog(asked);
    void navigate(`/chat/${id}`, { replace: true, state: null });
  }, [asked, id, navigate]);
  const meetingWindow = useMeetingWindow();
  const online = useSummary(id)?.online ?? [];
  const calling = useMutation({
    mutationFn: (_beside: MeetingWindow) =>
      postJson<Meeting>('/api/meetings', { conversation: id }),
    onSuccess: (made, beside) => beside.go(`/meet/${made.id}`),
    onError: (_error, beside) => beside.close(),
  });
  const joining = useMutation({
    mutationFn: () => postJson(`/api/conversations/${id}/join`, {}),
    onSuccess: refreshed,
  });
  const removing = useMutation({
    mutationFn: () => deleteJson(`/api/conversations/${id}`),
    onSuccess: () => {
      keepLast(null);
      void navigate('/chat');
    },
  });
  const leaving = useMutation({
    mutationFn: () => deleteJson(`/api/conversations/${id}/members`),
    onSuccess: () => {
      keepLast(null);
      void navigate('/chat');
    },
  });
  if (shown.isPending) return <Loading />;
  if (shown.isError) return <p className="text-sm text-danger">{errorMessage(shown.error, t)}</p>;
  if (!shown.data) return <Navigate to="/chat" replace />;
  const { kind, people, meeting, joined, removable } = shown.data;
  const channel = kind === 'channel';
  const problem = calling.error ?? leaving.error ?? joining.error ?? removing.error;
  let opened: ReactNode = null;
  if (dialog === 'people')
    opened = (
      <PeopleDialog
        heading={t('invite.add')}
        submitLabel={t('invite.add')}
        onSubmit={async (chosen) => {
          await postJson(`/api/conversations/${id}/members`, { people: chosen });
          await refreshed();
          setDialog(null);
        }}
        onClose={() => setDialog(null)}
      />
    );
  else if (dialog === 'rename')
    opened = (
      <NameDialog
        heading={t(channel ? 'channel.rename' : 'chat.renameGroup')}
        submitLabel={t('tree.save')}
        initial={shown.data.title}
        onSubmit={(title) => patchJson(`/api/conversations/${id}`, { title })}
        onDone={() => {
          void refreshed();
          setDialog(null);
        }}
        onClose={() => setDialog(null)}
      />
    );
  else if (dialog === 'leave')
    opened = (
      <ConfirmDialog
        heading={t('chat.leave')}
        confirmLabel={t('chat.leave')}
        onConfirm={() => {
          leaving.mutate();
          setDialog(null);
        }}
        onClose={() => setDialog(null)}
      >
        {t(channel && !shown.data.private ? 'channel.leaveSure' : 'chat.leaveSure')}
      </ConfirmDialog>
    );
  else if (dialog === 'remove')
    opened = (
      <ConfirmDialog
        heading={t('channel.remove')}
        confirmLabel={t('channel.remove')}
        onConfirm={() => {
          removing.mutate();
          setDialog(null);
        }}
        onClose={() => setDialog(null)}
      >
        {t('channel.removeSure')}
      </ConfirmDialog>
    );
  return (
    <div
      className={`flex h-full w-full flex-col gap-2 ${thread !== null && wide ? 'max-w-6xl' : 'max-w-3xl'}`}
    >
      <div className="flex items-center gap-2">
        <Link to="/chat" aria-label={t('frame.close')} className={`${iconButton} md:hidden`}>
          <X size={16} aria-hidden />
        </Link>
        <p className="min-w-0 flex-1 truncate text-sm text-muted">
          {channel
            ? t('channel.members').replace('{count}', formatNumber(people.length))
            : kind === 'direct'
              ? online.length > 0 && t('chat.online')
              : [
                  people.join(', '),
                  online.length > 0 &&
                    t('chat.onlineCount').replace('{count}', formatNumber(online.length)),
                ]
                  .filter(Boolean)
                  .join(' · ')}
        </p>
        {channel && !joined ? null : kind === 'meeting' && meeting ? (
          <MeetingLink path={`/meet/${meeting}`} className={`${button} shrink-0`}>
            <Video size={16} aria-hidden />
            {t('meeting.join')}
          </MeetingLink>
        ) : (
          <button
            type="button"
            disabled={calling.isPending}
            onClick={() => calling.mutate(meetingWindow.ready())}
            className={`${button} shrink-0`}
          >
            <Video size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">{t('meeting.now')}</span>
          </button>
        )}
        {kind !== 'direct' && (joined || removable) && (
          <ActionsMenu>
            {joined && (
              <MenuItem
                icon={UserPlus}
                label={t('invite.add')}
                onSelect={() => setDialog('people')}
              />
            )}
            {joined && (kind === 'group' || channel) && (
              <MenuItem
                icon={Pencil}
                label={t('tree.rename')}
                onSelect={() => setDialog('rename')}
              />
            )}
            {joined && (
              <MenuItem icon={LogOut} label={t('chat.leave')} onSelect={() => setDialog('leave')} />
            )}
            {removable && (
              <MenuItem
                icon={Trash2}
                label={t('channel.remove')}
                onSelect={() => setDialog('remove')}
              />
            )}
          </ActionsMenu>
        )}
      </div>
      {problem && <p className="text-sm text-danger">{errorMessage(problem, t)}</p>}
      <AwayNote conversation={id} />
      <Conversation
        talk={joined ? talk : { ...talk, peek: true }}
        thread={thread}
        onThread={channel ? setThread : undefined}
        instead={
          joined ? undefined : (
            <button
              type="button"
              disabled={joining.isPending}
              onClick={() => joining.mutate()}
              className={`${primaryButton} self-center`}
            >
              {t('channel.join')}
            </button>
          )
        }
      />
      {opened}
    </div>
  );
}

/** The user's conversations, the latest written to first, each with what it last said. */
export function Conversations({ current }: { current: string | null }) {
  const { t, formatNumber, formatTime, formatDay } = useI18n();
  const { conversations } = useLive();
  const navigate = useNavigate();
  const press = useMenuPress();
  const today = formatDay(new Date());
  if (conversations.length === 0)
    return <p className="px-2 text-sm text-muted">{t('chat.none')}</p>;
  const ask = (each: Summary, what: Asked) =>
    void navigate(`/chat/${each.id}`, { state: { ask: what } });
  const row = (each: Summary) => {
    const at = each.last && new Date(each.last.at);
    const line = (
      <li key={each.id} {...press} className="select-none [-webkit-touch-callout:none]">
        <Link
          to={`/chat/${each.id}`}
          aria-current={each.id === current ? 'page' : undefined}
          className="flex min-w-0 items-center gap-2 rounded px-2 py-2 hover:bg-hover aria-[current=page]:bg-selected"
        >
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline gap-2">
              <span
                className={`min-w-0 flex-1 truncate text-sm ${each.unread ? 'font-semibold' : ''}`}
              >
                {each.kind === 'channel' &&
                  (each.private ? (
                    <Lock size={12} aria-hidden className="mr-1 inline" />
                  ) : (
                    <Hash size={12} aria-hidden className="mr-1 inline" />
                  ))}
                {each.kind === 'direct' && each.online.length > 0 && (
                  <span
                    role="img"
                    aria-label={t('chat.online')}
                    className="mr-1.5 inline-block size-2 rounded-full bg-accent"
                  />
                )}
                {nameOf(each, t)}
              </span>
              {at && (
                <span className="shrink-0 text-xs text-muted">
                  {formatDay(at) === today ? formatTime(at) : formatDay(at)}
                </span>
              )}
            </span>
            <span className="block truncate text-xs text-muted">
              {each.last ? (
                <>
                  {each.last.by && `${each.last.by}: `}
                  {each.last.text ||
                    (each.last.meeting
                      ? t('chat.meetingOpened')
                      : t('chat.files').replace('{count}', formatNumber(each.last.files)))}
                </>
              ) : (
                t('chat.empty')
              )}
            </span>
          </span>
          {waitingIn(each) > 0 && (
            <span
              aria-label={t('chat.unread')}
              className="min-w-5 shrink-0 rounded-full bg-accent px-1.5 text-center text-xs font-semibold leading-5 text-on-accent tabular-nums"
            >
              {formatNumber(waitingIn(each))}
            </span>
          )}
        </Link>
      </li>
    );
    if (each.kind === 'direct') return line;
    return (
      <ContextMenuArea
        key={each.id}
        items={
          <>
            <MenuItem
              icon={UserPlus}
              label={t('invite.add')}
              onSelect={() => ask(each, 'people')}
            />
            {(each.kind === 'group' || each.kind === 'channel') && (
              <MenuItem
                icon={Pencil}
                label={t('tree.rename')}
                onSelect={() => ask(each, 'rename')}
              />
            )}
            <MenuItem icon={LogOut} label={t('chat.leave')} onSelect={() => ask(each, 'leave')} />
            {each.removable && (
              <MenuItem
                icon={Trash2}
                label={t('channel.remove')}
                onSelect={() => ask(each, 'remove')}
              />
            )}
          </>
        }
      >
        {line}
      </ContextMenuArea>
    );
  };
  const channels = conversations.filter((each) => each.kind === 'channel');
  const others = conversations.filter((each) => each.kind !== 'channel');
  return (
    <div className="flex flex-col gap-0.5">
      {channels.length > 0 && (
        <>
          <h2 className="px-2 text-xs font-semibold text-muted uppercase">
            {t('channel.channels')}
          </h2>
          <ul aria-label={t('channel.channels')} className="flex flex-col gap-0.5">
            {channels.map(row)}
          </ul>
          {others.length > 0 && (
            <h2 className="mt-2 px-2 text-xs font-semibold text-muted uppercase">
              {t('chat.conversations')}
            </h2>
          )}
        </>
      )}
      {others.length > 0 && (
        <ul aria-label={t('chat.conversations')} className="flex flex-col gap-0.5">
          {others.map(row)}
        </ul>
      )}
    </div>
  );
}
