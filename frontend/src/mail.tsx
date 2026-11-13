import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query';
import {
  AlarmClock,
  Hourglass,
  Archive,
  ArrowDown,
  ArrowDownUp,
  ArrowLeft,
  ArrowUp,
  Ban,
  CalendarCheck,
  CalendarDays,
  CalendarX,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Clock,
  Eye,
  EyeOff,
  FileDown,
  FilePen,
  FilePlus,
  Folder,
  FolderInput,
  FolderTree,
  FolderSymlink,
  Receipt,
  ImageOff,
  Images,
  Forward,
  Inbox,
  Languages,
  ListTodo,
  Mail,
  MailCheck,
  MailOpen,
  MailPlus,
  Palette,
  Lock,
  Paperclip,
  Pencil,
  Bot,
  Reply,
  ReplyAll,
  RotateCcw,
  Send,
  Settings,
  ShieldBan,
  Signature,
  SmilePlus,
  SquarePen,
  Star,
  StarOff,
  Trash2,
  User,
  X,
  type LucideIcon,
} from 'lucide-react';
import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { type User as Colleague } from './auth';
import { ResponseButtons } from './calendar';
import { CALENDAR, respond, type Invitation } from './calendarData';
import {
  ActionButtons,
  ActionItems,
  ChoiceBar,
  ChoiceBox,
  choiceKeys,
  rowOpener,
  type RowAction,
} from './choice';
import { Compose, fullPerson, type Start, type Unsent, useUnsent, type Way } from './compose';
import { LaterLink, LaterList } from './mailLater';
import { MailboxLinks, Mailboxes } from './mailShared';
import { MoveMailDialog, movesInto } from './mailMove';
import { useAi } from './editor/runs';
import { useReachable } from './live';
import { keptPart } from './kept';
import { type Destination, TRIAGED, TriageDialog, useMessageAction } from './mailTriage';
import { GatherDialog } from './collections';
import { WhenDialog } from './when';
import { between, formatSize } from './explorer';
import { Cancel, Close, ConfirmDialog, Labelled, Modal, NameDialog } from './dialogs';
import { Frame, Loading, PrimaryAction } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { ActionsMenu, ContextMenuArea, Menu, MenuItem, MenuSeparator, MenuSub } from './menu';
import { steady, useLongPress, useMenuPress } from './press';
import { mailto } from './recipients';
import { Splitter, useWidth, type Column } from './split';
import { button, field, iconButton, primaryButton, sideRow } from './styles';
import { TaskDialog } from './tasks';
import { useMessageTranslation } from './translation';
import { errorMessage, nodeHref, useTreeChange } from './tree';
import { placed } from './upload';
import { HtmlBody } from './mailBody';
import { MailKeysSection } from './mailKeyList';
import { RemoveButton } from './mailParts';
import { AccountDialog, OAuthAccountDialog, SignatureDialog, accountError } from './mailAccounts';
import { SealedBody, withUnsealed, type OpenedFile } from './mailSealed';
import { PlainBody } from './plain';
import { Reactions, useReacting, type Reaction } from './reactions';
import {
  type Account,
  ACCOUNT_COLORS,
  accountColor,
  accountName,
  accountRing,
  ACCOUNTS,
  BoxContext,
  correspondents,
  inBox,
  listPath,
  type MailFolder,
  type MailSort,
  type MailSortKey,
  MAIL_SORTS,
  messagePath,
  type Person,
  person,
  type Role,
  storedMailSort,
  storeMailSort,
  useAccounts,
  useBox,
} from './mailData';

/** What a list of messages holds: a folder, or all the user flagged, wherever it lies. */
type MailList = Omit<MailFolder, 'id'> & { id: number | 'flagged' | 'later' };

interface Message {
  id: number;
  folder: number;
  subject: string;
  sender: Partial<Person>;
  to: Person[];
  date: string;
  seen: boolean;
  flagged: boolean;
  answered: boolean;
  /** Until when it is put away, while it is. */
  snoozed_until: string | null;
  awaited_until: string | null;
  unanswered: boolean;
  /** How important the sender marked it: 0 low, 1 normal, 2 high. */
  priority: 0 | 1 | 2;
  attachments: boolean;
  preview: string;
  /** The accounts it came to, the one it is answered from first. */
  accounts: number[];
  /** Of a message the user sent, how many colleagues hold it and how many of them opened it. */
  opened: { held: number; opened: number } | null;
  /** How a signature or encryption seals it (U5), none where nothing does. */
  sealed: '' | 'signed' | 'encrypted';
  /** Whether a retention rule or a legal hold keeps it from being deleted for good. */
  kept: boolean;
}

export interface Attachment {
  part: string;
  name: string;
  type: string;
  size: number;
}

/** A reply an outside agent drafted for the user to send (D18), with the message it answers. */
export interface Draft {
  id: number;
  way: Way;
  text: string;
  by: string | null;
  created_at: string;
  message: Pick<Message, 'id' | 'folder' | 'subject' | 'sender'>;
}

const DRAFTS = ['mail', 'drafts'];

/** The drafts waiting for the user, polled apart from the message, which is read once and kept. */
function useDrafts() {
  const box = useBox();
  return useQuery({
    queryKey: [...DRAFTS, box],
    queryFn: () => getJson<{ drafts: Draft[] }>(inBox('/api/mail/drafts', box)),
    select: (data) => data.drafts,
  });
}

/** A message as it is read: what the list shows of it, its body and the files it carries. */
export interface Opened extends Omit<Message, 'attachments'> {
  cc: Person[];
  reply_to: Person[];
  attachments: Attachment[];
  /** What the message says of a meeting, where it carries a calendar part. */
  invitation: Invitation | null;
  /** Made safe by the server; shown only inside a sandboxed frame. */
  html: string | null;
  text: string | null;
  /** Whether the HTML asks for images from other servers. */
  remote: boolean;
  /** The sender's domain, and whether its images are shown (true) or kept out (false) without
      asking. */
  domain: string | null;
  images: boolean | null;
  /** Whether it came through a mailing list, which names how to leave it. */
  bulk: boolean;
  /** The sender's key as its Autocrypt header offers it. */
  autocrypt: string | null;
  /** What the browser opened of an encrypted message, for a reply to quote or a forward to
      carry; never from the server. */
  unsealed?: { text: string; files: OpenedFile[] };
  /** The emoji people reacted to it with, and whether the user may react to it themselves. */
  reactions: Reaction[];
  reactable: boolean;
  /** The language the server reads it in, where it can tell. */
  language: string | null;
  /** The language its subject and body are translated into, where they are. */
  translated: string | null;
  /** Of a message the user sent, each colleague holding it, those who opened it first. */
  opened_by: {
    colleagues: { user: Colleague; opened_at: string | null }[];
    outside: number;
  } | null;
}

/** A page of a folder's list, with how many messages the whole list shows and how many of them
    are unread. */
interface Page {
  messages: Message[];
  before: string | null;
  count: number;
  unseen: number;
}
type Pages = InfiniteData<Page>;
type Action =
  | 'seen'
  | 'unseen'
  | 'flagged'
  | 'unflagged'
  | 'move'
  | 'delete'
  | 'snooze'
  | 'unsnooze'
  | 'await'
  | 'unawait';
/** The messages chosen in a folder's list: those named, or every one it shows, the read or the
    unread alone if `seen` says so. */
interface Where {
  messages?: number[];
  account?: number;
  seen?: boolean;
}
/** The messages chosen in the list: those named, or every one the list shows, or its read or
    unread alone. */
type Choice = Set<number> | 'all' | 'seen' | 'unseen';

const listed = (
  folder: MailList['id'],
  account: number | undefined,
  sort: MailSort,
  box: number | null,
) => ['mail', 'messages', box, folder, account ?? null, sort.key, sort.descending];
const MESSAGES: Column = { name: 'messages', initial: 448, min: 288, max: 768 };
/** How a sort first runs when chosen, and how each way reads. */
const SORT_WAYS: Record<MailSortKey, [boolean, MessageKey, MessageKey]> = {
  date: [true, 'mail.newestFirst', 'mail.oldestFirst'],
  correspondent: [false, 'mail.aToZ', 'mail.zToA'],
  priority: [true, 'mail.highFirst', 'mail.lowFirst'],
};

const ROLES = {
  inbox: Inbox,
  snoozed: AlarmClock,
  drafts: FilePen,
  sent: Send,
  archive: Archive,
  junk: Ban,
  trash: Trash2,
} satisfies Record<Role, LucideIcon>;
const ORDER = Object.keys(ROLES) as Role[];
const QUIET: MailFolder['role'][] = ['snoozed', 'sent', 'drafts', 'archive', 'trash'];

function folderName(folder: MailList, t: (key: MessageKey) => string): string {
  return folder.role ? t(`mail.role.${folder.role}`) : folder.name;
}

/** The folders inside the parent, each followed by those inside it. */
function branch(
  folders: MailFolder[],
  parent: number,
  depth = 0,
): { folder: MailFolder; depth: number }[] {
  return folders
    .filter((folder) => folder.parent === parent)
    .flatMap((folder) => [{ folder, depth }, ...branch(folders, folder.id, depth + 1)]);
}

/** The account the folder holds mail of, if it holds only one's. */
function accountOf(folder: MailList, folders: MailFolder[]): number | null {
  const parent = folders.find((each) => each.id === folder.parent);
  return folder.account ?? (parent ? accountOf(parent, folders) : null);
}

/** Does the action to the messages chosen in a folder's list, in PONISTRA only. */
function useChosen() {
  const queryClient = useQueryClient();
  const box = useBox();
  return useMutation({
    mutationFn: ({
      folder,
      ...given
    }: {
      folder: MailList['id'];
      action: Action;
      to?: number | Role;
      at?: string;
      where?: Where;
    }) => postJson<{ changed: number }>(inBox(`/api/mail/folders/${folder}/chosen`, box), given),
    onSuccess: (_, { action }) => {
      // A message deleted for good is not read again; whoever has it open goes back to the list.
      if (action === 'delete') queryClient.removeQueries({ queryKey: ['mail', 'message'] });
      void queryClient.invalidateQueries({ queryKey: ['mail'] });
    },
  });
}

/** The folder's path below the node of its account, or from the top for a removed account's. */
function folderPath(folder: MailFolder, folders: MailFolder[]): string {
  const parent = folders.find((each) => each.id === folder.parent);
  return parent && parent.account === null
    ? `${folderPath(parent, folders)} / ${folder.name}`
    : folder.name;
}

/** The folders mail can go to, in the order of the side column: those of a role, each account's
    own, and the user's. */
