import { keepPreviousData, useQueries, useQuery } from '@tanstack/react-query';
import {
  CalendarDays,
  History,
  ListTodo,
  MessagesSquare,
  Mail,
  Paperclip,
  CircleHelp,
  Search,
  User,
  Vault,
  X,
  type LucideIcon,
} from 'lucide-react';
import {
  Fragment,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import { Link, useLocation } from 'react-router';
import { compact } from './address';
import { getJson } from './api';
import { dayOf, ZONE } from './calendarData';
import type { NoteKind } from './editor/schema';
import { isMessageKey, useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { shortcutLabel } from './keys';
import { usePalette, type Choice } from './palette';
import { usePlaces } from './places';
import { searchHref, useTranslator } from './sentence';
import { useSettled } from './settled';
import { iconButton } from './styles';
import { cellQuery, tabHref } from './tabs';
import { fold, matches, useHeld, wordsOf } from './vault/search';
import { hostOf } from './vault/secret';
import { useVault, useVaultData } from './vault/state';
import {
  errorMessage,
  KIND_ICONS,
  nodeHref,
  NodeIcon,
  placeText,
  PlaceLink,
  TREE,
  useOpen,
  type FoundNode,
  type NodeKind,
  type TreeNode,
} from './tree';
import {
  type Account,
  ACCOUNTS,
  type Accounts,
  accountColor,
  correspondents,
  inBox,
  type Person,
  type Role,
} from './mailData';
import { useReachable } from './live';

export const KINDS = [
  'document',
  'file',
  'link',
  'folder',
  'mail',
  'conversation',
  'event',
  'task',
  'person',
  'vault',
  'version',
] as const;
export type SearchKind = (typeof KINDS)[number];
export const SEARCH_ICONS: Record<SearchKind, LucideIcon> = {
  ...KIND_ICONS,
  mail: Mail,
  conversation: MessagesSquare,
  event: CalendarDays,
  task: ListTodo,
  person: User,
  vault: Vault,
  version: History,
};
const GROUPS = [
  'documents',
  'mail',
  'conversations',
  'events',
  'tasks',
  'people',
  'vault',
  'versions',
  'help',
] as const;
type Group = (typeof GROUPS)[number];
interface Section {
  group: Group;
  items: { key: string; href: string; shown: ReactNode }[];
}
export const LAST = ['week', 'month', 'year'] as const;

export const SHORTEST = 2;
const SHOWN = 8;
const COMMANDS_SHOWN = 5;
const MARK = '\ue000';
const END = '\ue001';
const GROUP_HEADING = 'px-2 pt-2 pb-1 text-xs font-medium tracking-wide text-muted uppercase';

/** Where a search looks, besides what its words and filters ask: inside one folder of
 * documents, or among one kind of result alone. */
export interface SearchScope {
  in?: string | null;
  kind?: NodeKind;
}

export const EVERYWHERE: SearchScope = {};

export interface Address {
  section?: string;
  /** The number the section's heading shows, where a style numbers it. */
  heading?: string;
  paragraph?: number;
  /** The number the block shows, where a style numbers it. */
  number?: string;
  table?: number;
  cell?: string;
  /** The name of the cell's table, where it has one. */
  name?: string;
  image?: number;
  chart?: number;
  pdf?: number;
  note?: NoteKind;
}

export interface Period {
  from?: string | null;
  to?: string | null;
  last?: (typeof LAST)[number];
}

/** A filter typed among the words, as the backend read it: where it stands in the box, what it
 * narrows to, or why it cannot. */
export interface SearchFilter {
  key: 'kind' | 'from' | 'account' | 'folder' | 'date' | 'changed' | 'has';
  token: string;
  /** Its value as typed. */
  raw: string;
  start: number;
  end: number;
  value?: string | Period;
  role?: Role;
  error?: 'empty' | 'invalid_kind' | 'invalid_date' | 'invalid_has';
}

export interface MailResult {
  id: number;
  folder: number;
  account: number | null;
  accounts: number[];
  subject: string;
  sender: Partial<Person>;
  to: Person[];
  date: string;
  seen: boolean;
  /** The role of the folder it is in. */
  role: Role | '';
  /** The shared mailbox it is in, none in the user's own. */
  box: { id: number; name: string } | null;
  attachment: { id: number; name: string; page: number | null } | null;
  hits: number;
  snippet: string;
  /** The subject with the words that matched marked. */
  marked: string;
}

export interface EventResult {
  id: number;
  master: number | null;
  calendar: { id: number; name: string; color: number; account: string | null };
  summary: string;
  /** The summary with the words that matched marked. */
  marked: string;
  /** The place or the description where the words matched there. */
  snippet: string;
  location: string;
  all_day: boolean;
  /** The day of an all-day event, else the start on the user's clock. */
  start: string;
  end: string;
  recurring: boolean;
  /** The occurrences of a series that matched; a series is one hit. */
  hits: number;
}

export interface TaskResult {
  id: number;
  text: string;
  marked: string;
  due: string | null;
  done: boolean;
}

export type PersonKind = 'contact' | 'colleague' | 'directory';

export interface PersonResult {
  kind: PersonKind;
  id: number;
  name: string;
  organisation: string;
  title: string;
  email: string;
  phone: string;
}

/** An item of the vault matched in the browser: the server never sees what it holds. */
export interface VaultResult {
  id: string;
  collection: string;
  collectionName: string;
  name: string;
  marked: string;
  username: string;
  host: string;
}

/** A document's newest version that says the words, asked for by vrsta:verzija. */
export interface VersionResult {
  id: string;
  number: number;
  title: string;
  created_at: string;
  restored_from: number | null;
  editors: { id: number; name: string }[];
  document: FoundNode;
  /** The tab whose text matched; none where the version's title did. */
  tab: { id: string; title: string } | null;
  /** The versions of the document that matched; the document is one hit. */
  hits: number;
  snippet: string;
}

export interface HelpResult {
  id: string;
  title: string;
  summary: string;
}

export interface ConversationResult {
  id: number;
  conversation: string;
  /** The message whose thread this one answers. */
  parent: number | null;
  kind: 'meeting' | 'direct' | 'group' | 'channel';
  title: string;
  by: string;
  at: string;
  snippet: string;
}

export function conversationHref({ conversation, id, parent }: ConversationResult): string {
  return `/chat/${conversation}?message=${parent ?? id}${parent ? `&reply=${id}` : ''}`;
}

export interface Found {
  filters: SearchFilter[];
  documents: SearchResult[];
  mail: MailResult[];
  conversations: ConversationResult[];
  events: EventResult[];
  tasks: TaskResult[];
  people: PersonResult[];
  versions: VersionResult[];
  help: HelpResult[];
}

type Groups = Omit<Found, 'filters'> & { vault: VaultResult[] };

export interface SearchResult extends FoundNode {
  source: 'title' | 'link' | 'tab' | 'block' | 'comment' | 'page' | 'data';
  tab: { id: string; title: string } | null;
  page: number | null;
  block: string | null;
  address: Address | null;
  thread: string | null;
  hits: number;
  snippet: string;
}

export function searchQuery(q: string, scope: SearchScope, limit: number): string {
  const params = new URLSearchParams({
    q: scope.kind ? `${q} kind:${scope.kind}` : q,
    limit: String(limit),
    zone: ZONE,
  });
  if (scope.in) params.set('in', scope.in);
  return params.toString();
}

export function useSearch(q: string, scope: SearchScope, limit: number) {
  const { language } = useI18n();
  const text = q.trim();
  return useQuery({
    queryKey: [...TREE, 'search', text, scope, limit, language],
    queryFn: () =>
      getJson<Found>(`/api/search?${searchQuery(text, scope, limit)}&lang=${language}`),
    enabled: text.length >= SHORTEST,
    placeholderData: keepPreviousData,
  });
}

/** The box's text with the filter's token put in place of the one typed, or taken out. */
export function replaced(text: string, filter: SearchFilter, token: string): string {
  const at =
    text.slice(filter.start, filter.end) === filter.token
      ? filter.start
      : text.indexOf(filter.token);
  if (at < 0) return text;
  return `${text.slice(0, at)}${token}${text.slice(at + filter.token.length)}`
    .replace(/\s+/g, ' ')
    .trim();
}

/** The box's text with the token in place of the filter of the same keys, or after the words. */
export function withFilter(
  text: string,
  filters: SearchFilter[],
  keys: SearchFilter['key'][],
  token: string,
): string {
  const same = filters.find((filter) => keys.includes(filter.key));
  return same ? replaced(text, same, token) : `${text.trim()} ${token}`.trim();
}

export function marked(snippet: string): { text: string; mark: boolean }[] {
  return snippet
    .split(END)
    .flatMap((chunk) => {
      const [before, inside] = chunk.split(MARK);
      return [
        { text: before, mark: false },
        ...(inside === undefined ? [] : [{ text: inside, mark: true }]),
      ];
    })
    .filter((part) => part.text);
}

export function resultHref(result: SearchResult): string {
  if (result.source === 'tab' && result.tab) return tabHref(nodeHref(result), result.tab);
  if (result.source === 'block' && result.tab && result.block) {
    const { cell, table, name } = result.address ?? {};
    const query = cell
      ? cellQuery(cell, { id: result.block, name: name ?? null, first: table === 1 })
      : new URLSearchParams({ block: result.block }).toString();
    return `${tabHref(nodeHref(result), result.tab)}?${query}`;
  }
  if (result.source === 'comment' && result.thread) {
    const thread = new URLSearchParams({
      panel: 'comments',
      comment: result.thread,
    });
    const home = nodeHref(result);
    return `${result.tab ? tabHref(home, result.tab) : home}?${thread}`;
  }
  if (result.source === 'page' && result.page) {
    const page = new URLSearchParams({ page: String(result.page) });
    const word = marked(result.snippet).find((part) => part.mark)?.text;
    if (word) page.set('find', word);
    return `${nodeHref(result)}?${page}`;
  }
  return nodeHref(result);
}

export function eventHref(result: EventResult): string {
  const day = result.all_day ? result.start : dayOf(new Date(result.start));
  return `/calendar/day/${day}?event=${result.id}`;
}

export function taskHref(result: TaskResult): string {
  return `/tasks?task=${result.id}`;
}

export function personHref(result: PersonResult): string {
  if (result.kind === 'contact') return `/contacts/${result.id}`;
  return `/contacts?${new URLSearchParams({ q: result.email || result.name })}`;
}

export function vaultHref(result: VaultResult): string {
  return `/vault/${result.collection}/${result.id}`;
}

export function versionHref(result: VersionResult): string {
  const version = `${nodeHref(result.document)}/versions/${compact(result.id)}`;
  return result.tab ? `${version}/${compact(result.tab.id)}` : version;
}

/** Whether the filters leave the vault in: none, or its kind alone. */
export function asksVault(filters: SearchFilter[]): boolean {
  return filters.every((filter) => filter.key === 'kind' && filter.value === 'vault');
}

/** The words typed besides the filters and the operators, folded. */
export function plainWords(text: string, filters: SearchFilter[]): string[] {
  let kept = '';
  let at = 0;
  for (const filter of filters) {
    kept += text.slice(at, filter.start);
    at = filter.end;
  }
  kept += text.slice(at);
  return wordsOf(
    kept
      .split(/\s+/)
      .filter((word) => !word.startsWith('-') && word.toLowerCase() !== 'or')
      .join(' '),
  );
}

/** The text with each word one of the words starts marked, as the server marks a snippet. */
export function markWords(text: string, words: string[]): string {
  return text.replace(/[\p{L}\p{N}]+/gu, (word) =>
    words.some((each) => fold(word).startsWith(each)) ? `${MARK}${word}${END}` : word,
  );
}

/** The vault's items the words match, while it is unlocked and the filters leave it in. */
export function useVaultHits(found: Found | undefined, text: string): VaultResult[] {
  const { t } = useI18n();
  const wanted = found !== undefined && asksVault(found.filters);
  const held = useHeld(wanted);
  const words = wanted ? plainWords(text, found.filters) : [];
  if (words.length === 0 || !held.data) return [];
  return held.data
    .filter(({ item }) => matches(item, words))
    .map(({ item, collection }) => ({
      id: item.id,
      collection: collection.id,
      collectionName: collection.kind === 'personal' ? t('vault.mine') : collection.name,
      name: item.secret.name,
      marked: markWords(item.secret.name, words),
      username: item.secret.username,
      host: item.secret.urls.map(hostOf).find(Boolean) ?? '',
    }));
}

/** A line saying the vault was not searched, where the user has one and it is locked. */
export function VaultLocked({ shown }: { shown: boolean }) {
  const { t } = useI18n();
  const { unlocked } = useVault();
  const vault = useVaultData();
  if (!shown || unlocked || !vault.data) return null;
  return (
    <p className="py-1.5 text-sm text-muted">
      {t('search.vaultLocked')}{' '}
      <Link to="/vault" className="underline underline-offset-2">
        {t('vault.unlock')}
      </Link>
    </p>
  );
}

/** How many of each group a short list shows: an equal share each, and what a group too short
 * for its share leaves goes to the longer ones. */
export function allotted(counts: number[], most: number): number[] {
  const shown = counts.map(() => 0);
  let left = most;
  let open = counts.flatMap((count, index) => (count > 0 ? [index] : []));
  while (left > 0 && open.length > 0) {
    const share = Math.floor(left / open.length);
    if (share === 0) {
      for (const index of open.slice(0, left)) shown[index] += 1;
      break;
    }
    for (const index of open) {
      const more = Math.min(share, counts[index] - shown[index]);
      shown[index] += more;
      left -= more;
    }
    open = open.filter((index) => shown[index] < counts[index]);
  }
  return shown;
}

/** A number with words of its own, as "Članak 3.", names its place by itself. */
function named(number: string, word: string): string {
  return /\s/.test(number) ? number : `${word} ${number}`;
}

/** Where in its node a hit is, as a reader would point to it, by the numbers its document shows. */
export function placeOf(
  result: SearchResult,
  t: (key: MessageKey) => string,
  formatNumber: (value: number) => string,
): string {
  if (result.source === 'tab') return t('search.tab');
  if (result.source === 'link') return t('kind.link');
  if (result.source === 'data') return t('search.data');
  if (result.source === 'comment') {
    return [result.tab?.title, t('search.comment')].filter(Boolean).join(' · ');
  }
  if (result.source === 'page') return `${t('search.page')} ${formatNumber(result.page ?? 0)}`;
  const { section, heading, table, cell, image, chart, pdf, paragraph, number, note } =
    result.address ?? {};
  return [
    result.tab?.title,
    section && named(heading ?? section, t('search.section')),
    table && `${t('search.table')} ${formatNumber(table)}`,
    cell && `${t('search.cell')} ${cell}`,
    image && `${t('search.image')} ${formatNumber(image)}`,
    chart && `${t('search.chart')} ${formatNumber(chart)}`,
    pdf && `${t('search.pdf')} ${formatNumber(pdf)}`,
    pdf && result.page && `${t('search.page')} ${formatNumber(result.page)}`,
    paragraph &&
      (number
        ? named(number, t('search.paragraph'))
        : `${t('search.paragraph')} ${formatNumber(paragraph)}`),
    note && t(note === 'end' ? 'search.endnote' : 'search.footnote'),
  ]
    .filter(Boolean)
    .join(' · ');
}

export function mailHref(
  result: Pick<MailResult, 'id' | 'folder' | 'account'> & Partial<Pick<MailResult, 'box'>>,
  accounts: Account[],
): string {
  const first = accounts.find((account) => account.id === result.account);
  const path = `/mail/${result.folder}/${result.id}${first && !first.together ? `?account=${first.id}` : ''}`;
  return inBox(path, result.box?.id ?? null);
}

/** The accounts of the mailbox each message is in, the user's own or a shared one's. */
export function useMailAccounts(mail: MailResult[]): (result: MailResult) => Account[] {
  const boxes = [...new Set(mail.map((result) => result.box?.id ?? null))];
  const found = useQueries({
    queries: boxes.map((box) => ({
      queryKey: [...ACCOUNTS, box],
      queryFn: () => getJson<Accounts>(inBox('/api/mail/accounts', box)),
    })),
  });
  return (result) => found[boxes.indexOf(result.box?.id ?? null)]?.data?.accounts ?? [];
}

function Snippet({ text }: { text: string }) {
  return marked(text).map((part, index) =>
    part.mark ? (
      <mark key={index} className="rounded-sm bg-mark text-ink">
        {part.text}
      </mark>
    ) : (
      <Fragment key={index}>{part.text}</Fragment>
    ),
  );
}

export function ResultSummary({ result }: { result: SearchResult }) {
  const { t, formatNumber } = useI18n();
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex min-w-0 items-center gap-2">
        <NodeIcon node={result} decorative />
        <span className="truncate font-medium">
          {result.source === 'title' ? <Snippet text={result.snippet} /> : result.title}
        </span>
      </span>
      <span className="truncate pl-[26px] text-xs text-muted">{placeText(result, t)}</span>
      {result.source !== 'title' && (
        <span className="line-clamp-2 pl-[26px] text-sm text-muted">
          <span className="text-ink">{placeOf(result, t, formatNumber)}: </span>
          <Snippet text={result.snippet} />
        </span>
      )}
    </span>
  );
}

export function MailSummary({ result, accounts }: { result: MailResult; accounts: Account[] }) {
  const { t, formatDate, formatNumber } = useI18n();
  const came = result.accounts.flatMap((id) => accounts.filter((account) => account.id === id));
  const { attachment } = result;
  return (
    <span className="flex min-w-0 flex-1 gap-2">
      {came.length > 0 && (
        <span aria-hidden className="flex w-1 shrink-0 flex-col overflow-hidden rounded-full">
          {came.map((account) => (
            <span key={account.id} className={`flex-1 ${accountColor(account, result.seen)}`} />
          ))}
        </span>
      )}
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex min-w-0 items-center gap-2">
          <Mail size={16} aria-hidden className="shrink-0 text-muted" />
          <span className="truncate font-medium">
            {result.marked ? <Snippet text={result.marked} /> : t('mail.noSubject')}
          </span>
        </span>
        <span className="truncate pl-6 text-xs text-muted">
          {result.box && `${result.box.name} · `}
          {correspondents(result, result.role)} · {formatDate(result.date)}
        </span>
        {result.snippet && (
          <span className="line-clamp-2 pl-6 text-sm text-muted">
            {attachment && (
              <span className="text-ink">
                <Paperclip size={12} aria-hidden className="mr-1 inline" />
                {t('search.attachment')} „{attachment.name}”
                {attachment.page && ` · ${t('search.page')} ${formatNumber(attachment.page)}`}:{' '}
              </span>
            )}
            <Snippet text={result.snippet} />
          </span>
        )}
      </span>
    </span>
  );
}

export function EventSummary({ result }: { result: EventResult }) {
  const { formatDay, formatTime } = useI18n();
  const start = new Date(result.all_day ? `${result.start}T00:00` : result.start);
  const when = result.all_day ? formatDay(start) : `${formatDay(start)} ${formatTime(start)}`;
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex min-w-0 items-center gap-2">
        <CalendarDays size={16} aria-hidden className="shrink-0 text-muted" />
        <span className="truncate font-medium">
          <Snippet text={result.marked} />
        </span>
      </span>
      <span className="truncate pl-6 text-xs text-muted">
        {when} · {result.calendar.name}
      </span>
      {result.snippet && (
        <span className="line-clamp-2 pl-6 text-sm text-muted">
          <Snippet text={result.snippet} />
        </span>
      )}
    </span>
  );
}

