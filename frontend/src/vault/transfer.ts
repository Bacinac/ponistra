import { blank, hostOf, type MailKey, type Secret } from './secret';

export type Format = 'bitwarden' | 'chrome' | 'firefox' | 'keepassxc' | 'keepass';

export class Unreadable extends Error {
  constructor(readonly reason: 'unknown' | 'encrypted') {
    super(reason);
  }
}

/** A secret and the folder it was kept in, as the names of the folder's levels. */
export interface Filed {
  secret: Secret;
  folder: string[];
}

export interface Imported {
  format: Format;
  items: Filed[];
  /** Cards and identities, which the vault does not keep yet. */
  skipped: number;
}

/** RFC 4180: fields in double quotes may hold commas, line breaks and doubled quotes. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = '';
  let quoted = false;
  const plain = text.replace(/^﻿/, '');
  for (let at = 0; at < plain.length; at++) {
    const char = plain[at];
    if (quoted) {
      if (char === '"' && plain[at + 1] === '"') {
        value += '"';
        at++;
      } else if (char === '"') quoted = false;
      else value += char;
    } else if (char === '"') quoted = true;
    else if (char === ',') {
      row.push(value);
      value = '';
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && plain[at + 1] === '\n') at++;
      row.push(value);
      rows.push(row);
      row = [];
      value = '';
    } else value += char;
  }
  if (value || row.length) rows.push([...row, value]);
  return rows.filter((each) => each.some((field) => field.trim()));
}

function login(fields: Partial<Secret>): Secret {
  const secret = { ...blank('login'), ...fields };
  return { ...secret, name: secret.name || hostOf(secret.urls[0] ?? '') || secret.username };
}

const levels = (path: string | undefined) =>
  (path ?? '')
    .split('/')
    .map((level) => level.trim())
    .filter(Boolean);

const urls = (text: string | undefined) =>
  (text ?? '')
    .split(/[\n,]/)
    .map((url) => url.trim())
    .filter(Boolean);

interface BitwardenItem {
  type: number;
  folderId?: string | null;
  name?: string;
  notes?: string | null;
  login?: {
    username?: string | null;
    password?: string | null;
    totp?: string | null;
    uris?: { uri?: string | null }[] | null;
  };
}

function fromBitwarden(text: string): Imported {
  const exported = JSON.parse(text) as {
    encrypted?: boolean;
    folders?: { id: string; name: string }[];
    items?: BitwardenItem[];
  };
  if (exported.encrypted) throw new Unreadable('encrypted');
  if (!Array.isArray(exported.items)) throw new Unreadable('unknown');
  const folders = new Map((exported.folders ?? []).map((folder) => [folder.id, folder.name]));
  const kept = exported.items.filter((item) => item.type === 1 || item.type === 2);
  return {
    format: 'bitwarden',
    skipped: exported.items.length - kept.length,
    items: kept.map((item) => ({
      folder: levels(item.folderId ? folders.get(item.folderId) : ''),
      secret:
        item.type === 2
          ? { ...blank('note'), name: item.name ?? '', notes: item.notes ?? '' }
          : login({
              name: item.name ?? '',
              notes: item.notes ?? '',
              username: item.login?.username ?? '',
              password: item.login?.password ?? '',
              totp: item.login?.totp ?? '',
              urls: (item.login?.uris ?? []).flatMap((uri) => (uri.uri ? [uri.uri] : [])),
            }),
    })),
  };
}

const FORMATS: { format: Format; needs: string[] }[] = [
  { format: 'bitwarden', needs: ['login_uri', 'login_password'] },
  { format: 'keepassxc', needs: ['title', 'username', 'password', 'url'] },
  { format: 'keepass', needs: ['account', 'login name', 'password', 'web site'] },
  { format: 'firefox', needs: ['url', 'username', 'password', 'httprealm'] },
  { format: 'chrome', needs: ['name', 'url', 'username', 'password'] },
];

/** The logins and notes a password manager or browser exported: Bitwarden's JSON or CSV,
    Chrome's and Edge's CSV, Firefox's, KeePassXC's and KeePass 2's. */