function destinations(folders: MailFolder[], accounts: Account[]) {
  return {
    roles: ORDER.flatMap(
      (role) => folders.find((folder) => folder.role === role && role !== 'snoozed') ?? [],
    ),
    accounts: accounts.flatMap((account) => {
      const node = folders.find((folder) => folder.account === account.id);
      const inside = node ? branch(folders, node.id).map(({ folder }) => folder) : [];
      return inside.length > 0 ? [{ account, inside }] : [];
    }),
    left: folders
      .filter((folder) => folder.parent === null && !folder.role && folder.account === null)
      .flatMap((root) => [root, ...branch(folders, root.id).map(({ folder }) => folder)]),
  };
}

function destinationName(
  folder: MailFolder,
  folders: MailFolder[],
  t: (key: MessageKey) => string,
): string {
  return folder.role ? folderName(folder, t) : folderPath(folder, folders);
}

/** The folders messages can be moved to, in the order of the side column; the one they are in is
    disabled. */
function MoveTargets({
  folders,
  accounts,
  from,
  onMove,
}: {
  folders: MailFolder[];
  accounts: Account[];
  from: MailList['id'];
  onMove: (folder: number) => void;
}) {
  const { t } = useI18n();
  const item = (folder: MailFolder) => (
    <MenuItem
      key={folder.id}
      icon={folder.role ? ROLES[folder.role] : Folder}
      label={destinationName(folder, folders, t)}
      disabled={folder.id === from}
      onSelect={() => onMove(folder.id)}
    />
  );
  const found = destinations(folders, accounts);
  return (
    <>
      {found.roles.map(item)}
      {found.accounts.map(({ account, inside }) => (
        <MenuSub key={account.id} icon={Mail} label={accountName(account)}>
          {inside.map(item)}
        </MenuSub>
      ))}
      {found.left.map(item)}
    </>
  );
}

/** The order of the folder's list, kept in the browser as a folder of documents keeps its own. */
function SortMenu({
  sort,
  role,
  onSort,
}: {
  sort: MailSort;
  role: Role | '';
  onSort: (sort: MailSort) => void;
}) {
  const { t } = useI18n();
  const named: Record<MailSortKey, [LucideIcon, MessageKey]> = {
    date: [Clock, 'mail.sortDate'],
    correspondent: [
      User,
      role === 'sent' || role === 'drafts' ? 'mail.sortRecipient' : 'mail.sortSender',
    ],
    priority: [CircleAlert, 'mail.sortPriority'],
  };
  const [first, forward, back] = SORT_WAYS[sort.key];
  return (
    <div className="flex justify-end pb-1">
      <Menu
        trigger={
          <button
            type="button"
            title={t('mail.sort')}
            className={`${iconButton} flex items-center gap-1.5 text-sm`}
          >
            <ArrowDownUp size={16} aria-hidden />
            <span className="sr-only">{t('mail.sort')}: </span>
            {t(named[sort.key][1])}, {t(sort.descending === first ? forward : back)}
          </button>
        }
      >
        {MAIL_SORTS.map((key) => (
          <MenuItem
            key={key}
            icon={named[key][0]}
            label={t(named[key][1])}
            checked={sort.key === key}
            onSelect={() => {
              if (sort.key !== key) onSort({ key, descending: SORT_WAYS[key][0] });
            }}
          />
        ))}
        <MenuSeparator />
        <MenuItem
          icon={ArrowDown}
          label={t(forward)}
          checked={sort.descending === first}
          onSelect={() => onSort({ key: sort.key, descending: first })}
        />
        <MenuItem
          icon={ArrowUp}
          label={t(back)}
          checked={sort.descending !== first}
          onSelect={() => onSort({ key: sort.key, descending: !first })}
        />
      </Menu>
    </div>
  );
}

/** The sender's mark of a message as more or less important than most; nothing where it is not. */
function PriorityMark({ priority, spelled }: { priority: 0 | 1 | 2; spelled?: boolean }) {
  const { t } = useI18n();
  if (priority === 1) return null;
  const high = priority === 2;
  const Icon = high ? CircleAlert : ArrowDown;
  const label = t(high ? 'mail.highPriority' : 'mail.lowPriority');
  const tone = high ? 'text-danger' : 'text-muted';
  return spelled ? (
    <span className={`flex items-center gap-1 text-sm ${tone}`}>
      <Icon size={14} aria-hidden />
      {label}
    </span>
  ) : (
    <Icon size={14} role="img" aria-label={label} className={`shrink-0 ${tone}`} />
  );
}

/** How many of the colleagues holding a message the user sent have opened it. */
function OpenedMark({ opened }: { opened: Message['opened'] }) {
  const { t, formatNumber } = useI18n();
  if (!opened?.opened) return null;
  if (opened.opened === opened.held) {
    return (
      <CheckCheck
        size={14}
        role="img"
        aria-label={t('mail.openedAll')}
        className="shrink-0 text-accent"
      />
    );
  }
  return (
    <span className="shrink-0 text-xs tabular-nums text-muted">
      <span className="sr-only">{t('mail.openedBy')}: </span>
      {formatNumber(opened.opened)}/{formatNumber(opened.held)}
    </span>
  );
}

