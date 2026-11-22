// Folders on other machines for PONISTRA's page of code (PJ12). A host is an entry of the
// workspace's own `~/.ssh/config`, so the terminal and the chats reach it by the same name, and
// the key it signs in with lives in `~/.ssh` beside it. Its files are read and written over SFTP,
// spoken here to the `sftp` subsystem of the image's OpenSSH (`ssh -s`), which brings whatever
// else that entry or the owner's own config says (a jump host, a known host). As in the projects'
// files, a file is written only while it is still what the editor read; nothing is removed,
// renamed or uploaded.
import { execFile, spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { chmodSync, existsSync, mkdirSync, readdirSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, posix } from 'node:path';
import { promisify } from 'node:util';
import { Refusal } from './chats.mjs';
import { askedPath, EDITED, hashOf, ordered, PATH, textOf, WRITE_BODY, writtenBytes } from './files.mjs';

export const HOSTS = /^\/ponistra\/hosts(\/(remove|key))?$/;
const SSH = join(homedir(), '.ssh');
const CONFIG = join(SSH, 'config');
// The line above each entry this page keeps, with the folder its files open at.
const MARK = '# Ponistra files:';
const KEY = 'ponistra_ed25519';
const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$/;
const ADDRESS = /^(?!-)[A-Za-z0-9._:-]{1,253}$/;
const USER = /^[A-Za-z0-9._][A-Za-z0-9._-]{0,63}$/;
const KEY_NAME = /^[A-Za-z0-9._-]{1,100}$/;
const HOST_BODY = 16 * 1024;
// A connection unused this long ends; the next request opens another.
const IDLE = 2 * 60 * 1000;
const OPENING = 20 * 1000;
const ANSWERING = 30 * 1000;
const CHUNK = 32 * 1024;
const AHEAD = 16;
// Larger than any packet OpenSSH sends; a larger length is a shell's greeting in the stream.
const PACKET = 1024 * 1024;

const execute = promisify(execFile);

// SFTP version 3 (draft-ietf-secsh-filexfer-02), as OpenSSH's sftp-server speaks it.
const T = {
  INIT: 1, VERSION: 2, OPEN: 3, CLOSE: 4, READ: 5, WRITE: 6, FSTAT: 8, FSETSTAT: 10,
  OPENDIR: 11, READDIR: 12, REMOVE: 13, REALPATH: 16, STAT: 17, EXTENDED: 200,
  STATUS: 101, HANDLE: 102, DATA: 103, NAME: 104, ATTRS: 105,
};
const STATUS = { OK: 0, EOF: 1, NO_SUCH_FILE: 2, PERMISSION_DENIED: 3 };
const ATTR = { SIZE: 0x1, UIDGID: 0x2, PERMISSIONS: 0x4, ACMODTIME: 0x8, EXTENDED: 0x80000000 };
const OPEN = { READ: 0x1, WRITE: 0x2, CREAT: 0x8, TRUNC: 0x10, EXCL: 0x20 };
const RENAME = 'posix-rename@openssh.com';

// What ssh says when it cannot sign in, as the owner's error; the first that matches wins.
const FAILURES = [
  [/REMOTE HOST IDENTIFICATION HAS CHANGED/, 'host_key_changed'],
  [/Host key verification failed|No \S+ host key is known/, 'host_key_unknown'],
  [/Bad configuration option|bad configuration options|Unsupported option|line \d+: /, 'ssh_config_invalid'],
  [/Load key .*: (invalid format|bad permissions)|UNPROTECTED PRIVATE KEY/, 'ssh_key_unreadable'],
  [/Permission denied \(|Too many authentication failures/, 'ssh_key_refused'],
  [/Could not resolve hostname/, 'host_unknown'],
  [/subsystem request failed/, 'sftp_missing'],
  [/Connection refused|timed out|No route to host|Network is unreachable|Connection reset|Connection closed|banner exchange/, 'host_unreachable'],
];

const u32 = (value) => {
  const bytes = Buffer.alloc(4);
  bytes.writeUInt32BE(value);
  return bytes;
};
const u64 = (value) => {
  const bytes = Buffer.alloc(8);
  bytes.writeBigUInt64BE(BigInt(value));
  return bytes;
};
const string = (value) => {
  const bytes = Buffer.isBuffer(value) ? value : Buffer.from(value, 'utf8');
  return Buffer.concat([u32(bytes.length), bytes]);
};
const attrsOf = ({ uid, gid, permissions }) =>
  uid === undefined
    ? Buffer.concat([u32(ATTR.PERMISSIONS), u32(permissions)])
    : Buffer.concat([u32(ATTR.UIDGID | ATTR.PERMISSIONS), u32(uid), u32(gid), u32(permissions)]);

class Reader {
  constructor(bytes) {
    this.bytes = bytes;
    this.at = 0;
  }
  u32() {
    const value = this.bytes.readUInt32BE(this.at);
    this.at += 4;
    return value;
  }
  u64() {
    const value = Number(this.bytes.readBigUInt64BE(this.at));
    this.at += 8;
    return value;
  }
  raw() {
    const length = this.u32();
    const value = this.bytes.subarray(this.at, this.at + length);
    this.at += length;
    return value;
  }
  string() {
    return this.raw().toString('utf8');
  }
  attrs() {
    const flags = this.u32();
    const attrs = {};
    if (flags & ATTR.SIZE) attrs.size = this.u64();
    if (flags & ATTR.UIDGID) [attrs.uid, attrs.gid] = [this.u32(), this.u32()];
    if (flags & ATTR.PERMISSIONS) attrs.permissions = this.u32();
    if (flags & ATTR.ACMODTIME) [attrs.atime, attrs.mtime] = [this.u32(), this.u32()];
    if (flags & ATTR.EXTENDED)
      for (let count = this.u32(); count > 0; count--) {
        this.raw();
        this.raw();
      }
    return attrs;
  }
}

const kindOf = ({ permissions }) => {
  if (permissions === undefined) return 'other';
  const type = permissions & 0o170000;
  return type === 0o040000 ? 'folder' : type === 0o100000 ? 'file' : type === 0o120000 ? 'link' : 'other';
};
const modifiedOf = ({ mtime }) => (mtime === undefined ? null : new Date(mtime * 1000).toISOString());

/** One connection to a host's `sftp` subsystem, requests answered by their ids. */
class Connection {
  constructor(name, folder, onGone) {
    this.name = name;
    this.waiting = new Map();
    this.next = 1;
    this.pending = Buffer.alloc(0);
    this.said = '';
    this.gone = false;
    this.failure = null;
    this.onGone = onGone;
    this.process = spawn(
      'ssh',
      ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', '-s', '--', name, 'sftp'],
      { stdio: ['pipe', 'pipe', 'pipe'] },
    );
    this.process.stderr.on('data', (part) => {
      if (this.said.length < 16 * 1024) this.said += part.toString('utf8');
    });
    this.process.stdout.on('data', (part) => this.received(part));
    this.process.stdin.on('error', () => {});
    this.process.on('error', (error) => this.end(new Refusal(500, `ssh failed to start: ${error.message}`)));
    this.process.on('close', () => this.end(null));
    this.ready = new Promise((resolve, reject) => {
      this.version = { resolve, reject };
    });
    this.ready.catch(() => {});
    const opening = setTimeout(() => this.end(new Refusal(409, 'host_unreachable')), OPENING);
    this.ready.finally(() => clearTimeout(opening)).catch(() => {});
    this.send(Buffer.concat([Buffer.from([T.INIT]), u32(3)]));
    // SFTP takes a relative path from the user's home, where a shell would expand `~`.
    this.start = this.ready.then(() => this.realpath(folder.replace(/^~(\/|$)/, './') || '.'));
    this.start.catch(() => {});
    this.touch();
  }

  /** What ssh said as the owner's error, logged where it is none of those known. */
  failed() {
    const said = this.said.trim();
    const known = FAILURES.find(([pattern]) => pattern.test(said));
    if (known) return new Refusal(409, known[1]);
    console.error(`ssh to ${this.name} ended: ${said || 'without a word'}`);
    return new Refusal(409, 'host_failed');
  }

  end(failure) {
    if (this.gone) return;
    this.gone = true;
    clearTimeout(this.idle);
    this.failure = failure ?? this.failed();
    this.process.kill();
    this.version.reject(this.failure);
    for (const { reject } of this.waiting.values()) reject(this.failure);
    this.waiting.clear();
    this.onGone(this);
  }

  touch() {
    clearTimeout(this.idle);
    this.idle = setTimeout(() => {
      if (!this.waiting.size) this.end(new Refusal(409, 'host_closed'));
      else this.touch();
    }, IDLE);
  }

  send(body) {
    this.process.stdin.write(Buffer.concat([u32(body.length), body]));
  }

  received(part) {
    this.pending = Buffer.concat([this.pending, part]);
    while (this.pending.length >= 4) {
      const length = this.pending.readUInt32BE(0);
      if (length > PACKET || length < 1) {
        console.error(`sftp on ${this.name} sent what is no packet; a shell greeting reaches the stream`);
        return this.end(new Refusal(409, 'sftp_garbled'));
      }
      if (this.pending.length < 4 + length) return;
      const packet = this.pending.subarray(4, 4 + length);
      this.pending = this.pending.subarray(4 + length);
      this.answered(packet[0], new Reader(packet.subarray(1)));
    }
  }

  answered(type, reader) {
    if (type === T.VERSION) {
      reader.u32();
      this.extensions = new Set();
      while (reader.at < reader.bytes.length) {
        this.extensions.add(reader.string());
        reader.string();
      }
      return this.version.resolve();
    }
    const id = reader.u32();
    const asked = this.waiting.get(id);
    if (!asked) return;
    this.waiting.delete(id);
    clearTimeout(asked.timer);
    if (type !== T.STATUS) return asked.resolve({ type, reader });
    const code = reader.u32();
    const message = reader.string();
    if (code === STATUS.OK || code === STATUS.EOF) return asked.resolve({ type, code });
    if (code === STATUS.NO_SUCH_FILE) return asked.reject(new Refusal(404, 'not_found'));
    if (code === STATUS.PERMISSION_DENIED) return asked.reject(new Refusal(403, 'not_permitted'));
    console.error(`sftp on ${this.name} refused a request: ${code} ${message}`);
    asked.reject(new Refusal(409, 'host_failed'));
  }

  request(type, ...parts) {
    if (this.gone) return Promise.reject(this.failure);
    const id = this.next++;
    this.touch();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => this.end(new Refusal(409, 'host_unreachable')), ANSWERING);
      this.waiting.set(id, { resolve, reject, timer });
      this.send(Buffer.concat([Buffer.from([type]), u32(id), ...parts]));
    });
  }

  async expect(type, asked) {
    const answer = await asked;
    if (answer.type !== type) throw new Refusal(409, 'host_failed');
    return answer.reader;
  }

  async realpath(path) {
    const reader = await this.expect(T.NAME, this.request(T.REALPATH, string(path)));
    reader.u32();
    return reader.string();
  }

  async stat(path) {
    return (await this.expect(T.ATTRS, this.request(T.STAT, string(path)))).attrs();
  }

  async fstat(handle) {
    return (await this.expect(T.ATTRS, this.request(T.FSTAT, string(handle)))).attrs();
  }

  async open(path, flags, attrs) {
    const given = attrs ? attrsOf(attrs) : u32(0);
    return (await this.expect(T.HANDLE, this.request(T.OPEN, string(path), u32(flags), given))).raw();
  }

  async opendir(path) {
    return (await this.expect(T.HANDLE, this.request(T.OPENDIR, string(path)))).raw();
  }

  async close(handle) {
    await this.request(T.CLOSE, string(handle));
  }

  /** Up to `length` bytes from `offset`, null at the end of the file. */
  async read(handle, offset, length) {
    const answer = await this.request(T.READ, string(handle), u64(offset), u32(length));
    if (answer.type === T.STATUS) return null;
    if (answer.type !== T.DATA) throw new Refusal(409, 'host_failed');
    return Buffer.from(answer.reader.raw());
  }

  async write(handle, offset, bytes) {
    await this.request(T.WRITE, string(handle), u64(offset), string(bytes));
  }

  async fsetstat(handle, attrs) {
    await this.request(T.FSETSTAT, string(handle), attrsOf(attrs));
  }

  async remove(path) {
    await this.request(T.REMOVE, string(path));
  }

  /** Puts `from` in the place of `to` at once, as OpenSSH's own extension does. */
  async replace(from, to) {
    await this.request(T.EXTENDED, string(RENAME), string(from), string(to));
  }

  /** A folder's entries with their attributes, as lstat sees them. */
  async entries(path) {
    const handle = await this.opendir(path);
    const found = [];
    try {
      for (;;) {
        const answer = await this.request(T.READDIR, string(handle));
        if (answer.type === T.STATUS) break;
        if (answer.type !== T.NAME) throw new Refusal(409, 'host_failed');
        for (let count = answer.reader.u32(); count > 0; count--) {
          const name = answer.reader.string();
          answer.reader.string();
          const attrs = answer.reader.attrs();
          if (name !== '.' && name !== '..') found.push({ name, attrs });
        }
      }
    } finally {
      await this.close(handle).catch(() => {});
    }
    return found;
  }

  /** A file's bytes while they are no more than `most`, null once they are more. */
  async whole(path, most) {
    const handle = await this.open(path, OPEN.READ);
    const parts = [];
    let size = 0;
    try {
      for (;;) {
        const part = await this.read(handle, size, CHUNK);
        if (part === null) break;
        size += part.length;
        if (size > most) return null;
        parts.push(part);
      }
    } finally {
      await this.close(handle).catch(() => {});
    }
    return Buffer.concat(parts);
  }
}