export function imported(text: string): Imported {
  if (text.trimStart().startsWith('{')) {
    try {
      return fromBitwarden(text);
    } catch (error) {
      if (error instanceof Unreadable) throw error;
      throw new Unreadable('unknown');
    }
  }
  const [header, ...rows] = parseCsv(text);
  const names = (header ?? []).map((name) => name.trim().toLowerCase());
  const found = FORMATS.find(({ needs }) => needs.every((name) => names.includes(name)));
  if (!found) throw new Unreadable('unknown');
  const records = rows.map((row) =>
    Object.fromEntries(names.map((name, at) => [name, row[at] ?? ''])),
  );
  const secretOf = (field: Record<string, string>): Secret => {
    switch (found.format) {
      case 'bitwarden':
        return field.type === 'note'
          ? { ...blank('note'), name: field.name, notes: field.notes }
          : login({
              name: field.name,
              notes: field.notes,
              urls: urls(field.login_uri),
              username: field.login_username,
              password: field.login_password,
              totp: field.login_totp ?? '',
            });
      case 'keepassxc':
        return login({
          name: field.title,
          username: field.username,
          password: field.password,
          urls: urls(field.url),
          notes: field.notes ?? '',
          totp: field.totp ?? '',
        });
      case 'keepass':
        return login({
          name: field.account,
          username: field['login name'],
          password: field.password,
          urls: urls(field['web site']),
          notes: field.comments ?? '',
        });
      case 'firefox':
        return login({
          username: field.username,
          password: field.password,
          urls: urls(field.url),
        });
      case 'chrome':
        return login({
          name: field.name,
          username: field.username,
          password: field.password,
          urls: urls(field.url),
          notes: field.note ?? field.notes ?? '',
        });
    }
  };
  const folderOf = (field: Record<string, string>): string[] => {
    switch (found.format) {
      case 'bitwarden':
        return levels(field.folder);
      // KeePassXC names the database's own root group first.
      case 'keepassxc':
        return levels(field.group).slice(1);
      default:
        return [];
    }
  };
  return {
    format: found.format,
    items: records.map((field) => ({ secret: secretOf(field), folder: folderOf(field) })),
    skipped: 0,
  };
}

function pem(label: string, base64: string): string {
  return [
    `-----BEGIN ${label}-----`,
    ...(base64.match(/.{1,64}/g) ?? []),
    `-----END ${label}-----`,
  ].join('\n');
}

/** A mail key as the text every tool reads back: PEM for S/MIME, the armored key for PGP. Bitwarden
    has no kind of its own for it, so it travels in a note's text. */
function keyText(key: MailKey): string {
  if (key.format === 'pgp') return key.private;
  return [
    pem('PRIVATE KEY', key.private),
    ...key.public.map((each) => pem('CERTIFICATE', each)),
  ].join('\n');
}

/** The secrets as Bitwarden's unencrypted JSON export, which every password manager imports,
    each folder by the path Bitwarden nests folders by. */
export function exported(items: Filed[]): string {
  const paths = [
    ...new Set(items.flatMap(({ folder }) => (folder.length ? [folder.join('/')] : []))),
  ];
  const ids = new Map(paths.map((path) => [path, crypto.randomUUID()]));
  return JSON.stringify(
    {
      encrypted: false,
      folders: paths.map((path) => ({ id: ids.get(path), name: path })),
      items: items.map(({ secret, folder }) => ({
        id: crypto.randomUUID(),
        folderId: ids.get(folder.join('/')) ?? null,
        organizationId: null,
        collectionIds: null,
        favorite: false,
        name: secret.name,
        notes:
          [secret.notes, secret.mailkey && keyText(secret.mailkey)].filter(Boolean).join('\n\n') ||
          null,
        ...(secret.kind !== 'login'
          ? { type: 2, secureNote: { type: 0 } }
          : {
              type: 1,
              login: {
                username: secret.username || null,
                password: secret.password || null,
                totp: secret.totp || null,
                uris: secret.urls.map((uri) => ({ match: null, uri })),
              },
            }),
      })),
    },
    null,
    2,
  );
}