/** Which colleagues opened the message the user sent, and when, opened where asked. */
function OpenedBy({ opened }: { opened: NonNullable<Opened['opened_by']> }) {
  const { t, formatDate, formatNumber } = useI18n();
  const [open, setOpen] = useState(false);
  const count = opened.colleagues.filter((each) => each.opened_at).length;
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="flex flex-col gap-1 text-sm">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 self-start rounded text-muted hover:text-ink"
      >
        <CheckCheck size={14} aria-hidden className={count ? 'text-accent' : undefined} />
        {t('mail.openedBy')}: {formatNumber(count)} {t('mail.of')}{' '}
        {formatNumber(opened.colleagues.length)}
        <Chevron size={14} aria-hidden />
      </button>
      {open && (
        <ul className="flex flex-col gap-0.5 ps-5">
          {opened.colleagues.map(({ user, opened_at }) => (
            <li key={user.id}>
              {user.name} –{' '}
              <span className="text-muted">
                {opened_at ? formatDate(opened_at) : t('mail.notOpened')}
              </span>
            </li>
          ))}
          {opened.outside > 0 && (
            <li className="text-muted">
              {t('mail.outside')}: {formatNumber(opened.outside)}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

/** What can be done to a folder, in its menu over the list and beside it in the side column. */
function FolderActions({ unseen, onAllSeen }: { unseen?: number; onAllSeen: () => void }) {
  const { t } = useI18n();
  const reachable = useReachable();
  return (
    <MenuItem
      icon={MailCheck}
      label={t('mail.allSeen')}
      disabled={unseen === 0 || !reachable}
      onSelect={onAllSeen}
    />
  );
}

function FolderLink({
  folder,
  depth,
  here,
  onAllSeen,
}: {
  folder: MailFolder;
  depth: number;
  here: MailList['id'] | undefined;
  onAllSeen: (folder: MailFolder) => void;
}) {
  const href = useMailHref();
  const { t, formatNumber } = useI18n();
  const Icon = folder.role ? ROLES[folder.role] : Folder;
  const press = useMenuPress();
  return (
    <ContextMenuArea
      items={<FolderActions unseen={folder.unseen} onAllSeen={() => onAllSeen(folder)} />}
    >
      <Link
        {...press}
        to={href(`/mail/${folder.id}`)}
        aria-current={folder.id === here ? 'page' : undefined}
        style={{ paddingLeft: `${0.5 + depth * 0.75}rem` }}
        className={`${sideRow} select-none [-webkit-touch-callout:none]`}
      >
        <Icon size={16} aria-hidden className="shrink-0 text-muted" />
        <span className="min-w-0 flex-1 truncate">{folderName(folder, t)}</span>
        {folder.unseen > 0 && !QUIET.includes(folder.role) && (
          <span className="text-xs tabular-nums">{formatNumber(folder.unseen)}</span>
        )}
      </Link>
    </ContextMenuArea>
  );
}

/** The user's one tree of folders: those with a role first, in the order of a working day, then
    each account's own, then those of accounts since removed. */
function AccountsPanel({
  accounts,
  folders,
  here,
  only,
  onAllSeen,
  onEdit,
  onRename,
  onSign,
  onMove,
  onRemove,
  children,
}: {
  accounts: Account[];
  folders: MailFolder[];
  here: MailList['id'] | undefined;
  /** The account whose mail alone the shared folders show, if the user chose one. */
  only: number | undefined;
  onAllSeen: (folder: MailFolder) => void;
  onEdit: (account: Account) => void;
  onRename: (account: Account) => void;
  onSign: (account: Account) => void;
  onMove: (account: Account) => void;
  onRemove: (account: Account) => void;
  /** What follows the tree: the shared mailboxes. */
  children: ReactNode;
}) {
  const href = useMailHref();
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const press = useMenuPress();
  const reachable = useReachable();
  const [failed, setFailed] = useState<Account | null>(null);
  const shown = useMutation({
    mutationFn: ({ account, change }: { account: Account; change: Partial<Account> }) =>
      patchJson<Account>(`/api/mail/accounts/${account.id}`, change),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['mail'] }),
  });
  const roles = ORDER.flatMap((role) => folders.find((folder) => folder.role === role) ?? []);
  const shared =
    folders.find((folder) => folder.id === here && folder.role) ??
    folders.find((folder) => folder.role === 'inbox');
  const left = folders.filter(
    (folder) => folder.parent === null && !folder.role && folder.account === null,
  );
  return (
    <nav aria-label={t('mail.accounts')} className="flex flex-col gap-3">
      {roles.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {roles.map((folder) => (
            <Fragment key={folder.id}>
              <FolderLink
                folder={folder}
                depth={0}
                here={only ? undefined : here}
                onAllSeen={onAllSeen}
              />
              {folder.role === 'inbox' && (
                <Link
                  to={href('/mail/flagged')}
                  aria-current={here === 'flagged' ? 'page' : undefined}
                  className={sideRow}
                >
                  <Star size={16} aria-hidden className="shrink-0 text-muted" />
                  <span className="min-w-0 flex-1 truncate">{t('favourites.title')}</span>
                </Link>
              )}
              {folder.role === 'inbox' && <LaterLink here={here === 'later'} />}
            </Fragment>
          ))}
        </div>
      )}
      {shown.isError && <p className="px-2 text-xs text-danger">{errorMessage(shown.error, t)}</p>}
      {accounts.map((account) => {
        const node = folders.find((folder) => folder.account === account.id);
        return (
          <section
            key={account.id}
            aria-label={accountName(account)}
            className="flex flex-col gap-0.5"
          >
            <ContextMenuArea
              items={
                <>
                  <MenuItem
                    icon={Pencil}
                    disabled={!reachable}
                    label={t('tree.rename')}
                    onSelect={() => onRename(account)}
                  />
                  <MenuItem
                    icon={Settings}
                    disabled={!reachable}
                    label={t('mail.edit')}
                    onSelect={() => onEdit(account)}
                  />
                  <MenuItem
                    icon={Signature}
                    disabled={!reachable}
                    label={t('mail.signature')}
                    onSelect={() => onSign(account)}
                  />
                  {movesInto(account, accounts).length > 0 && (
                    <MenuItem
                      icon={FolderSymlink}
                      disabled={!reachable}
                      label={t('mail.moveMailItem')}
                      onSelect={() => onMove(account)}
                    />
                  )}
                  <MenuSub icon={Palette} label={t('mail.color')} disabled={!reachable}>
                    {ACCOUNT_COLORS.map(([name], color) => (
                      <MenuItem
                        key={name}
                        icon={Palette}
                        swatch={`var(--account-${color + 1})`}
                        label={t(`mail.color.${name}`)}
                        checked={account.color % ACCOUNT_COLORS.length === color}
                        onSelect={() => shown.mutate({ account, change: { color } })}
                      />
                    ))}
                  </MenuSub>
                  <MenuItem
                    icon={Send}
                    label={t('mail.default')}
                    checked={account.default}
                    disabled={account.default || !reachable}
                    onSelect={() => shown.mutate({ account, change: { default: true } })}
                  />
                  <MenuItem
                    icon={account.together ? Eye : EyeOff}
                    disabled={!reachable}
                    label={t('mail.together')}
                    checked={account.together}
                    onSelect={() =>
                      shown.mutate({ account, change: { together: !account.together } })
                    }
                  />
                  <MenuSeparator />
                  <MenuItem
                    icon={Trash2}
                    disabled={!reachable}
                    label={t('mail.remove')}
                    onSelect={() => onRemove(account)}
                  />
                </>
              }
            >
              <div
                {...press}
                className="flex min-w-0 items-center gap-1 pl-0.5 select-none [-webkit-touch-callout:none]"
              >
                <button
                  type="button"
                  aria-pressed={account.together}
                  aria-label={t('mail.together')}
                  title={t('mail.together')}
                  disabled={shown.isPending || !reachable}
                  onClick={() => shown.mutate({ account, change: { together: !account.together } })}
                  className="flex size-6 shrink-0 items-center justify-center rounded-full hover:bg-hover"
                >
                  <span
                    aria-hidden
                    className={`size-2.5 rounded-full ${account.together ? accountColor(account) : `border-2 ${accountRing(account)}`}`}
                  />
                </button>
                <h2 className="min-w-0 flex-1 text-sm font-semibold">
                  {shared ? (
                    <Link
                      to={href(
                        `/mail/${shared.id}${only === account.id ? '' : `?account=${account.id}`}`,
                      )}
                      aria-current={only === account.id ? 'true' : undefined}
                      className={`flex min-w-0 items-center gap-2 rounded px-1 ${account.together ? '' : 'text-muted'} ${only === account.id ? 'bg-selected' : 'hover:bg-hover'}`}
                    >
                      <span title={account.address} className="min-w-0 flex-1 truncate">
                        {accountName(account)}
                      </span>
                      {!account.together && account.unseen > 0 && (
                        <span className="text-xs font-normal tabular-nums">
                          {formatNumber(account.unseen)}
                        </span>
                      )}
                    </Link>
                  ) : (
                    <span title={account.address} className="block truncate">
                      {accountName(account)}
                    </span>
                  )}
                </h2>
                {account.state === 'failed' && (
                  <button
                    type="button"
                    aria-label={accountError(account, t)}
                    title={accountError(account, t)}
                    onClick={() => setFailed(account)}
                    className="flex size-6 shrink-0 items-center justify-center rounded-full text-danger hover:bg-hover"
                  >
                    <CircleAlert size={16} aria-hidden />
                  </button>
                )}
              </div>
            </ContextMenuArea>
            {(account.state === 'syncing' || (account.state === 'ready' && account.older)) && (
              <p className="px-2 text-xs text-muted">{t('mail.syncing')}</p>
            )}
            {node &&
              branch(folders, node.id).map(({ folder, depth }) => (
                <FolderLink
                  key={folder.id}
                  folder={folder}
                  depth={depth}
                  here={here}
                  onAllSeen={onAllSeen}
                />
              ))}
          </section>
        );
      })}
      {left.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {left
            .flatMap((root) => [{ folder: root, depth: 0 }, ...branch(folders, root.id, 1)])
            .map(({ folder, depth }) => (
              <FolderLink
                key={folder.id}
                folder={folder}
                depth={depth}
                here={here}
                onAllSeen={onAllSeen}
              />
            ))}
        </div>
      )}
      {children}
      {failed && (
        <Modal heading={accountName(failed)} onClose={() => setFailed(null)}>
          <p className="text-sm text-danger">{accountError(failed, t)}</p>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              disabled={!reachable}
              onClick={() => {
                setFailed(null);
                onEdit(failed);
              }}
              className={button}
            >
              {t('mail.edit')}
            </button>
            <Close />
          </div>
        </Modal>
      )}
    </nav>
  );
}

function Messages({
  folder,
  folders,
  accounts,
  only,
  mixed,
  opened,
}: {
  folder: MailList;
  folders: MailFolder[];
  accounts: Account[];
  /** The account whose messages alone the list shows. */
  only?: number;
  /** Whether the folder holds the mail of several accounts, each message naming those it came to. */
  mixed: boolean;
  opened?: number;
}) {
  const href = useMailHref();
  const box = useBox();
  const { t, formatDate, formatNumber } = useI18n();
  const navigate = useNavigate();
  const [choice, setChoice] = useState<Choice>(new Set());
  const [anchor, setAnchor] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [snoozing, setSnoozing] = useState(false);
  const chosen = useChosen();
  const reachable = useReachable();
  const rule = useMessageAction();
  const ai = useAi().data === true;
  const [triaging, setTriaging] = useState(false);
  const [press, pressed] = useLongPress();
  const [sort, setSort] = useState<MailSort>(storedMailSort);
  const sortBy = (next: MailSort) => {
    setSort(next);
    storeMailSort(next);
  };
  const pages = useInfiniteQuery({
    queryKey: listed(folder.id, only, sort, box),
    queryFn: ({ pageParam }) => getJson<Page>(listPath(folder.id, sort, box, only, pageParam)),
    initialPageParam: '',
    getNextPageParam: (last) => last.before ?? undefined,
  });
  if (pages.isPending) return <Loading />;
  if (pages.isError) return <p className="text-danger">{errorMessage(pages.error, t)}</p>;
  const messages = pages.data.pages.flatMap((page) => page.messages);
  if (messages.length === 0) {
    return (
      <p className="text-muted">
        {t(folder.id === 'flagged' ? 'favourites.noMail' : 'mail.empty')}
      </p>
    );
  }
  const byId = new Map(accounts.map((account) => [account.id, account]));
  const { count, unseen } = pages.data.pages[0];
  const ids = messages.map((message) => message.id);
  const picked = (message: Message) =>
    choice instanceof Set
      ? choice.has(message.id)
      : choice === 'all' || message.seen === (choice === 'seen');
  const many =
    choice instanceof Set ? choice.size : { all: count, seen: count - unseen, unseen }[choice];
  const every = choice === 'all' || messages.every(picked);
  const choose = (next: Choice, from: number | null = null) => {
    setChoice(next);
    setAnchor(from);
  };
  const toggle = (id: number, range: boolean) => {
    const next = new Set(messages.filter(picked).map((message) => message.id));
    const on = !next.has(id);
    for (const each of range && anchor !== null ? between(ids, anchor, id) : [id]) {
      if (on) next.add(each);
      else next.delete(each);
    }
    choose(next, id);
  };
  const where: Where = {
    ...(only ? { account: only } : {}),
    ...(choice instanceof Set
      ? { messages: [...choice] }
      : choice === 'all'
        ? {}
        : { seen: choice === 'seen' }),
  };
  const current = messages.find((message) => message.id === opened);
  const back = () => void navigate(href(`/mail/${folder.id}${only ? `?account=${only}` : ''}`));
  const done = (action: Action, to?: number | Role, at?: string) => {
    const leaves = !MARKING.includes(action) && current && picked(current);
    chosen.mutate(
      { folder: folder.id, action, to, at, where },
      {
        onSuccess: () => {
          choose(new Set());
          setConfirming(false);
          setSnoozing(false);
          if (leaves) back();
        },
      },
    );
  };
  const pickedOnes = choice instanceof Set ? messages.filter(picked) : [];
  const senders = pickedOnes.filter((message) => message.sender.address);
  const failure = chosen.error ?? rule.error;
  const block = () => {
    const leaves = current && picked(current) && !UNRULED.includes(folder.role);
    rule.mutate(
      {
        action: 'mail.block',
        messages: senders.map((message) => message.id),
        parameters: { by: 'address' },
      },
      {
        onSuccess: () => {
          choose(new Set());
          if (leaves) back();
        },
      },
    );
  };
  const trash = () => (folder.role === 'trash' ? setConfirming(true) : done('move', 'trash'));
  const kept =
    folder.role === 'trash' &&
    choice instanceof Set &&
    messages.filter(picked).some((each) => each.kept);
  const snoozable = !UNSNOOZABLE.includes(folder.role);
  const junk = folder.role === 'junk';
  const tools: [Action, LucideIcon, MessageKey][] = [
    ['seen', MailOpen, 'mail.markSeen'],
    ['unseen', Mail, 'mail.markUnseen'],
    ['flagged', Star, 'favourites.add'],
    ['unflagged', StarOff, 'favourites.remove'],
  ];
  const halted = chosen.isPending || !reachable;
  const marking: RowAction[] = tools.map(([action, icon, label]) => ({
    icon,
    label: t(label),
    disabled: halted,
    onSelect: () => done(action),
  }));
  const busy = { disabled: halted };
  const sending: RowAction[] = [
    {
      icon: Archive,
      label: t('mail.archive'),
      disabled: halted || folder.role === 'archive',
      onSelect: () => done('move', 'archive'),
    },
    {
      icon: junk ? Inbox : Ban,
      label: t(junk ? 'mail.notJunk' : 'mail.junk'),
      ...busy,
      onSelect: () => done('move', junk ? 'inbox' : 'junk'),
    },
    ...(snoozable
      ? [{ icon: AlarmClock, label: t('mail.snooze'), ...busy, onSelect: () => setSnoozing(true) }]
      : []),
    ...(folder.role === 'snoozed'
      ? [{ icon: Inbox, label: t('mail.unsnooze'), ...busy, onSelect: () => done('unsnooze') }]
      : []),
    ...(senders.length > 0 && !UNREACHED.includes(folder.role)
      ? [
          {
            icon: ShieldBan,
            label: t('mail.blockSenders'),
            disabled: rule.isPending || !reachable,
            onSelect: block,
          },
        ]
      : []),
    ...(pickedOnes.length > 0 && !UNREACHED.includes(folder.role)
      ? [
          {
            icon: FolderTree,
            label: t('mail.triage'),
            disabled: !ai || !reachable || pickedOnes.length > TRIAGED,
            onSelect: () => setTriaging(true),
          },
        ]
      : []),
    {
      icon: Trash2,
      label: t(folder.role === 'trash' ? 'mail.deleteForGood' : 'mail.delete'),
      disabled: halted || kept,
      onSelect: trash,
    },
  ];
  const targets = (
    <MoveTargets
      folders={folders}
      accounts={accounts}
      from={folder.id}
      onMove={(to) => done('move', to)}
    />
  );
  const rowMenu = (
    <>
      <ActionItems actions={marking} />
      <MenuSub icon={FolderInput} label={t('mail.moveTo')} disabled={halted}>
        {targets}
      </MenuSub>
      <ActionItems actions={sending} />
    </>
  );
  return (
    <div
      className="flex flex-col"
      onKeyDown={(event) =>
        choiceKeys(event, many, {
          clear: () => choose(new Set()),
          all: () => choose(new Set(ids)),
          remove: reachable ? trash : undefined,
        })
      }
    >
      {many > 0 && (
        <ChoiceBar
          above={<SortMenu sort={sort} role={folder.role} onSort={sortBy} />}
          all={{
            every,
            many,
            total: count,
            onChange: () => choose(every ? new Set() : new Set(ids)),
            onAll: () => choose('all'),
            onInvert: () =>
              choose(new Set(messages.filter((each) => !picked(each)).map((each) => each.id))),
            onClear: () => choose(new Set()),
          }}
          more={
            <>
              <MenuItem
                icon={MailOpen}
                label={`${t('mail.selectSeen')} (${formatNumber(count - unseen)})`}
                disabled={count === unseen}
                onSelect={() => choose('seen')}
              />
              <MenuItem
                icon={Mail}
                label={`${t('mail.selectUnseen')} (${formatNumber(unseen)})`}
                disabled={unseen === 0}
                onSelect={() => choose('unseen')}
              />
            </>
          }
        >
          <ActionButtons actions={marking} />
          <Menu
            trigger={
              <button
                type="button"
                aria-label={t('mail.moveTo')}
                title={t('mail.moveTo')}
                disabled={halted}
                className={iconButton}
              >
                <FolderInput size={16} aria-hidden />
              </button>
            }
          >
            {targets}
          </Menu>
          <ActionButtons actions={sending} />
        </ChoiceBar>
      )}
      {failure && <p className="mt-2 text-sm text-danger">{errorMessage(failure, t)}</p>}
      {snoozing && (
        <WhenDialog
          heading={t('mail.snoozeAsk')}
          confirmLabel={t('mail.snooze')}
          pending={chosen.isPending}
          error={chosen.error}
          onChoose={(at) => done('snooze', undefined, at.toISOString())}
          onClose={() => setSnoozing(false)}
        />
      )}
      {triaging && (
        <TriageDialog
          messages={pickedOnes}
          nameOf={(to: Destination) => {
            const found = typeof to === 'number' && folders.find((each) => each.id === to);
            return found ? destinationName(found, folders, t) : t(`mail.role.${to as Role}`);
          }}
          onDone={() => {
            setTriaging(false);
            choose(new Set());
          }}
          onClose={() => setTriaging(false)}
        />
      )}
      <ul aria-label={folderName(folder, t)} className="flex flex-col">
        {messages.map((message) => {
          const weight = message.seen ? '' : 'font-semibold';
          const here = message.id === opened;
          const came = message.accounts.flatMap((id) => byId.get(id) ?? []);
          return (
            <ContextMenuArea
              key={message.id}
              items={rowMenu}
              onOpen={(event) => {
                if (!picked(message))
                  steady(event.currentTarget, () => choose(new Set([message.id]), message.id));
              }}
            >
              <li
                data-id={message.id}
                className={`flex min-w-0 items-start rounded-md border-b border-line select-none [-webkit-touch-callout:none] ${here || picked(message) ? 'bg-selected' : 'hover:bg-hover'}`}
              >
                {many > 0 && (
                  <ChoiceBox
                    checked={picked(message)}
                    onToggle={(range) => toggle(message.id, range)}
                    className="mt-3 ml-2"
                  />
                )}
                <Link
                  {...rowOpener(press, pressed, many, (range) => toggle(message.id, range))}
                  to={href(`/mail/${folder.id}/${message.id}${only ? `?account=${only}` : ''}`)}
                  aria-current={here ? 'true' : undefined}
                  className="flex min-w-0 flex-1 gap-2 rounded-md px-2 py-2"
                >
                  {came.length > 0 && (
                    <span
                      aria-hidden
                      className="flex w-1 shrink-0 flex-col overflow-hidden rounded-full"
                    >
                      {came.map((account) => (
                        <span
                          key={account.id}
                          className={`flex-1 ${accountColor(account, message.seen)}`}
                        />
                      ))}
                    </span>
                  )}
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className={`min-w-0 flex-1 truncate ${weight}`}>
                        {!message.seen && <span className="sr-only">{t('mail.unseen')}: </span>}
                        {correspondents(
                          message,
                          folders.find((each) => each.id === message.folder)?.role ?? folder.role,
                        )}
                      </span>
                      {message.unanswered && (
                        <span className="shrink-0 rounded bg-panel px-1.5 text-xs text-muted">
                          {t('mail.unanswered')}
                        </span>
                      )}
                      {message.awaited_until && (
                        <Hourglass
                          size={14}
                          role="img"
                          aria-label={t('mail.await')}
                          className="shrink-0 text-muted"
                        />
                      )}
                      <OpenedMark opened={message.opened} />
                      <PriorityMark priority={message.priority} />
                      {message.sealed === 'encrypted' && (
                        <Lock
                          size={14}
                          role="img"
                          aria-label={t('mail.sealed.encrypted')}
                          className="shrink-0 text-muted"
                        />
                      )}
                      {message.attachments && (
                        <Paperclip
                          size={14}
                          role="img"
                          aria-label={t('mail.attachments')}
                          className="shrink-0 text-muted"
                        />
                      )}
                      {message.flagged && (
                        <Star
                          size={14}
                          role="img"
                          aria-label={t('favourites.title')}
                          className="shrink-0 text-accent"
                        />
                      )}
                      <span className="shrink-0 text-xs text-muted">
                        {formatDate(message.snoozed_until ?? message.date)}
                      </span>
                    </span>
                    <span className={`truncate text-sm ${weight}`}>
                      {message.subject || t('mail.noSubject')}
                    </span>
                    {message.preview && (
                      <span className="truncate text-sm text-muted">{message.preview}</span>
                    )}
                    {mixed && came.length > 0 && (
                      <span className="truncate text-xs text-muted">
                        {came.map(accountName).join(', ')}
                      </span>
                    )}
                  </span>
                </Link>
              </li>
            </ContextMenuArea>
          );
        })}
      </ul>
      {pages.hasNextPage && (
        <button
          type="button"
          disabled={pages.isFetchingNextPage}
          onClick={() => void pages.fetchNextPage()}
          className={`${button} mt-3 self-center`}
        >
          {t('mail.more')}
        </button>
      )}
      {confirming && (
        <ConfirmDialog
          heading={t('mail.deleteChosenTitle')}
          confirmLabel={t('mail.deleteForGood')}
          onConfirm={() => done('delete')}
          onClose={() => setConfirming(false)}
        >
          {t('mail.deleteChosenWarning')}
        </ConfirmDialog>
      )}
    </div>
  );
}

/** Shows the images of a domain's senders without asking, keeps them out without asking, or asks
    again (null); the messages open are read again to show it. */
function useDecide() {
  const queryClient = useQueryClient();
  const box = useBox();
  return useMutation({
    mutationFn: ({ domain, shown }: { domain: string; shown: boolean | null }) =>
      shown === null
        ? deleteJson(inBox(`/api/mail/images/${encodeURIComponent(domain)}`, box))
        : postJson(inBox('/api/mail/images', box), { domain, shown }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ACCOUNTS });
      void queryClient.invalidateQueries({ queryKey: ['mail', 'message'] });
    },
  });
}