const connections = new Map();

/** The host's open connection or a new one, once it is signed in, and the folder it starts at. */
const connectionOf = async (host) => {
  let connection = connections.get(host.name);
  if (!connection || connection.gone) {
    connection = new Connection(host.name, host.path, (gone) => {
      if (connections.get(gone.name) === gone) connections.delete(gone.name);
    });
    connections.set(host.name, connection);
  }
  await connection.ready;
  return { connection, start: await connection.start };
};

const ended = (name) => {
  connections.get(name)?.end(new Refusal(409, 'host_closed'));
};

// The workspace's ssh config: the entries this page keeps, each the mark, `Host` and its options.

const configFile = () => {
  try {
    return realpathSync(CONFIG);
  } catch (error) {
    if (error.code === 'ENOENT') return CONFIG;
    throw error;
  }
};

const linesOf = () => {
  try {
    return readFileSync(configFile(), 'utf8').split('\n');
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
};

/** Each entry kept here with where it stands among the lines, the others' names besides. */
const parsed = (lines) => {
  const kept = [];
  const names = new Set();
  for (let at = 0; at < lines.length; at++) {
    const host = /^\s*Host\s+(.+?)\s*$/i.exec(lines[at]);
    if (host) for (const name of host[1].split(/\s+/)) names.add(name);
    if (!lines[at].startsWith(MARK)) continue;
    const named = /^Host\s+(\S+)\s*$/i.exec(lines[at + 1] ?? '');
    if (!named) continue;
    let end = at + 2;
    const options = {};
    for (; end < lines.length && /^\s+\S/.test(lines[end]); end++) {
      const option = /^\s+(\S+)\s+(.*?)\s*$/.exec(lines[end]);
      if (option) options[option[1].toLowerCase()] = option[2];
    }
    const identity = options.identityfile ?? '';
    kept.push({
      at,
      end,
      host: {
        name: named[1],
        address: options.hostname ?? named[1],
        port: Number(options.port ?? 22),
        user: options.user ?? '',
        path: lines[at].slice(MARK.length).trim(),
        key: identity.startsWith('~/.ssh/') ? identity.slice('~/.ssh/'.length) : identity,
      },
    });
  }
  return { kept, names };
};

const blockOf = (host) => [
  `${MARK}${host.path ? ` ${host.path}` : ''}`,
  `Host ${host.name}`,
  `\tHostName ${host.address}`,
  `\tPort ${host.port}`,
  `\tUser ${host.user}`,
  `\tIdentityFile ~/.ssh/${host.key}`,
  '\tIdentitiesOnly yes',
  '\tStrictHostKeyChecking accept-new',
];

const placeSsh = () => {
  mkdirSync(SSH, { recursive: true, mode: 0o700 });
};

const writeConfig = (lines) => {
  placeSsh();
  const file = configFile();
  const kept = join(posix.dirname(file), `.${randomUUID()}.ponistra`);
  try {
    const last = lines.length - [...lines].reverse().findIndex((line) => line.trim() !== '');
    const text = lines.slice(0, last > lines.length ? 0 : last).join('\n');
    writeFileSync(kept, text ? `${text}\n` : '', { mode: 0o600 });
    chmodSync(kept, 0o600);
    renameSync(kept, file);
  } catch (error) {
    rmSync(kept, { force: true });
    throw error;
  }
};

const hostOf = (name) => {
  if (typeof name !== 'string' || !NAME.test(name)) throw new Refusal(400, 'invalid_host');
  const found = parsed(linesOf()).kept.find(({ host }) => host.name === name);
  if (!found) throw new Refusal(404, 'unknown_host');
  return found.host;
};

/** The keys in `~/.ssh` that have their public half beside them. */
const keysOf = () => {
  let names;
  try {
    names = readdirSync(SSH);
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
  return names
    .filter((name) => name.endsWith('.pub') && names.includes(name.slice(0, -4)) && KEY_NAME.test(name.slice(0, -4)))
    .map((name) => {
      const line = readFileSync(join(SSH, name), 'utf8').trim().split('\n')[0];
      const [type = '', , ...comment] = line.split(/\s+/);
      return { name: name.slice(0, -4), type, comment: comment.join(' '), public: line };
    })
    .sort((one, other) => (one.name === KEY ? -1 : other.name === KEY ? 1 : one.name.localeCompare(other.name)));
};

const hostsOf = () => ({
  hosts: parsed(linesOf()).kept.map(({ host }) => host),
  keys: keysOf(),
  made: KEY,
});

const given = (body) => {
  const { name, address, port, user, path, key } = body;
  if (typeof name !== 'string' || !NAME.test(name)) throw new Refusal(400, 'invalid_host');
  if (typeof address !== 'string' || !ADDRESS.test(address)) throw new Refusal(400, 'invalid_host_address');
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Refusal(400, 'invalid_host_port');
  if (typeof user !== 'string' || !USER.test(user)) throw new Refusal(400, 'invalid_host_user');
  const folder = typeof path === 'string' ? path.trim() : path;
  if (typeof folder !== 'string' || folder.length > PATH || /[\0\r\n]/.test(folder)) throw new Refusal(400, 'invalid_path');
  if (typeof key !== 'string' || !keysOf().some((each) => each.name === key)) throw new Refusal(400, 'invalid_host_key');
  return { name, address, port, user, path: folder, key };
};

/** A host written into the config: in the place of the one it was, or after the others kept
    here, ahead of the owner's own entries so that a `Host *` of theirs does not outrank it. */
const saved = (body) => {
  const host = given(body);
  const was = body.was ?? null;
  const lines = linesOf();
  const { kept, names } = parsed(lines);
  const before = was === null ? null : kept.find((each) => each.host.name === was);
  if (was !== null && !before) throw new Refusal(404, 'unknown_host');
  if (host.name !== was && names.has(host.name)) throw new Refusal(409, 'host_exists');
  if (before) lines.splice(before.at, before.end - before.at, ...blockOf(host));
  else {
    const first = lines.findIndex((line) => /^\s*(Host|Match)\s/i.test(line));
    const at = kept.length ? kept.at(-1).end : first === -1 ? lines.length : first;
    const spaced = at > 0 && lines[at - 1].trim() !== '' ? [''] : [];
    const parted = at < lines.length && lines[at].trim() !== '' ? [''] : [];
    lines.splice(at, 0, ...spaced, ...blockOf(host), ...parted);
  }
  writeConfig(lines);
  if (was !== null) ended(was);
  return hostsOf();
};

const removed = ({ name }) => {
  hostOf(name);
  const lines = linesOf();
  const found = parsed(lines).kept.find(({ host }) => host.name === name);
  const blank = lines[found.end]?.trim() === '' ? 1 : 0;
  lines.splice(found.at, found.end - found.at + blank);
  writeConfig(lines);
  ended(name);
  return hostsOf();
};

const keyMade = async () => {
  placeSsh();
  const file = join(SSH, KEY);
  if (existsSync(file)) throw new Refusal(409, 'key_exists');
  const installation = new URL(process.env.PONISTRA_PUBLIC_URL).hostname;
  await execute('ssh-keygen', ['-q', '-t', 'ed25519', '-N', '', '-C', `ponistra@${installation}`, '-f', file]);
  return hostsOf();
};

/** Where a path given from the host's starting folder lies; the folder is where its files open,
    not a fence, since the host's own rights decide what its user reaches. */
const placed = (start, path) => posix.join(start, askedPath(path));
const shownOf = (start, real) => posix.relative(start, real);

const listedOn = async (host, path) => {
  const { connection, start } = await connectionOf(host);
  const directory = placed(start, path ?? '');
  if (kindOf(await connection.stat(directory)) !== 'folder') throw new Refusal(400, 'not_a_folder');
  const found = await connection.entries(directory);
  const entries = await Promise.all(
    found.map(async ({ name, attrs }) => {
      let real = attrs;
      if (kindOf(attrs) === 'link') {
        try {
          real = await connection.stat(posix.join(directory, name));
        } catch (error) {
          if (!(error instanceof Refusal) || connection.gone) throw error;
          return { name, kind: 'broken', size: null, modified: null };
        }
      }
      const kind = kindOf(real);
      return { name, kind, size: kind === 'file' ? (real.size ?? null) : null, modified: modifiedOf(real) };
    }),
  );
  return { path: shownOf(start, directory), entries: ordered(entries) };
};

const fileOn = async (connection, real) => {
  const attrs = await connection.stat(real);
  if (kindOf(attrs) !== 'file') throw new Refusal(400, 'not_a_file');
  return attrs;
};

const readOn = async (host, path) => {
  const { connection, start } = await connectionOf(host);
  const real = placed(start, path);
  const attrs = await fileOn(connection, real);
  const shown = { path: shownOf(start, real), size: attrs.size, modified: modifiedOf(attrs) };
  const bytes = attrs.size > EDITED ? null : await connection.whole(real, EDITED);
  if (bytes === null) return { ...shown, kind: 'large', text: null, hash: null };
  const text = textOf(bytes);
  return { ...shown, size: bytes.length, kind: text === null ? 'binary' : 'text', text, hash: hashOf(bytes) };
};

const refusedRight = (error) => error instanceof Refusal && error.status === 403;

const writeAll = async (connection, handle, bytes) => {
  for (let offset = 0; offset < bytes.length; offset += CHUNK)
    await connection.write(handle, offset, bytes.subarray(offset, offset + CHUNK));
};

/** The text written beside the file and put in its place at once, with the owner, group and mode
    the file had; false where the host cannot make that copy (a folder its user may not write in,
    an owner or group it cannot give, no OpenSSH rename), and nothing of it is left behind. */
const replacedWith = async (connection, real, attrs, bytes) => {
  if (!connection.extensions.has(RENAME)) return false;
  const kept = posix.join(posix.dirname(real), `.${randomUUID()}.ponistra`);
  const permissions = (attrs.permissions ?? 0o644) & 0o7777;
  let handle;
  try {
    handle = await connection.open(kept, OPEN.WRITE | OPEN.CREAT | OPEN.EXCL, { permissions });
  } catch (error) {
    if (refusedRight(error)) return false;
    throw error;
  }
  let done = false;
  try {
    try {
      await writeAll(connection, handle, bytes);
      const made = await connection.fstat(handle);
      if (attrs.uid !== undefined && (made.uid !== attrs.uid || made.gid !== attrs.gid)) {
        try {
          await connection.fsetstat(handle, { uid: attrs.uid, gid: attrs.gid, permissions });
        } catch (error) {
          if (refusedRight(error)) return false;
          throw error;
        }
      }
    } finally {
      await connection.close(handle);
    }
    await connection.replace(kept, real);
    done = true;
  } finally {
    if (!done) await connection.remove(kept).catch(() => {});
  }
  return true;
};

/** A file written anew while it still holds what the editor read. It is replaced at once where
    the copy beside it keeps who owns it, and otherwise written over in place, as vim's
    `backupcopy=auto` does: a server's file is often writable by a group in a folder that is not,
    and a copy would hand it to the user who saved it. */
const writtenOn = async (host, { path, text, hash }) => {
  const bytes = writtenBytes(text, hash);
  const { connection, start } = await connectionOf(host);
  const real = await connection.realpath(placed(start, path));
  const attrs = await fileOn(connection, real);
  const now = attrs.size > EDITED ? null : await connection.whole(real, EDITED);
  if (now === null || hashOf(now) !== hash) throw new Refusal(409, 'changed');
  if (!(await replacedWith(connection, real, attrs, bytes))) {
    const handle = await connection.open(real, OPEN.WRITE | OPEN.TRUNC);
    try {
      await writeAll(connection, handle, bytes);
    } finally {
      await connection.close(handle);
    }
  }
  const after = await connection.stat(real);
  return { path: shownOf(start, real), size: after.size, modified: modifiedOf(after), hash: hashOf(bytes) };
};

/** The file's bytes as they are, several reads ahead of what is written out. */
const sentOn = async (host, path, response) => {
  const { connection, start } = await connectionOf(host);
  const real = placed(start, path);
  const attrs = await fileOn(connection, real);
  const handle = await connection.open(real, OPEN.READ);
  const size = attrs.size;
  response.writeHead(200, { 'content-type': 'application/octet-stream', 'content-length': size });
  let offset = 0;
  const ahead = [];
  const ask = (at, length) => ({ at, length, part: connection.read(handle, at, length) });
  const more = () => {
    while (ahead.length < AHEAD && offset < size) {
      const length = Math.min(CHUNK, size - offset);
      ahead.push(ask(offset, length));
      offset += length;
    }
  };
  try {
    more();
    while (ahead.length) {
      const { at, length, part } = ahead.shift();
      const bytes = await part;
      if (bytes === null) break;
      if (bytes.length < length) ahead.unshift(ask(at + bytes.length, length - bytes.length));
      if (!response.write(bytes)) await once(response, 'drain');
      more();
    }
    response.end();
  } catch (error) {
    console.error(`a file of ${host.name} could not be sent`, error);
    response.destroy(error);
  } finally {
    for (const { part } of ahead) part.catch(() => {});
    await connection.close(handle).catch(() => {});
  }
};

/** Answers a request under `/ponistra/files` for a host's files (its `host` asked beside the
    path), the JSON to send back, or null once the bytes of a file are on their way. */
export const hostFilesAnswered = async (request, path, address, bodyOf, response) => {
  const host = hostOf(address.searchParams.get('host'));
  const asked = address.searchParams.get('path');
  if (request.method === 'GET' && path === '/ponistra/files') return listedOn(host, asked);
  if (request.method === 'GET' && path === '/ponistra/files/read') return readOn(host, asked);
  if (request.method === 'GET' && path === '/ponistra/files/raw') {
    await sentOn(host, asked, response);
    return null;
  }
  if (request.method === 'POST' && path === '/ponistra/files/write') return writtenOn(host, await bodyOf(request, WRITE_BODY));
  throw new Refusal(404, 'not_found');
};

/** Answers a request under `/ponistra/hosts`: the hosts and keys, a host saved or removed, the
    workspace's own key made. */
export const hostsAnswered = async (request, path, bodyOf) => {
  if (request.method === 'GET' && path === '/ponistra/hosts') return hostsOf();
  if (request.method === 'POST' && path === '/ponistra/hosts') return saved(await bodyOf(request, HOST_BODY));
  if (request.method === 'POST' && path === '/ponistra/hosts/remove') return removed(await bodyOf(request, HOST_BODY));
  if (request.method === 'POST' && path === '/ponistra/hosts/key') return keyMade();
  throw new Refusal(404, 'not_found');
};