export function ConversationSummary({ result }: { result: ConversationResult }) {
  const { formatDay } = useI18n();
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex min-w-0 items-center gap-2">
        <MessagesSquare size={16} aria-hidden className="shrink-0 text-muted" />
        <span className="truncate font-medium">{result.title}</span>
      </span>
      <span className="truncate pl-6 text-xs text-muted">
        {result.by}, {formatDay(new Date(result.at))}: <Snippet text={result.snippet} />
      </span>
    </span>
  );
}

export function TaskSummary({ result }: { result: TaskResult }) {
  const { t, formatDay } = useI18n();
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex min-w-0 items-center gap-2">
        <ListTodo size={16} aria-hidden className="shrink-0 text-muted" />
        <span className={`truncate font-medium ${result.done ? 'text-muted line-through' : ''}`}>
          <Snippet text={result.marked} />
        </span>
      </span>
      {(result.done || result.due) && (
        <span className="truncate pl-6 text-xs text-muted">
          {result.done
            ? t('tasks.done')
            : `${t('tasks.due')}: ${formatDay(new Date(`${result.due}T00:00`))}`}
        </span>
      )}
    </span>
  );
}

export function PersonSummary({ result }: { result: PersonResult }) {
  const { t } = useI18n();
  const about = [result.title, result.organisation, result.email || result.phone]
    .filter(Boolean)
    .join(' · ');
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex min-w-0 items-center gap-2">
        <User size={16} aria-hidden className="shrink-0 text-muted" />
        <span className="truncate font-medium">{result.name}</span>
        <span className="ml-auto shrink-0 text-xs text-muted">
          {t(`search.person.${result.kind}`)}
        </span>
      </span>
      {about && <span className="truncate pl-6 text-xs text-muted">{about}</span>}
    </span>
  );
}