function useUnrule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteJson(`/api/mail/rules/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ACCOUNTS }),
  });
}

/** The folders a rule takes no mail out of, so a message open in one stays where it is. */
const UNRULED: MailFolder['role'][] = ['snoozed', 'sent', 'drafts', 'trash', 'junk'];
const UNSNOOZABLE: MailFolder['role'][] = ['sent', 'drafts', 'trash', 'junk'];
const MARKING: Action[] = ['seen', 'unseen', 'flagged', 'unflagged'];
/** The folders no rule sends mail to. */
const UNREACHED: MailFolder['role'][] = ['sent', 'drafts'];

/** Blocks the sender of a message, sending their mail to Junk, or sends it to a folder: by the
    address, or by the domain it is from. */
function RuleDialog({
  message,
  address,
  block,
  folders,
  accounts,
  onDone,
  onClose,
}: {
  message: number;
  address: string;
  block: boolean;
  folders: MailFolder[];
  accounts: Account[];
  onDone: (to: number | 'junk') => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const rule = useMessageAction();
  const domain = address.slice(address.lastIndexOf('@') + 1).toLowerCase();
  const [whole, setWhole] = useState(false);
  const [to, setTo] = useState<number | null>(null);
  const found = destinations(folders, accounts);
  const option = (folder: MailFolder) => (
    <option key={folder.id} value={folder.id}>
      {destinationName(folder, folders, t)}
    </option>
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    const where = block ? 'junk' : to;
    if (where === null) return;
    const by = whole ? 'domain' : 'address';
    rule.mutate(
      block
        ? { action: 'mail.block', messages: [message], parameters: { by } }
        : { action: 'mail.always', messages: [message], parameters: { to: where, by } },
      { onSuccess: () => onDone(where) },
    );
  }

  return (
    <Modal heading={t(block ? 'mail.blockTitle' : 'mail.alwaysTitle')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div role="radiogroup" aria-label={t('mail.from')} className="flex flex-col gap-2">
          {[false, ...(domain.includes('.') ? [true] : [])].map((each) => (
            <label key={String(each)} className="flex min-w-0 items-center gap-2 text-sm">
              <input
                type="radio"
                name="rule-sender"
                checked={whole === each}
                onChange={() => setWhole(each)}
                className="size-4 shrink-0"
              />
              <span className="truncate">
                {each ? `${t('mail.wholeDomain')} ${domain}` : address}
              </span>
            </label>
          ))}
        </div>
        {!block && (
          <Labelled label={t('mail.ruleFolder')}>
            {(id) => (
              <select
                id={id}
                value={to ?? ''}
                required
                onChange={(event) => setTo(Number(event.target.value))}
                className={field}
              >
                <option value="" disabled />
                {found.roles.filter((folder) => !UNREACHED.includes(folder.role)).map(option)}
                {found.accounts.map(({ account, inside }) => (
                  <optgroup key={account.id} label={accountName(account)}>
                    {inside.map(option)}
                  </optgroup>
                ))}
                {found.left.map(option)}
              </select>
            )}
          </Labelled>
        )}
        {rule.isError && <p className="text-sm text-danger">{errorMessage(rule.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="submit"
            disabled={rule.isPending || (!block && to === null)}
            className={primaryButton}
          >
            {t(block ? 'mail.blockConfirm' : 'tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** The user's mail accounts, and the shared mailboxes they reach with the accounts of those they
    own. */
export function MailAccounts() {
  return (
    <>
      <MailAccountList />
      <Mailboxes accounts={() => <MailAccountList />} />
    </>
  );
}

function MailAccountList() {
  const { t } = useI18n();
  const accounts = useAccounts();
  const [connecting, setConnecting] = useState(false);
  if (!accounts.data)
    return accounts.isError ? (
      <p className="text-sm text-danger">{errorMessage(accounts.error, t)}</p>
    ) : (
      <Loading />
    );
  const mine = accounts.data.accounts;
  return (
    <>
      {mine.length === 0 ? (
        <p className="text-sm text-muted">{t('mail.none')}</p>
      ) : (
        <ul aria-label={t('mail.accounts')} className="flex flex-col">
          {mine.map((account) => (
            <li
              key={account.id}
              className="flex min-w-0 items-center gap-2 border-b border-line py-2 pl-2"
            >
              <span
                aria-hidden
                className={`size-2.5 shrink-0 rounded-full ${accountColor(account)}`}
              />
              <span className="min-w-0 flex-1 truncate">{accountName(account)}</span>
              <span
                className={`truncate text-sm ${account.state === 'failed' ? 'text-danger' : 'text-muted'}`}
              >
                {account.state === 'failed' ? accountError(account, t) : account.address}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div>
        <button type="button" onClick={() => setConnecting(true)} className={primaryButton}>
          <MailPlus size={16} aria-hidden />
          {t('mail.connect')}
        </button>
      </div>
      {connecting && <AccountDialog known={accounts.data} onClose={() => setConnecting(false)} />}
    </>
  );
}

export function MailSettings() {
  const { t } = useI18n();
  const accounts = useAccounts();
  const unrule = useUnrule();
  const decide = useDecide();
  if (!accounts.data)
    return accounts.isError ? (
      <p className="text-sm text-danger">{errorMessage(accounts.error, t)}</p>
    ) : (
      <Loading />
    );
  const { rules, images, folders } = accounts.data;
  const failure = unrule.error ?? decide.error;
  const row = 'flex min-w-0 items-center gap-2 border-b border-line py-1 pl-2';
  return (
    <>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      <section aria-label={t('mail.rules')} className="flex flex-col gap-2">
        <h2 className="font-semibold">{t('mail.rules')}</h2>
        {rules.length === 0 ? (
          <p className="text-sm text-muted">{t('mail.rulesNone')}</p>
        ) : (
          <ul aria-label={t('mail.rules')} className="flex flex-col">
            {rules.map((rule) => {
              const folder = folders.find((each) => each.id === rule.folder);
              return (
                <li key={rule.id} className={row}>
                  <span className="min-w-0 flex-1 truncate">{rule.sender}</span>
                  <span className="truncate text-sm text-muted">
                    {folder && destinationName(folder, folders, t)}
                  </span>
                  <RemoveButton
                    label={`${t('mail.unrule')} ${rule.sender}`}
                    disabled={unrule.isPending}
                    onClick={() => unrule.mutate(rule.id)}
                  />
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <section aria-label={t('mail.decidedTitle')} className="flex flex-col gap-2">
        <h2 className="font-semibold">{t('mail.decidedTitle')}</h2>
        {images.length === 0 ? (
          <p className="text-sm text-muted">{t('mail.decidedNone')}</p>
        ) : (
          <ul aria-label={t('mail.decidedTitle')} className="flex flex-col">
            {images.map(({ domain, shown }) => (
              <li key={domain} className={row}>
                <span className="min-w-0 flex-1 truncate">{domain}</span>
                <span className="text-sm text-muted">
                  {t(shown ? 'mail.imagesShown' : 'mail.imagesQuiet')}
                </span>
                <RemoveButton
                  label={`${t('mail.askImages')} ${domain}`}
                  disabled={decide.isPending}
                  onClick={() => decide.mutate({ domain, shown: null })}
                />
              </li>
            ))}
          </ul>
        )}
      </section>
      <MailKeysSection />
    </>
  );
}

/** Sets the message's flags, which stay in PONISTRA, and shows them everywhere it is listed. */
function useFlags(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (flags: Partial<Pick<Message, 'seen' | 'flagged'>>) =>
      patchJson<Message>(`/api/mail/messages/${id}`, flags),
    onSuccess: (changed, flags) => {
      queryClient.setQueriesData<Pages>(
        { queryKey: ['mail', 'messages'] },
        (pages) =>
          pages && {
            ...pages,
            pages: pages.pages.map((page) => ({
              ...page,
              messages: page.messages.map((each) =>
                each.id === changed.id
                  ? { ...each, seen: changed.seen, flagged: changed.flagged }
                  : each,
              ),
            })),
          },
      );
      queryClient.setQueriesData<Opened>(
        { queryKey: ['mail', 'message', id] },
        (shown) => shown && { ...shown, seen: changed.seen, flagged: changed.flagged },
      );
      void queryClient.invalidateQueries({
        queryKey: ['mail', 'messages'],
        refetchType: 'flagged' in flags ? 'active' : 'none',
      });
      void queryClient.invalidateQueries({ queryKey: ACCOUNTS });
    },
  });
}

function Reader({
  folder,
  folders,
  accounts,
  id,
  search,
  onCompose,
}: {
  folder: MailList;
  folders: MailFolder[];
  accounts: Account[];
  id: number;
  /** What of the list's choice going back keeps. */
  search: string;
  onCompose: (way: Way, original: Opened, written?: string) => void;
}) {
  const href = useMailHref();
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [once, setOnce] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [tasking, setTasking] = useState(false);
  const [ruling, setRuling] = useState<'block' | 'folder' | null>(null);
  const [gathering, setGathering] = useState(false);
  const own = useBox() === null;
  const [into, setInto] = useState<string | null>(null);
  const chosen = useChosen();
  const reachable = useReachable();
  const opened = useQuery({
    queryKey: ['mail', 'message', id, once, into],
    queryFn: () => getJson<Opened>(messagePath(id, { images: once, into })),
    staleTime: Infinity,
    placeholderData: keepPreviousData,
    enabled: !chosen.isSuccess,
  });
  const drafts = useDrafts();
  const left = () => {
    queryClient.removeQueries({ queryKey: ['mail', 'message', id] });
    if (window.location.pathname.endsWith(`/${id}`))
      void navigate(href(`/mail/${folder.id}${search}`));
  };
  const moved = (
    action: 'move' | 'delete' | 'snooze' | 'unsnooze',
    to?: number | Role,
    at?: string,
  ) =>
    chosen.mutate(
      { folder: folder.id, action, to, at, where: { messages: [id] } },
      { onSuccess: left },
    );
  const [snoozing, setSnoozing] = useState(false);
  const [awaiting, setAwaiting] = useState(false);
  const flags = useFlags(id);
  const decide = useDecide();
  const react = useMutation({
    mutationFn: (emoji: string) =>
      postJson<{ reactions: Reaction[] }>(`/api/mail/messages/${id}/reaction`, {
        emoji,
        said: t('reactions.said'),
      }),
    onSuccess: ({ reactions }) =>
      queryClient.setQueriesData<Opened>({ queryKey: ['mail', 'message', id] }, (old) =>
        old ? { ...old, reactions } : old,
      ),
  });
  const reacting = useReacting(react.mutate);
  const marked = useRef(false);
  const shown = opened.data;
  const html = useKeptHtml(id, shown?.html ?? null);
  const translation = useMessageTranslation(id, shown, setInto);
  const reading = useAccounts().data?.role === 'read';
  useEffect(() => {
    if (!shown || marked.current || reading || !reachable) return;
    marked.current = true;
    if (!shown.seen) flags.mutate({ seen: true });
  }, [shown, flags, reading, reachable]);
  const trashed = folder.role === 'trash';

  const back = (
    <Link
      to={href(`/mail/${folder.id}${search}`)}
      aria-label={t('mail.back')}
      className={`${iconButton} lg:hidden`}
    >
      <ArrowLeft size={18} aria-hidden />
    </Link>
  );
  if (!shown) {
    return opened.isError ? (
      <div className="flex items-start gap-2">
        {back}
        <p className="text-danger">{errorMessage(opened.error, t)}</p>
      </div>
    ) : (
      <Loading />
    );
  }
  const subject = shown.subject || t('mail.noSubject');
  const people: [MessageKey, Partial<Person>[]][] = [
    ['mail.from', [shown.sender]],
    ['mail.to', shown.to],
    ['mail.cc', shown.cc],
    ['mail.replyTo', shown.reply_to.filter((each) => each.address !== shown.sender.address)],
  ];
  const failure = flags.error ?? chosen.error ?? decide.error ?? react.error;
  const junk = folder.role === 'junk';
  const showing = once || shown.images === true;
  const domain = shown.domain;
  const held = folders.find((each) => each.id === shown.folder)?.role ?? folder.role;
  const ruled = Boolean(shown.sender.address) && !UNREACHED.includes(held);
  const body =
    html !== null ? (
      <HtmlBody
        key={`${showing} ${shown.translated} ${html === shown.html}`}
        title={subject}
        html={html}
      />
    ) : (
      <PlainBody text={shown.text ?? ''} />
    );
  return (
    <article aria-label={subject} className="flex min-w-0 flex-col gap-4">
      {snoozing && (
        <WhenDialog
          heading={t('mail.snoozeAsk')}
          confirmLabel={t('mail.snooze')}
          pending={chosen.isPending}
          error={chosen.error}
          onChoose={(at) => moved('snooze', undefined, at.toISOString())}
          onClose={() => setSnoozing(false)}
        />
      )}
      {awaiting && (
        <WhenDialog
          heading={t('mail.awaitAsk')}
          confirmLabel={t('mail.await')}
          pending={chosen.isPending}
          error={chosen.error}
          onChoose={(at) =>
            chosen.mutate(
              {
                folder: folder.id,
                action: 'await',
                at: at.toISOString(),
                where: { messages: [id] },
              },
              { onSuccess: () => setAwaiting(false) },
            )
          }
          onClose={() => setAwaiting(false)}
        />
      )}
      {shown.snoozed_until && (
        <p className="rounded-lg bg-panel px-3 py-2 text-sm text-muted">
          {t('mail.snoozedUntil').replace('{when}', formatDate(shown.snoozed_until))}
        </p>
      )}
      {shown.awaited_until && (
        <p className="flex flex-wrap items-center gap-2 rounded-lg bg-panel px-3 py-2 text-sm text-muted">
          <span className="flex-1">
            {t('mail.awaitingUntil').replace('{when}', formatDate(shown.awaited_until))}
          </span>
          <button
            type="button"
            disabled={chosen.isPending || !reachable}
            onClick={() =>
              chosen.mutate({ folder: folder.id, action: 'unawait', where: { messages: [id] } })
            }
            className="text-accent hover:underline"
          >
            {t('mail.unawait')}
          </button>
        </p>
      )}
      {shown.unanswered && !shown.awaited_until && (
        <p className="rounded-lg bg-panel px-3 py-2 text-sm text-muted">{t('mail.unanswered')}</p>
      )}
      {tasking && (
        <TaskDialog
          draft={{
            text: subject,
            source: {
              kind: 'mail',
              label: subject,
              link: href(`/mail/${shown.folder}/${shown.id}`),
            },
          }}
          onClose={() => setTasking(false)}
        />
      )}
      {ruling && shown.sender.address && (
        <RuleDialog
          message={shown.id}
          address={shown.sender.address}
          block={ruling === 'block'}
          folders={folders}
          accounts={accounts}
          onDone={(to) => {
            setRuling(null);
            if (!UNRULED.includes(folder.role) && to !== folder.id) left();
          }}
          onClose={() => setRuling(null)}
        />
      )}
      {gathering && (
        <GatherDialog
          messages={[shown.id]}
          onDone={() => setGathering(false)}
          onClose={() => setGathering(false)}
        />
      )}
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-1">
          {back}
          <div className="ml-auto flex items-center gap-1">
            {shown.remote && !showing && shown.images === null && (
              <fieldset disabled={!reachable} className="contents">
                <Menu
                  trigger={
                    <button
                      type="button"
                      aria-label={t('mail.images')}
                      title={t('mail.images')}
                      className={iconButton}
                    >
                      <ImageOff size={18} aria-hidden />
                    </button>
                  }
                >
                  <MenuItem
                    icon={Eye}
                    label={t('mail.showImages')}
                    onSelect={() => setOnce(true)}
                  />
                  {domain && (
                    <>
                      <MenuItem
                        icon={Images}
                        label={`${t('mail.alwaysImages')} ${domain}`}
                        disabled={decide.isPending}
                        onSelect={() => decide.mutate({ domain, shown: true })}
                      />
                      <MenuItem
                        icon={ImageOff}
                        label={`${t('mail.quietImages')} ${domain}`}
                        disabled={decide.isPending}
                        onSelect={() => decide.mutate({ domain, shown: false })}
                      />
                    </>
                  )}
                </Menu>
              </fieldset>
            )}
            {(
              [
                ['reply', Reply, 'mail.reply'],
                ['all', ReplyAll, 'mail.replyAll'],
                ['forward', Forward, 'mail.forward'],
              ] as const
            ).map(([way, Icon, label]) => (
              <button
                key={way}
                type="button"
                aria-label={t(label)}
                title={t(label)}
                onClick={() => onCompose(way, withUnsealed(queryClient, shown))}
                className={iconButton}
              >
                <Icon size={18} aria-hidden />
              </button>
            ))}
            <fieldset disabled={!reachable} className="contents">
              {shown.reactable && (
                <Menu
                  trigger={
                    <button
                      type="button"
                      aria-label={t('reactions.react')}
                      title={t('reactions.react')}
                      disabled={react.isPending}
                      className={iconButton}
                    >
                      <SmilePlus size={18} aria-hidden />
                    </button>
                  }
                >
                  {reacting.items}
                </Menu>
              )}
              <button
                type="button"
                aria-label={t('tasks.fromMail')}
                title={t('tasks.fromMail')}
                onClick={() => setTasking(true)}
                className={iconButton}
              >
                <ListTodo size={18} aria-hidden />
              </button>
              <button
                type="button"
                aria-pressed={shown.flagged}
                aria-label={t(shown.flagged ? 'favourites.remove' : 'favourites.add')}
                title={t(shown.flagged ? 'favourites.remove' : 'favourites.add')}
                disabled={flags.isPending}
                onClick={() => flags.mutate({ flagged: !shown.flagged })}
                className={iconButton}
              >
                <Star
                  size={18}
                  aria-hidden
                  className={shown.flagged ? 'fill-current text-accent' : ''}
                />
              </button>
              {(held === 'sent' || shown.unanswered) && !shown.awaited_until && (
                <button
                  type="button"
                  aria-label={t('mail.await')}
                  title={t('mail.await')}
                  disabled={chosen.isPending}
                  onClick={() => setAwaiting(true)}
                  className={iconButton}
                >
                  <Hourglass size={18} aria-hidden />
                </button>
              )}
              {!UNSNOOZABLE.includes(held) && (
                <button
                  type="button"
                  aria-label={t('mail.snooze')}
                  title={t('mail.snooze')}
                  disabled={chosen.isPending}
                  onClick={() => setSnoozing(true)}
                  className={iconButton}
                >
                  <AlarmClock size={18} aria-hidden />
                </button>
              )}
              {held === 'snoozed' && (
                <button
                  type="button"
                  aria-label={t('mail.unsnooze')}
                  title={t('mail.unsnooze')}
                  disabled={chosen.isPending}
                  onClick={() => moved('unsnooze')}
                  className={iconButton}
                >
                  <Inbox size={18} aria-hidden />
                </button>
              )}
              <button
                type="button"
                aria-label={t('mail.archive')}
                title={t('mail.archive')}
                disabled={chosen.isPending || folder.role === 'archive'}
                onClick={() => moved('move', 'archive')}
                className={iconButton}
              >
                <Archive size={18} aria-hidden />
              </button>
              {ruled && shown.bulk && (
                <button
                  type="button"
                  aria-label={t('mail.block')}
                  title={t('mail.block')}
                  onClick={() => setRuling('block')}
                  className={iconButton}
                >
                  <ShieldBan size={18} aria-hidden />
                </button>
              )}
              <button
                type="button"
                aria-label={t(trashed ? 'mail.deleteForGood' : 'mail.delete')}
                title={t(trashed ? 'mail.deleteForGood' : 'mail.delete')}
                disabled={chosen.isPending || (trashed && shown.kept)}
                onClick={() => (trashed ? setConfirming(true) : moved('move', 'trash'))}
                className={iconButton}
              >
                <Trash2 size={18} aria-hidden />
              </button>
              <ActionsMenu>
                <MenuItem
                  icon={shown.seen ? Mail : MailOpen}
                  label={t(shown.seen ? 'mail.markUnseen' : 'mail.markSeen')}
                  disabled={flags.isPending}
                  onSelect={() => flags.mutate({ seen: !shown.seen })}
                />
                <MenuSub icon={FolderInput} label={t('mail.moveTo')} disabled={chosen.isPending}>
                  <MoveTargets
                    folders={folders}
                    accounts={accounts}
                    from={shown.folder}
                    onMove={(to) => moved('move', to)}
                  />
                </MenuSub>
                <MenuItem
                  icon={junk ? Inbox : Ban}
                  label={t(junk ? 'mail.notJunk' : 'mail.junk')}
                  disabled={chosen.isPending}
                  onSelect={() => moved('move', junk ? 'inbox' : 'junk')}
                />
                {ruled && !shown.bulk && (
                  <MenuItem
                    icon={ShieldBan}
                    label={t('mail.block')}
                    onSelect={() => setRuling('block')}
                  />
                )}
                {ruled && (
                  <MenuItem
                    icon={FolderSymlink}
                    label={t('mail.always')}
                    onSelect={() => setRuling('folder')}
                  />
                )}
                {own && (
                  <MenuItem
                    icon={Receipt}
                    label={t('collections.add')}
                    onSelect={() => setGathering(true)}
                  />
                )}
                {translation.offered && (
                  <MenuItem
                    icon={Languages}
                    label={t('translation.translate')}
                    onSelect={translation.translate}
                  />
                )}
                <MenuItem
                  icon={FileDown}
                  label={t('mail.original')}
                  onSelect={() => location.assign(`/api/mail/messages/${id}/original`)}
                />
                {shown.remote && !showing && shown.images === false && (
                  <MenuItem
                    icon={Eye}
                    label={t('mail.showImages')}
                    onSelect={() => setOnce(true)}
                  />
                )}
                {shown.images !== null && domain && (
                  <MenuItem
                    icon={RotateCcw}
                    label={`${t('mail.askImages')} ${domain}`}
                    disabled={decide.isPending}
                    onSelect={() => decide.mutate({ domain, shown: null })}
                  />
                )}
              </ActionsMenu>
            </fieldset>
          </div>
        </div>
        <h1 className="text-lg font-semibold break-words">{subject}</h1>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 text-sm">
          {people
            .filter(([, found]) => found.some((each) => each.address || each.name))
            .map(([label, found]) => (
              <div key={label} className="contents">
                <dt className="text-muted">{t(label)}</dt>
                <dd className="break-words">{found.map(fullPerson).join(', ')}</dd>
              </div>
            ))}
        </dl>
        <div className="flex flex-wrap items-center gap-x-3">
          <time dateTime={shown.date} className="text-sm text-muted">
            {formatDate(shown.date)}
          </time>
          <PriorityMark priority={shown.priority} spelled />
        </div>
        {shown.opened_by && <OpenedBy opened={shown.opened_by} />}
        <Reactions
          reactions={shown.reactions}
          onGive={react.mutate}
          disabled={react.isPending || !shown.reactable || !reachable}
        />
      </header>
      {reacting.dialog}
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {translation.bar}
      {shown.invitation && <InvitationCard invitation={shown.invitation} message={id} />}
      {drafts.data
        ?.filter((draft) => draft.message.id === id)
        .map((draft) => (
          <DraftCard
            key={draft.id}
            draft={draft}
            onOpen={() => onCompose(draft.way, withUnsealed(queryClient, shown), draft.text)}
          />
        ))}
      {shown.attachments.length > 0 && <Attachments message={shown} />}
      {shown.sealed ? (
        <SealedBody key={shown.id} message={shown} title={subject}>
          {body}
        </SealedBody>
      ) : (
        body
      )}
      {confirming && (
        <ConfirmDialog
          heading={t('mail.deleteTitle')}
          confirmLabel={t('mail.deleteForGood')}
          onConfirm={() => moved('delete')}
          onClose={() => setConfirming(false)}
        >
          {t('mail.deleteWarning')}
        </ConfirmDialog>
      )}
    </article>
  );
}

const INVITATION_ICONS: Record<Invitation['method'], LucideIcon> = {
  request: CalendarDays,
  cancel: CalendarX,
  reply: CalendarCheck,
  counter: CalendarDays,
};

const WAY_LABELS = { reply: 'mail.reply', all: 'mail.replyAll', forward: 'mail.forward' } as const;

/** A reply an outside agent drafted: read here, sent only by the user's hand. */
function DraftCard({ draft, onOpen }: { draft: Draft; onOpen: () => void }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const drop = useMutation({
    mutationFn: () => deleteJson(`/api/mail/drafts/${draft.id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DRAFTS }),
  });
  return (
    <section
      aria-label={t('mail.draft')}
      className="flex flex-col gap-2 rounded-lg bg-panel px-3 py-2 text-sm"
    >
      <p className="flex flex-wrap items-center gap-x-2 text-muted">
        <Bot size={14} aria-hidden />
        <span>{draft.by ? t('mail.draftBy').replace('{by}', draft.by) : t('mail.draft')}</span>
        <time dateTime={draft.created_at}>{formatDate(draft.created_at)}</time>
      </p>
      <p className="whitespace-pre-line">{draft.text}</p>
      {drop.isError && <p className="text-danger">{errorMessage(drop.error, t)}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onOpen} className={primaryButton}>
          {t(WAY_LABELS[draft.way])}
        </button>
        <button
          type="button"
          disabled={drop.isPending}
          onClick={() => drop.mutate()}
          className={button}
        >
          {t('mail.dropDraft')}
        </button>
      </div>
    </section>
  );
}

