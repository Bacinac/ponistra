import { useQuery } from '@tanstack/react-query';
import { createContext, useContext } from 'react';
import { getJson } from './api';
import { ZONE } from './calendarData';

export type Security = 'tls' | 'starttls' | 'none';
export type Provider = 'google' | 'microsoft';
export type Protocol = (typeof PROTOCOLS)[number];
export type Role = 'inbox' | 'snoozed' | 'drafts' | 'sent' | 'archive' | 'junk' | 'trash';

export interface Server {
  host: string;
  port: number;
  security: Security;
}

/** A folder of the user's one tree: one with a role holds that mail of every account, the one an
    account names holds that account's other folders. */
export interface MailFolder {
  id: number;
  name: string;
  role: Role | '';
  parent: number | null;
  /** The account whose folders it holds; none once the account is removed. */
  account: number | null;
  unseen: number;
  count: number;
}

export interface Account {
  id: number;
  address: string;
  name: string;
  /** What the interface calls it in place of its address; empty where the user gave none. */
  label: string;
  /** HTML the composer puts under what the user writes from it; empty where there is none. */
  signature: string;
  /** Whether that signature is the account's own rather than the one every account takes. */
  own_signature: boolean;
  username: string;
  /** How it signs in: with its password, or through OAuth at the provider. */
  login: 'password' | Provider;
  protocol: Protocol;
  activesync: { host: string };
  /** Empty, with no port, on an ActiveSync account. */
  imap: Server;
  smtp: Server;
  /** The account's place among the account colours, wrapping past their end. */
  color: number;
  /** Whether a new message goes from it unless the user picks another. */
  default: boolean;
  /** Whether its mail shows in the folders every account shares. */
  together: boolean;
  /** Its unread messages in Inbox. */
  unseen: number;
  state: 'syncing' | 'ready' | 'failed';
  error: string;
  synced_at: string | null;
  /** Whether mail the account held before it was connected is still being taken. */
  older: boolean;
}

/** A shared mailbox the user reaches (S3-6): its own accounts and mail, shared through grants. */
export interface Mailbox {
  id: number;
  name: string;
  role: 'read' | 'edit' | 'own';
  unseen: number;
}

export interface Accounts {
  /** The shared mailboxes the user reaches, whichever mailbox is listed. */
  mailboxes: Mailbox[];
  /** The user's role in the shared mailbox listed; none in their own. */
  role: Mailbox['role'] | null;
  accounts: Account[];
  /** The signature every account takes where it has none of its own. */
  signature: string;
  folders: MailFolder[];
  /** The domains whose senders' images are shown, or kept out, without asking. */
  images: { domain: string; shown: boolean }[];
  /** The folder each sender's mail goes to, by their address or a domain they write from. */
  rules: { id: number; sender: string; folder: number }[];
  /** The servers this installation reaches without TLS: its test server, if any. */
  plain: string[];
  /** Where a provider that refuses the account's own password has its app passwords made, by
      its incoming server. */
  app_passwords: Record<string, string>;
  /** The providers an account signs in through, by the incoming server their accounts use. */
  providers: Partial<Record<Provider, string>>;
}

export interface Person {
  name: string;
  address: string;
}

/** Who a message is with as a list shows it: whom it went to in the folders of what the user
 * sends, who sent it elsewhere. */
export function correspondents(
  message: { sender: Partial<Person>; to: Person[]; unanswered?: boolean },
  role: Role | '',
): string {
  return role === 'sent' || role === 'drafts' || message.unanswered
    ? message.to.map(person).join(', ')
    : person(message.sender);
}

export function person(given: Partial<Person>): string {
  return given.name || given.address || '';
}

