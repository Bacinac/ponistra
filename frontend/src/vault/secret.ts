import {
  bytesText,
  fromBase64,
  open,
  random,
  seal,
  textBytes,
  toBase64,
  type Bytes,
} from './crypto';

export type Kind = 'login' | 'note' | 'mailkey';

/** A key that signs and opens the user's mail (U5), kept whole by the vault: the server never
    sees its private part. */
export interface MailKey {
  format: 'smime' | 'pgp';
  addresses: string[];
  fingerprint: string;
  expires: string | null;
  /** PKCS #8 in base64 for S/MIME, the armored secret key for PGP. */
  private: string;
  /** For S/MIME the certificate chain in base64 DER, the user's own first; for PGP the binary
      public key in base64. */
  public: string[];
}

/** What an item holds, sealed whole: the server sees none of it, not even its name. */
export interface Secret {
  kind: Kind;
  name: string;
  username: string;
  password: string;
  urls: string[];
  /** An otpauth:// address or a bare base32 secret. */
  totp: string;
  notes: string;
  /** The passwords it held before, the latest first. */
  history: { password: string; until: string }[];
  mailkey?: MailKey;
}

export interface Person {
  id: number;
  email: string;
  name: string;
}

export interface SealedItem {
  id: string;
  collection: string;
  folder: string | null;
  key: string;
  data: string;
  attachments: { id: string; meta: string; size: number }[];
  created_at: string;
  updated_at: string;
  updated_by: Person | null;
  trashed_at: string | null;
}

export interface Attached {
  id: string;
  name: string;
  type: string;
  size: number;
}

export interface Opened {
  id: string;
  collection: string;
  folder: string | null;
  /** The item's own key, which seals its contents and its attachments. */
  key: Bytes;
  secret: Secret;
  attachments: Attached[];
  updated_at: string;
  updated_by: Person | null;
  trashed_at: string | null;
}

const KEPT = 10;

export function blank(kind: Kind): Secret {
  return { kind, name: '', username: '', password: '', urls: [], totp: '', notes: '', history: [] };
}

/** The secret as it is about to be saved over `before`, the password it replaces remembered. */
export function changed(before: Secret | undefined, after: Secret): Secret {
  if (!before?.password || before.password === after.password) return after;
  const history = [
    { password: before.password, until: new Date().toISOString() },
    ...after.history,
  ];
  return { ...after, history: history.slice(0, KEPT) };
}

export async function sealJson(key: Bytes, value: unknown): Promise<string> {
  return toBase64(await seal(key, textBytes(JSON.stringify(value))));
}

export async function openJson<T>(key: Bytes, sealed: string): Promise<T> {
  return JSON.parse(bytesText(await open(key, fromBase64(sealed)))) as T;
}

/** A new item's key wrapped with the collection's, and its contents sealed with it. */
export async function sealSecret(
  collectionKey: Bytes,
  secret: Secret,
  itemKey: Bytes = random(32),
): Promise<{ key: string; data: string }> {
  return {
    key: toBase64(await seal(collectionKey, itemKey)),
    data: await sealJson(itemKey, secret),
  };
}

export async function openItem(collectionKey: Bytes, item: SealedItem): Promise<Opened> {
  const key = await open(collectionKey, fromBase64(item.key));
  const secret = { ...blank('login'), ...(await openJson<Partial<Secret>>(key, item.data)) };
  const attachments = await Promise.all(
    item.attachments.map(async (attachment) => ({
      id: attachment.id,
      size: attachment.size,
      ...(await openJson<{ name: string; type: string }>(key, attachment.meta)),
    })),
  );
  return {
    id: item.id,
    collection: item.collection,
    folder: item.folder,
    key,
    secret,
    attachments,
    updated_at: item.updated_at,
    updated_by: item.updated_by,
    trashed_at: item.trashed_at,
  };
}

export interface Recipe {
  length: number;
  upper: boolean;
  digits: boolean;
  symbols: boolean;
}

export const RECIPE: Recipe = { length: 20, upper: true, digits: true, symbols: true };

const SETS = {
  lower: 'abcdefghijklmnopqrstuvwxyz',
  upper: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
  digits: '0123456789',
  symbols: '!#$%&*+-=?@^_~',
};

/** A uniformly random index below `size`: draws past the last whole multiple are thrown back. */
function below(size: number): number {
  const limit = Math.floor(0x100000000 / size) * size;
  for (;;) {
    const [drawn] = crypto.getRandomValues(new Uint32Array(1));
    if (drawn < limit) return drawn % size;
  }
}

/** A password of the recipe's length with at least one character of each set it asks for. */
export function generated(recipe: Recipe): string {
  const sets = [
    SETS.lower,
    ...(recipe.upper ? [SETS.upper] : []),
    ...(recipe.digits ? [SETS.digits] : []),
    ...(recipe.symbols ? [SETS.symbols] : []),
  ];
  const all = sets.join('');
  const chars = sets.map((set) => set[below(set.length)]);
  while (chars.length < recipe.length) chars.push(all[below(all.length)]);
  for (let at = chars.length - 1; at > 0; at--) {
    const other = below(at + 1);
    [chars[at], chars[other]] = [chars[other], chars[at]];
  }
  return chars.join('');
}

/** The host of a site's address, none where the address is not one. */
export function hostIn(address: string): string {
  try {
    return new URL(address.includes('://') ? address : `https://${address}`).hostname;
  } catch {
    return '';
  }
}

/** How a site's address reads in a list: its host, or the address as it was typed. */
export function hostOf(address: string): string {
  return hostIn(address) || address;
}