export function HelpSummary({ result }: { result: HelpResult }) {
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex min-w-0 items-center gap-2">
        <CircleHelp size={16} aria-hidden className="shrink-0 text-muted" />
        <span className="truncate font-medium">{result.title}</span>
      </span>
      <span className="line-clamp-2 pl-6 text-sm text-muted">{result.summary}</span>
    </span>
  );
}

export function VersionSummary({ result }: { result: VersionResult }) {
  const { t, formatDate, formatNumber } = useI18n();
  const name =
    result.title ||
    (result.restored_from === null
      ? t('version.automatic')
      : `${t('version.restoredFrom')} ${formatNumber(result.restored_from)}`);
  const about = [
    result.document.title,
    `${t('version.number')} ${formatNumber(result.number)}`,
    formatDate(result.created_at),
  ].join(' · ');
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex min-w-0 items-center gap-2">
        <History size={16} aria-hidden className="shrink-0 text-muted" />
        <span className="truncate font-medium">
          {result.tab || !result.snippet ? name : <Snippet text={result.snippet} />}
        </span>
      </span>
      <span className="truncate pl-6 text-xs text-muted">{about}</span>
      {result.tab && (
        <span className="line-clamp-2 pl-6 text-sm text-muted">
          {result.tab.title && <span className="text-ink">{result.tab.title}: </span>}
          <Snippet text={result.snippet} />
        </span>
      )}
    </span>
  );
}