/** The colours accounts take in turn, by name and by what draws them. */
export const ACCOUNT_COLORS = [
  ['petrol', 'bg-account-1', 'border-account-1', 'bg-account-1/40'],
  ['green', 'bg-account-2', 'border-account-2', 'bg-account-2/40'],
  ['orange', 'bg-account-3', 'border-account-3', 'bg-account-3/40'],
  ['violet', 'bg-account-4', 'border-account-4', 'bg-account-4/40'],
  ['rose', 'bg-account-5', 'border-account-5', 'bg-account-5/40'],
  ['gold', 'bg-account-6', 'border-account-6', 'bg-account-6/40'],
  ['blue', 'bg-account-7', 'border-account-7', 'bg-account-7/40'],
] as const;

/** The account's colour, faded for what is already read. */
export function accountColor(account: Pick<Account, 'color'>, faded = false): string {
  return ACCOUNT_COLORS[account.color % ACCOUNT_COLORS.length][faded ? 3 : 1];
}

export function accountRing(account: Pick<Account, 'color'>): string {
  return ACCOUNT_COLORS[account.color % ACCOUNT_COLORS.length][2];
}

export function accountName(account: Pick<Account, 'label' | 'address'>): string {
  return account.label || account.address;
}

export const ACCOUNTS = ['mail', 'accounts'];
export const PROTOCOLS = ['imap', 'activesync'] as const;

/** The shared mailbox the mail page shows, none for the user's own. */
export const BoxContext = createContext<number | null>(null);

export function useBox(): number | null {
  return useContext(BoxContext);
}

/** The path in the mailbox: what names no message, folder or account of it says which. */
export function inBox(path: string, box: number | null): string {
  if (box === null) return path;
  return `${path}${path.includes('?') ? '&' : '?'}box=${box}`;
}

export function useAccounts(enabled = true) {
  const box = useBox();
  return useQuery({
    queryKey: [...ACCOUNTS, box],
    queryFn: () => getJson<Accounts>(inBox('/api/mail/accounts', box)),
    enabled,
  });
}

export type MailSortKey = 'date' | 'correspondent' | 'priority';
export interface MailSort {
  key: MailSortKey;
  descending: boolean;
}
const MAIL_SORT = 'ponistra.mailSort';
export const MAIL_SORTS: MailSortKey[] = ['date', 'correspondent', 'priority'];

export function storedMailSort(): MailSort {
  try {
    const sort = JSON.parse(localStorage.getItem(MAIL_SORT) ?? 'null') as MailSort | null;
    if (sort && MAIL_SORTS.includes(sort.key))
      return { key: sort.key, descending: !!sort.descending };
  } catch {
    // Storage blocked or holding something else: the newest first, as always.
  }
  return { key: 'date', descending: true };
}

export function storeMailSort(sort: MailSort) {
  try {
    localStorage.setItem(MAIL_SORT, JSON.stringify(sort));
  } catch {
    // Storage blocked: the order holds until the page is left.
  }
}

/** A page of a folder's list, or of all the user flagged, as the list asks for it. */
export function listPath(
  folder: number | 'flagged' | 'later',
  sort: MailSort,
  box: number | null,
  only?: number,
  before?: string,
): string {
  const given = new URLSearchParams({
    ...(only ? { account: String(only) } : {}),
    ...(sort.key === 'date' && sort.descending
      ? {}
      : { sort: sort.key, descending: sort.descending ? '1' : '0' }),
    ...(before ? { before } : {}),
  });
  return inBox(`/api/mail/folders/${folder}/messages${given.size ? `?${given}` : ''}`, box);
}

/** A message as the reader asks for it: with the images from elsewhere let in once, translated. */
export function messagePath(id: number, { images = false, into = null as string | null } = {}) {
  return `/api/mail/messages/${id}?zone=${ZONE}${images ? '&images=1' : ''}${into ? `&into=${into}` : ''}`;
}

/** The reply, reply to all or forward of a message as the composer starts it. */
export function draftPath(id: number, way: 'reply' | 'all' | 'forward'): string {
  return `/api/mail/messages/${id}/draft?as=${way}`;
}