/** The messages the user began in Ponistra and has not sent, shown over the Drafts folder, each
 * opening in the composer as they left it. */
function UnsentList({ onOpen }: { onOpen: (unsent: Unsent) => void }) {
  const { t, formatDate } = useI18n();
  const unsent = useUnsent();
  if (!unsent.data?.length) return null;
  return (
    <section aria-label={t('mail.unsentTitle')} className="mb-2 flex flex-col">
      <h2 className="px-2 py-1 text-sm text-muted">{t('mail.unsentTitle')}</h2>
      <ul className="flex flex-col">
        {unsent.data.map((each) => (
          <li key={each.id} className="rounded-md border-b border-line hover:bg-hover">
            <button
              type="button"
              onClick={() => onOpen(each)}
              className="flex w-full min-w-0 flex-col gap-0.5 px-2 py-2 text-left"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="min-w-0 flex-1 truncate">
                  {[...each.to, ...each.cc].map(person).join(', ') || t('mail.noRecipients')}
                </span>
                <span className="shrink-0 text-xs text-muted">{formatDate(each.updated_at)}</span>
              </span>
              <span className="truncate text-sm">{each.subject || t('mail.noSubject')}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The drafts waiting for the user, shown over the Drafts folder, each opening its message. */
function WaitingDrafts() {
  const href = useMailHref();
  const { t, formatDate } = useI18n();
  const drafts = useDrafts();
  if (!drafts.data?.length) return null;
  return (
    <section aria-label={t('mail.waitingDrafts')} className="mb-2 flex flex-col">
      <h2 className="px-2 py-1 text-sm text-muted">{t('mail.waitingDrafts')}</h2>
      <ul className="flex flex-col">
        {drafts.data.map((draft) => (
          <li key={draft.id} className="rounded-md border-b border-line hover:bg-hover">
            <Link
              to={href(`/mail/${draft.message.folder}/${draft.message.id}`)}
              className="flex min-w-0 flex-col gap-0.5 px-2 py-2"
            >
              <span className="flex min-w-0 items-center gap-2">
                <Bot size={14} aria-hidden className="shrink-0 text-muted" />
                <span className="min-w-0 flex-1 truncate">
                  {draft.message.sender.name || draft.message.sender.address}
                </span>
                <span className="shrink-0 text-xs text-muted">{formatDate(draft.created_at)}</span>
              </span>
              <span className="truncate text-sm">{draft.message.subject}</span>
              <span className="truncate text-sm text-muted">
                {draft.by ? t('mail.draftBy').replace('{by}', draft.by) : t('mail.draft')}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function InvitationCard({ invitation, message }: { invitation: Invitation; message: number }) {
  const { t, language, formatDate, formatDays, formatTime } = useI18n();
  const queryClient = useQueryClient();
  const reachable = useReachable();
  const answer = useMutation({
    mutationFn: (response: Parameters<typeof respond>[1]) =>
      respond(invitation.held!.id, response, language),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['mail', 'message', message] });
      void queryClient.invalidateQueries({ queryKey: CALENDAR });
    },
  });
  const { event, held, attendee } = invitation;
  const Icon = INVITATION_ICONS[invitation.method];
  const sameDay = event.start.slice(0, 10) === event.end.slice(0, 10);
  const when = event.all_day
    ? formatDays(event.start, event.end)
    : sameDay
      ? `${formatDate(event.start)} – ${formatTime(new Date(event.end))}`
      : `${formatDate(event.start)} – ${formatDate(event.end)}`;
  const organizer = 'email' in event.organizer ? event.organizer.name || event.organizer.email : '';
  const answering = invitation.method === 'request' && held && !held.outdated;
  const cancelled = invitation.method === 'cancel' || event.status === 'cancelled';
  return (
    <section
      aria-label={t(`mail.invitation.${invitation.method}`)}
      className="flex flex-col gap-2 rounded-lg bg-panel px-3 py-2 text-sm"
    >
      <div className="flex items-center gap-2">
        <Icon size={18} aria-hidden className="shrink-0 text-muted" />
        <span className="font-semibold">{t(`mail.invitation.${invitation.method}`)}</span>
        {held && (
          <Link
            to={`/calendar/day/${held.day}`}
            className="ml-auto flex items-center gap-0.5 text-link hover:underline"
          >
            {t('mail.invitation.open')}
            <ChevronRight size={16} aria-hidden />
          </Link>
        )}
      </div>
      <div className="flex flex-col gap-0.5">
        <span className={`font-medium ${cancelled ? 'line-through' : ''}`}>
          {event.summary || '—'}
        </span>
        <span className="text-muted">{when}</span>
        {event.location && <span className="text-muted">{event.location}</span>}
        {organizer && (
          <span className="text-muted">
            {t('calendar.organizer')}: {organizer}
          </span>
        )}
        {'email' in attendee && (
          <span>
            {attendee.name || attendee.email}: {t(`calendar.status.${statusKey(attendee.status)}`)}
          </span>
        )}
      </div>
      {held?.outdated && <span className="text-muted">{t('mail.invitation.outdated')}</span>}
      {invitation.method === 'request' && !held && (
        <span className="text-muted">{t('mail.invitation.notHeld')}</span>
      )}
      {answering && held.response !== 'organizer' && (
        <ResponseButtons
          current={held.response}
          disabled={answer.isPending || !reachable}
          onPick={(response) => answer.mutate(response)}
        />
      )}
      {answer.isError && <p className="text-sm text-danger">{errorMessage(answer.error, t)}</p>}
    </section>
  );
}

function statusKey(status: string): 'accepted' | 'declined' | 'tentative' | 'needsAction' {
  if (status === 'accepted' || status === 'declined' || status === 'tentative') return status;
  return 'needsAction';
}

const PART = /\/api\/mail\/messages\/\d+\/parts\/[\w.-]+/g;

function asData(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

/** The message's HTML with the images it carries read from the device, while the server cannot
 * be reached (D45); the frame it is shown in takes no other address. */
function useKeptHtml(id: number, html: string | null): string | null {
  const reachable = useReachable();
  const kept = useQuery({
    queryKey: ['offline', 'html', id, html],
    queryFn: async () => {
      const found = new Map<string, string>();
      for (const path of new Set(html!.match(PART) ?? [])) {
        const blob = await keptPart(path);
        if (blob) found.set(path, await asData(blob));
      }
      return html!.replace(PART, (path) => found.get(path) ?? path);
    },
    enabled: !reachable && html !== null && html.search(PART) !== -1,
    staleTime: Infinity,
  });
  return (!reachable && kept.data) || html;
}

/** Where the file a message carries is read: the server, or what the device kept of it while the
 * server cannot be reached; none where it kept nothing. */
function useKeptFile(path: string): string | null {
  const reachable = useReachable();
  const kept = useQuery({
    queryKey: ['offline', 'part', path],
    queryFn: () => keptPart(path),
    enabled: !reachable,
  });
  const address = useMemo(() => kept.data && URL.createObjectURL(kept.data), [kept.data]);
  useEffect(() => () => void (address && URL.revokeObjectURL(address)), [address]);
  return reachable ? path : address || null;
}

function AttachmentLink({ message, attachment }: { message: number; attachment: Attachment }) {
  const { t } = useI18n();
  const address = useKeptFile(`/api/mail/messages/${message}/parts/${attachment.part}`);
  const name = attachment.name || t('mail.download');
  if (!address) return <span className="min-w-0 truncate text-muted">{name}</span>;
  return (
    <a
      href={address}
      download={attachment.name || true}
      title={t('mail.download')}
      className="min-w-0 truncate hover:underline"
    >
      {name}
    </a>
  );
}

function Attachments({ message }: { message: Opened }) {
  const { t, formatNumber } = useI18n();
  const navigate = useNavigate();
  const reachable = useReachable();
  const keep = useTreeChange(async (attachment: Attachment) => {
    const stored = await postJson<{ sha256: string; media_type: string }>(
      `/api/mail/messages/${message.id}/parts/${attachment.part}/blob`,
      {},
    );
    return placed(stored, attachment.name, null);
  });
  return (
    <div className="flex flex-col gap-2">
      <ul aria-label={t('mail.files')} className="flex flex-wrap gap-2">
        {message.attachments.map((attachment) => (
          <li
            key={attachment.part}
            className="flex min-w-0 max-w-full items-center gap-2 rounded-lg border border-line py-1 pr-1 pl-2 text-sm"
          >
            <Paperclip size={14} aria-hidden className="shrink-0 text-muted" />
            <AttachmentLink message={message.id} attachment={attachment} />
            <span className="shrink-0 text-xs text-muted">
              {formatSize(attachment.size, formatNumber)}
            </span>
            <button
              type="button"
              aria-label={`${t('mail.toDocuments')}: ${attachment.name}`}
              title={t('mail.toDocuments')}
              disabled={keep.isPending || !reachable}
              onClick={() =>
                keep.mutate(attachment, {
                  onSuccess: ({ node, unimported }) => {
                    if (!unimported) void navigate(nodeHref(node));
                  },
                })
              }
              className={iconButton}
            >
              <FilePlus size={16} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      {keep.isError && <p className="text-sm text-danger">{errorMessage(keep.error, t)}</p>}
      {keep.data?.unimported && (
        <p className="text-sm text-danger">
          {t('upload.unimported')}{' '}
          <Link to={nodeHref(keep.data.node)} className="underline">
            {keep.data.node.title}
          </Link>{' '}
          ({errorMessage(keep.data.unimported, t)})
        </p>
      )}
    </div>
  );
}

/** Where the user's mail is not there to list yet: no account, or none of its mail taken so far. */
function Waiting({ accounts, onConnect }: { accounts: Account[]; onConnect: () => void }) {
  const { t } = useI18n();
  if (accounts.length === 0) {
    return (
      <div className="flex w-full max-w-xl flex-col items-start gap-3">
        <p>{t('mail.none')}</p>
        <p className="text-sm text-muted">{t('mail.connectNote')}</p>
        <button type="button" onClick={onConnect} className={primaryButton}>
          <MailPlus size={16} aria-hidden />
          {t('mail.connect')}
        </button>
      </div>
    );
  }
  const failed = accounts.every((account) => account.state === 'failed');
  return (
    <p className={failed ? 'text-danger' : 'text-muted'}>
      {failed ? accountError(accounts[0], t) : t('mail.firstSync')}
    </p>
  );
}

/** A place in the mail page, in the shared mailbox it shows. */
function useMailHref() {
  const box = useBox();
  return (path: string) => inBox(path, box);
}

export function MailPage() {
  const [search] = useSearchParams();
  const box = Number(search.get('box')) || null;
  return (
    <BoxContext key={box ?? 0} value={box}>
      <MailShown />
    </BoxContext>
  );
}

function MailShown() {
  const { t } = useI18n();
  const href = useMailHref();
  const box = useBox();
  const queryClient = useQueryClient();
  const params = useParams();
  const [search, setSearch] = useSearchParams();
  const accounts = useAccounts();
  const [list, setList, listStyle] = useWidth(MESSAGES);
  const [dialog, setDialog] = useState<
    | { type: 'connect'; returned?: string }
    | { type: 'edit' | 'rename' | 'sign' | 'move' | 'remove'; account: Account }
    | { type: 'compose'; start: Start }
    | null
  >(() => {
    const returned = search.get('oauth');
    return returned ? { type: 'connect', returned } : null;
  });
  useEffect(() => {
    if (!search.has('oauth')) return;
    setSearch(
      (now) => {
        now.delete('oauth');
        return now;
      },
      { replace: true },
    );
  }, [search, setSearch]);
  useEffect(() => {
    const to = search.getAll('to');
    const link = search.get('mailto');
    if ((to.length === 0 && !search.has('compose') && link === null) || !accounts.data) return;
    const { accounts: mine } = accounts.data;
    const sender = mine.find((account) => account.default) ?? mine[0];
    if (sender) {
      const names = search.getAll('name');
      const asked = mailto(link ?? '');
      setDialog({
        type: 'compose',
        start: {
          account: sender.id,
          to: [...to.map((address, at) => ({ name: names[at] ?? '', address })), ...asked.to],
          cc: asked.cc,
          bcc: asked.bcc,
          subject: asked.subject,
          text: asked.text,
        },
      });
    }
    setSearch(
      (now) => {
        now.delete('to');
        now.delete('name');
        now.delete('compose');
        now.delete('mailto');
        return now;
      },
      { replace: true },
    );
  }, [search, setSearch, accounts.data]);
  const close = () => setDialog(null);
  const remove = useMutation({
    mutationFn: (account: Account) => deleteJson(`/api/mail/accounts/${account.id}`),
    onSuccess: () => {
      close();
      void queryClient.invalidateQueries({ queryKey: ACCOUNTS });
    },
  });
  const allSeen = useChosen();

  if (accounts.isPending || accounts.isError) {
    return (
      <Frame title={t('rail.mail')} folders={false}>
        {accounts.isError ? (
          <p className="text-danger">{errorMessage(accounts.error, t)}</p>
        ) : (
          <Loading />
        )}
      </Frame>
    );
  }
  const { accounts: mine, folders, mailboxes } = accounts.data;
  const reading = accounts.data.role === 'read';
  const here =
    params.folder === 'flagged' || params.folder === 'later'
      ? params.folder
      : params.folder
        ? Number(params.folder)
        : undefined;
  const opened = params.message ? Number(params.message) : undefined;
  const folder: MailList | undefined =
    here === 'flagged' || here === 'later'
      ? {
          id: here,
          name: t(here === 'later' ? 'mail.laterTitle' : 'favourites.title'),
          role: '',
          parent: null,
          account: null,
          unseen: 0,
          count: 0,
        }
      : folders.find((each) => each.id === here);
  const idle = mine.length === 0 && !folders.some((each) => each.count > 0);
  const start =
    here === undefined && !idle
      ? (folders.find((each) => each.role === 'inbox') ?? folders.find((each) => each.count > 0))
      : undefined;
  const asked = search.get('account');
  const alone = folder?.role ? mine.find((account) => String(account.id) === asked) : undefined;
  // Rendered inside the frame: one in its place would unmount an open dialog while its state stays.
  const redirect =
    here !== undefined && (!folder || idle)
      ? href('/mail')
      : start
        ? { pathname: `/mail/${start.id}`, search: `?${search}` }
        : folder && asked !== null && !alone
          ? href(`/mail/${folder.id}${opened ? `/${opened}` : ''}`)
          : undefined;
  const only = alone?.id;
  const kept = only ? `?account=${only}` : '';
  const own = folder && (accountOf(folder, folders) ?? only ?? null);
  const sender =
    mine.find((account) => account.id === own) ??
    mine.find((account) => account.default) ??
    mine[0];
  const mixed = mine.length > 1 && own === null;
  const syncing = mixed ? mine.filter((account) => account.state === 'syncing') : [];

  return (
    <Frame
      title={folder ? folderName(folder, t) : t('rail.mail')}
      primary={
        sender &&
        !reading && (
          <PrimaryAction
            icon={SquarePen}
            label={t('mail.compose')}
            onClick={() => setDialog({ type: 'compose', start: { account: sender.id } })}
          />
        )
      }
      more={
        folder &&
        here !== 'later' &&
        !reading && (
          <FolderActions
            unseen={only ? undefined : folder.unseen}
            onAllSeen={() =>
              allSeen.mutate({
                folder: folder.id,
                action: 'seen',
                where: { seen: false, ...(only ? { account: only } : {}) },
              })
            }
          />
        )
      }
      folders={false}
      side={
        <AccountsPanel
          accounts={mine}
          folders={folders}
          here={here}
          only={only}
          onAllSeen={(each) =>
            allSeen.mutate({ folder: each.id, action: 'seen', where: { seen: false } })
          }
          onEdit={(account) => setDialog({ type: 'edit', account })}
          onRename={(account) => setDialog({ type: 'rename', account })}
          onSign={(account) => setDialog({ type: 'sign', account })}
          onMove={(account) => setDialog({ type: 'move', account })}
          onRemove={(account) => setDialog({ type: 'remove', account })}
        >
          <MailboxLinks mailboxes={mailboxes} box={box} />
        </AccountsPanel>
      }
    >
      {folder ? (
        <div style={listStyle} className="flex h-full min-h-0">
          <div
            className={`relative min-w-0 flex-1 overflow-y-auto lg:w-(--messages) lg:max-w-[calc(100%-20rem)] lg:flex-none ${opened ? 'hidden lg:block' : ''}`}
          >
            {allSeen.isError && (
              <p className="mb-2 text-sm text-danger">{errorMessage(allSeen.error, t)}</p>
            )}
            {alone && (
              <p className="mb-2 flex items-center gap-2 rounded-lg bg-panel py-1 pr-1 pl-3 text-sm">
                <span
                  aria-hidden
                  className={`size-2.5 shrink-0 rounded-full ${accountColor(alone)}`}
                />
                <span title={alone.address} className="min-w-0 flex-1 truncate">
                  {accountName(alone)}
                </span>
                <Link
                  to={href(`/mail/${folder.id}`)}
                  aria-label={t('mail.allAccounts')}
                  title={t('mail.allAccounts')}
                  className={iconButton}
                >
                  <X size={16} aria-hidden />
                </Link>
              </p>
            )}
            {syncing.map((account) => (
              <p key={account.id} className="mb-2 rounded-lg bg-panel px-3 py-2 text-sm text-muted">
                {accountName(account)}: {t('mail.syncing')}
              </p>
            ))}
            {folder.role === 'drafts' && (
              <UnsentList onOpen={(unsent) => setDialog({ type: 'compose', start: { unsent } })} />
            )}
            {folder.role === 'drafts' && <WaitingDrafts />}
            {here === 'later' ? (
              <LaterList onEdit={(unsent) => setDialog({ type: 'compose', start: { unsent } })} />
            ) : (
              <Messages
                key={`${folder.id}${kept}`}
                folder={folder}
                folders={folders}
                accounts={mine}
                only={only}
                mixed={mixed}
                opened={opened}
              />
            )}
          </div>
          <Splitter
            column={MESSAGES}
            width={list}
            onWidth={setList}
            className="hidden w-6 lg:flex"
          />
          {opened ? (
            <div className="min-w-0 flex-1 overflow-y-auto">
              <Reader
                key={opened}
                folder={folder}
                folders={folders}
                accounts={mine}
                id={opened}
                search={kept}
                onCompose={(way, original, written) =>
                  setDialog({ type: 'compose', start: { way, original, written } })
                }
              />
            </div>
          ) : (
            <p className="hidden flex-1 text-muted lg:block">{t('mail.choose')}</p>
          )}
        </div>
      ) : (
        <Waiting accounts={mine} onConnect={() => setDialog({ type: 'connect' })} />
      )}
      {redirect && <Navigate to={redirect} replace />}
      {remove.isError && <p className="text-sm text-danger">{errorMessage(remove.error, t)}</p>}
      {dialog?.type === 'connect' && (
        <AccountDialog known={accounts.data} returned={dialog.returned} onClose={close} />
      )}
      {dialog?.type === 'edit' &&
        (dialog.account.login === 'password' ? (
          <AccountDialog
            key={dialog.account.id}
            account={dialog.account}
            known={accounts.data}
            onClose={close}
          />
        ) : (
          <OAuthAccountDialog
            key={dialog.account.id}
            account={dialog.account}
            provider={dialog.account.login}
            onClose={close}
          />
        ))}
      {dialog?.type === 'rename' && (
        <NameDialog
          heading={t('tree.rename')}
          submitLabel={t('tree.save')}
          initial={accountName(dialog.account)}
          onSubmit={(label) => patchJson(`/api/mail/accounts/${dialog.account.id}`, { label })}
          onDone={() => {
            close();
            void queryClient.invalidateQueries({ queryKey: ['mail'] });
            void queryClient.invalidateQueries({ queryKey: CALENDAR });
            void queryClient.invalidateQueries({ queryKey: ['contacts'] });
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'sign' && <SignatureDialog account={dialog.account} onClose={close} />}
      {dialog?.type === 'move' && (
        <MoveMailDialog account={dialog.account} accounts={mine} onClose={close} />
      )}
      {dialog?.type === 'remove' && (
        <ConfirmDialog
          heading={t('mail.removeTitle')}
          confirmLabel={t('mail.remove')}
          onConfirm={() => remove.mutate(dialog.account)}
          onClose={close}
        >
          <strong>{accountName(dialog.account)}</strong> {t('mail.removeWarning')}
        </ConfirmDialog>
      )}
      {dialog?.type === 'compose' && (
        <Compose accounts={mine} start={dialog.start} onClose={close} />
      )}
    </Frame>
  );
}