export function VaultSummary({ result }: { result: VaultResult }) {
  const about = [result.username, result.host, result.collectionName].filter(Boolean).join(' · ');
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
      <span className="flex min-w-0 items-center gap-2">
        <Vault size={16} aria-hidden className="shrink-0 text-muted" />
        <span className="truncate font-medium">
          <Snippet text={result.marked} />
        </span>
      </span>
      {about && <span className="truncate pl-6 text-xs text-muted">{about}</span>}
    </span>
  );
}

function periodText(
  period: Period,
  t: (key: MessageKey) => string,
  formatDays: (first: string, last: string) => string,
): string {
  if (period.last) return t(`search.last.${period.last}`);
  if (period.from && period.to) return formatDays(period.from, period.to);
  if (period.from) return `${t('search.filter.since')} ${formatDays(period.from, period.from)}`;
  return `${t('search.filter.until')} ${formatDays(period.to ?? '', period.to ?? '')}`;
}

function filterText(
  filter: SearchFilter,
  t: (key: MessageKey) => string,
  formatDays: (first: string, last: string) => string,
): string {
  const { value } = filter;
  if (filter.error || value === undefined) return filter.token;
  if (typeof value !== 'string') return periodText(value, t, formatDays);
  if (filter.key === 'has') return t('search.filter.has');
  if (filter.role) return t(`mail.role.${filter.role}`);
  const kind = `search.kind.${value}`;
  return filter.key === 'kind' && isMessageKey(kind) ? t(kind) : value;
}

/** The filters the box holds, each to be taken out; a period of documents turns between when
 * they were made and when they were changed. */
export function FilterChips({
  text,
  filters,
  onChange,
}: {
  text: string;
  filters: SearchFilter[];
  onChange: (text: string) => void;
}) {
  const { t, formatDays } = useI18n();
  if (filters.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-1">
      {filters.map((filter) => {
        const label = filter.key === 'kind' ? t('search.kind') : t(`search.filter.${filter.key}`);
        const dated = !filter.error && (filter.key === 'date' || filter.key === 'changed');
        return (
          <li
            key={`${filter.start}:${filter.token}`}
            className={`inline-flex min-w-0 items-center gap-1 rounded border py-0.5 pr-0.5 pl-2 text-sm ${filter.error ? 'border-danger text-danger' : 'border-line'}`}
          >
            {dated ? (
              <button
                type="button"
                title={t(
                  filter.key === 'date' ? 'search.filter.toChanged' : 'search.filter.toMade',
                )}
                onClick={() => {
                  const key = filter.key === 'date' ? 'search.token.changed' : 'search.token.date';
                  onChange(replaced(text, filter, `${t(key)}:${filter.raw}`));
                }}
                className="rounded text-muted underline decoration-dotted underline-offset-2 hover:text-ink"
              >
                {label}:
              </button>
            ) : (
              !filter.error && filter.key !== 'has' && <span className="text-muted">{label}:</span>
            )}
            <span className="truncate">{filterText(filter, t, formatDays)}</span>
            <button
              type="button"
              aria-label={`${t('search.filter.remove')} ${filter.token}`}
              title={t('search.filter.remove')}
              onClick={() => onChange(replaced(text, filter, ''))}
              className={iconButton}
            >
              <X size={14} aria-hidden />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function FilterErrors({ filters }: { filters: SearchFilter[] }) {
  const { t } = useI18n();
  return filters.map(
    (filter) =>
      filter.error && (
        <p key={`${filter.start}:${filter.token}`} className="text-sm text-danger">
          „{filter.token}”: {t(`search.error.${filter.error}`)}
        </p>
      ),
  );
}

let box: HTMLInputElement | null = null;

export function focusSearch(): void {
  box?.focus();
  box?.select();
}

/** Alt+/ reaches the box from anywhere; Ctrl+K only where nothing else took it, since in the text
 * it makes a link. */
function wantsSearch(event: globalThis.KeyboardEvent): boolean {
  if (event.defaultPrevented) return false;
  if (event.altKey && !event.ctrlKey && !event.metaKey) {
    return event.key === '/' || event.code === 'Slash';
  }
  return (event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 'k';
}

export function SearchBox({ here }: { here?: Pick<TreeNode, 'id' | 'title'> }) {
  const { t } = useI18n();
  const reachable = useReachable();
  const opened = useOpen();
  const input = useRef<HTMLInputElement>(null);
  const list = useId();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const { pathname } = useLocation();
  const typed = useSettled(q.trim(), 150);
  const search = useSearch(typed, EVERYWHERE, SHOWN);
  const found = typed.length >= SHORTEST ? search.data : undefined;
  const filters = found?.filters ?? [];
  const all: Groups = {
    documents: found?.documents ?? [],
    mail: found?.mail ?? [],
    conversations: found?.conversations ?? [],
    events: found?.events ?? [],
    tasks: found?.tasks ?? [],
    people: found?.people ?? [],
    vault: useVaultHits(found, typed),
    versions: found?.versions ?? [],
    help: found?.help ?? [],
  };
  const shares = allotted(
    GROUPS.map((group) => all[group].length),
    SHOWN,
  );
  const documents = all.documents.slice(0, shares[0]);
  const mail = all.mail.slice(0, shares[1]);
  const talks = all.conversations.slice(0, shares[2]);
  const events = all.events.slice(0, shares[3]);
  const tasks = all.tasks.slice(0, shares[4]);
  const people = all.people.slice(0, shares[5]);
  const vault = all.vault.slice(0, shares[6]);
  const versions = all.versions.slice(0, shares[7]);
  const help = all.help.slice(0, shares[8]);
  const accountsOf = useMailAccounts(mail);
  const palette = usePalette();
  const places = usePlaces();
  const text = q.trim();
  const commands =
    text.length >= SHORTEST
      ? [...(palette?.(text) ?? []), ...places(text)].slice(0, COMMANDS_SHOWN)
      : [];
  const listed: Section[] = [
    {
      group: 'documents',
      items: documents.map((result) => ({
        key: result.id,
        href: resultHref(result),
        shown: <ResultSummary result={result} />,
      })),
    },
    {
      group: 'mail',
      items: mail.map((result) => ({
        key: String(result.id),
        href: mailHref(result, accountsOf(result)),
        shown: <MailSummary result={result} accounts={accountsOf(result)} />,
      })),
    },
    {
      group: 'conversations',
      items: talks.map((result) => ({
        key: String(result.id),
        href: conversationHref(result),
        shown: <ConversationSummary result={result} />,
      })),
    },
    {
      group: 'events',
      items: events.map((result) => ({
        key: String(result.id),
        href: eventHref(result),
        shown: <EventSummary result={result} />,
      })),
    },
    {
      group: 'tasks',
      items: tasks.map((result) => ({
        key: String(result.id),
        href: taskHref(result),
        shown: <TaskSummary result={result} />,
      })),
    },
    {
      group: 'people',
      items: people.map((result) => ({
        key: `${result.kind}-${result.id}`,
        href: personHref(result),
        shown: <PersonSummary result={result} />,
      })),
    },
    {
      group: 'vault',
      items: vault.map((result) => ({
        key: result.id,
        href: vaultHref(result),
        shown: <VaultSummary result={result} />,
      })),
    },
    {
      group: 'versions',
      items: versions.map((result) => ({
        key: result.id,
        href: versionHref(result),
        shown: <VersionSummary result={result} />,
      })),
    },
    {
      group: 'help',
      items: help.map((result) => ({
        key: result.id,
        href: `/help/${result.id}`,
        shown: <HelpSummary result={result} />,
      })),
    },
  ];
  const sections = listed.filter((section) => section.items.length > 0);
  const hrefs = sections.flatMap((section) => section.items.map((item) => item.href));
  const options = commands.length + hrefs.length;
  const translator = useTranslator(go);

  // Empty on each page unless typed in: a page comes in a transition a moment after its link is
  // followed, and what is typed meanwhile stays.
  useEffect(() => {
    if (document.activeElement === input.current) return;
    setQ('');
    setOpen(false);
    setActive(-1);
  }, [pathname]);

  useEffect(() => {
    const own = input.current;
    box = own;
    function focus(event: globalThis.KeyboardEvent) {
      if (!wantsSearch(event)) return;
      event.preventDefault();
      focusSearch();
    }
    window.addEventListener('keydown', focus);
    return () => {
      window.removeEventListener('keydown', focus);
      if (box === own) box = null;
    };
  }, []);

  function close() {
    setOpen(false);
    setActive(-1);
    input.current?.blur();
  }

  function go(to: string) {
    close();
    opened(to);
  }

  function showAll(within?: string) {
    const text = q.trim();
    if (!text) return;
    const params = new URLSearchParams({ q: text });
    if (within) params.set('in', within);
    go(`/search?${params}`);
  }

  function submit() {
    if (translator.pending) return;
    const href = hrefs[active - commands.length];
    if (commands[active]) perform(commands[active]);
    else if (href) go(href);
    else if (!translator.translate(q)) showAll();
  }

  function perform(choice: Choice) {
    if (choice.disabled) return;
    setQ('');
    close();
    choice.run();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const next = active + (event.key === 'ArrowDown' ? 1 : -1);
      setActive(next >= options ? -1 : next < -1 ? options - 1 : next);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      submit();
    } else if (event.key === 'Escape') {
      close();
    }
  }

  return (
    <div className="relative w-9 shrink-0 max-sm:focus-within:absolute max-sm:focus-within:inset-x-2 max-sm:focus-within:top-2 max-sm:focus-within:z-40 max-sm:focus-within:w-auto sm:w-72 sm:shrink">
      <Search
        size={16}
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted"
      />
      <input
        ref={input}
        type="search"
        role="combobox"
        autoComplete="off"
        aria-expanded={open}
        aria-controls={list}
        aria-activedescendant={active >= 0 ? `${list}-${active}` : undefined}
        aria-label={t('search.label')}
        placeholder={t(reachable ? 'search.placeholder' : 'offline.needed')}
        disabled={!reachable}
        value={q}
        onChange={(event) => {
          setQ(event.target.value);
          setActive(-1);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className="w-full rounded border border-transparent bg-surface py-1.5 pr-2 pl-8 text-sm text-ink outline-none placeholder:text-muted focus:border-focus max-sm:cursor-pointer max-sm:text-transparent max-sm:placeholder:text-transparent max-sm:focus:cursor-text max-sm:focus:text-ink max-sm:focus:placeholder:text-muted sm:border-line sm:pr-16"
      />
      {!q && (
        <kbd className="pointer-events-none absolute top-1/2 right-2 hidden -translate-y-1/2 rounded border border-line px-1 font-sans text-xs text-muted sm:block">
          {shortcutLabel('Alt-/')}
        </kbd>
      )}
      {open && (
        <div
          onMouseDown={(event) => event.preventDefault()}
          className="absolute top-full right-0 z-50 mt-1 flex max-h-[70dvh] w-[min(30rem,calc(100vw-1rem))] flex-col overflow-y-auto rounded border border-line bg-raised p-1 text-ink shadow-lg max-sm:left-0 max-sm:w-auto"
        >
          {filters.length > 0 && (
            <div className="px-1 pt-1 pb-1.5">
              <FilterChips text={text} filters={filters} onChange={setQ} />
            </div>
          )}
          {options > 0 && (
            <div id={list} role="listbox" aria-label={t('search.label')}>
              {commands.map((choice, index) => (
                <div
                  key={choice.id}
                  id={`${list}-${index}`}
                  role="option"
                  aria-selected={index === active}
                  aria-disabled={choice.disabled}
                  onClick={() => perform(choice)}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-hover aria-disabled:cursor-default aria-disabled:opacity-40 aria-selected:bg-selected"
                >
                  <choice.icon size={16} aria-hidden className="text-muted" />
                  <span className="grow">{choice.label}</span>
                  {choice.keys && (
                    <kbd className="font-sans text-xs text-muted">{shortcutLabel(choice.keys)}</kbd>
                  )}
                </div>
              ))}
              {sections.map((section, at) => {
                const before =
                  commands.length +
                  sections.slice(0, at).reduce((sum, each) => sum + each.items.length, 0);
                return (
                  <div
                    key={section.group}
                    role="group"
                    aria-labelledby={`${list}-${section.group}`}
                  >
                    {sections.length > 1 && (
                      <div id={`${list}-${section.group}`} className={GROUP_HEADING}>
                        {t(`search.${section.group}`)}
                      </div>
                    )}
                    {section.items.map((item, index) => (
                      <PlaceLink
                        key={item.key}
                        id={`${list}-${before + index}`}
                        role="option"
                        aria-selected={before + index === active}
                        to={item.href}
                        onClick={close}
                        className="flex rounded px-2 py-1.5 hover:bg-hover aria-selected:bg-selected"
                      >
                        {item.shown}
                      </PlaceLink>
                    ))}
                  </div>
                );
              })}
            </div>
          )}
          <div className="px-2">
            <FilterErrors filters={filters} />
            <VaultLocked shown={found !== undefined && asksVault(filters)} />
            {translator.pending && (
              <p className="py-1.5 text-sm text-muted">{t('search.ai.translating')}</p>
            )}
            {translator.failed && (
              <p className="py-1.5 text-sm text-danger">
                {errorMessage(translator.failed, t)}{' '}
                <button
                  type="button"
                  onClick={() => go(searchHref(translator.sentence ?? text))}
                  className="underline underline-offset-2"
                >
                  {t('search.ai.literal')}
                </button>
              </p>
            )}
          </div>
          {typed.length < SHORTEST ? (
            commands.length === 0 && (
              <p className="px-2 py-1.5 text-sm text-muted">{t('search.hint')}</p>
            )
          ) : search.isError ? (
            <p className="px-2 py-1.5 text-sm text-danger">{errorMessage(search.error, t)}</p>
          ) : (
            options === 0 &&
            !search.isFetching && (
              <p className="px-2 py-1.5 text-sm text-muted">
                {t('search.none')} „{typed}”.
              </p>
            )
          )}
          {typed.length >= SHORTEST && (
            <div className="mt-1 flex flex-wrap gap-1 border-t border-line pt-1 text-sm">
              <button
                type="button"
                onClick={() => showAll()}
                className="rounded px-2 py-1 hover:bg-hover"
              >
                {t('search.all')}
              </button>
              {here && (
                <button
                  type="button"
                  onClick={() => showAll(here.id)}
                  className="min-w-0 truncate rounded px-2 py-1 text-muted hover:bg-hover hover:text-ink"
                >
                  {t('search.in')} „{here.title}”
                </button>
              )}
            </div>
          )}
        </div>
      )}
      {translator.dialog}
    </div>
  );
}
