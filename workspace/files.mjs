// A project's files for PONISTRA's page of code (PJ6, ML6): a folder's entries, a file's text or
// its bytes, a file written anew or uploaded, a folder made, an entry renamed, moved or deleted.
// Every path is taken relative to one of the workspace's project folders and followed to where it
// really lies, so neither `..` nor a symbolic link leads out of the project; what is changed is
// the entry itself, a link and never what it points at. A file is written only while it is still
// what the editor read (its hash), as a chat or another session may be writing the same tree.
import { createHash, randomUUID } from 'node:crypto';
import {
  chmodSync,
  createReadStream,
  lchownSync,
  createWriteStream,
  linkSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  readlinkSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { pipeline } from 'node:stream/promises';
import { basename, dirname, join, relative, sep } from 'node:path';
import { Refusal } from './chats.mjs';

export const FILES = /^\/ponistra\/files(\/(read|raw|write|folder|rename|remove|put|stat|mode|owner))?$/;
// Larger than this a file is only downloaded; the editor would hold it all in the page.
const EDITED = 1024 * 1024;
const WRITE_BODY = 4 * EDITED + 64 * 1024;
const PATH = 4096;
const NAMED = 255;
const REMOVED = 1000;
const CHANGE_BODY = REMOVED * (PATH + 8) + 64 * 1024;
const HIDDEN = new Set(['.git']);
const BY_NAME = new Intl.Collator('hr', { numeric: true, sensitivity: 'base' });

const denied = (error) => (error.code === 'EACCES' || error.code === 'EPERM' ? new Refusal(403, 'not_permitted') : error);

const hashOf = (bytes) => createHash('sha256').update(bytes).digest('hex');

const inside = (base, real) => real === base || real.startsWith(`${base}${sep}`);

/** The project's folder as the disk has it, only for a folder the workspace lists. */
const baseOf = (folder, folders) => {
  if (typeof folder !== 'string' || !folders().includes(folder)) throw new Refusal(404, 'unknown_folder');
  return realpathSync(folder);
};

/** A path asked within a place, which a text of no more than PATH characters names. */
const askedPath = (path) => {
  if (typeof path !== 'string' || path.length > PATH || path.includes('\0')) throw new Refusal(400, 'invalid_path');
  return path;
};

/** Where a path given within the project really lies, refused when that is outside it. */
const placed = (base, path) => {
  const asked = join(base, askedPath(path));
  if (!inside(base, asked)) throw new Refusal(400, 'invalid_path');
  let real;
  try {
    real = realpathSync(asked);
  } catch {
    throw new Refusal(404, 'not_found');
  }
  if (!inside(base, real)) throw new Refusal(403, 'outside');
  return real;
};

const linkOf = (at) => {
  try {
    return readlinkSync(at);
  } catch {
    return null;
  }
};

const entryOf = (base, directory, name, symbolic) => {
  const at = join(directory, name);
  const link = symbolic ? { link: linkOf(at) } : {};
  let stat;
  let outside = false;
  try {
    stat = statSync(at);
    if (symbolic) outside = !inside(base, realpathSync(at));
  } catch {
    return { name, kind: symbolic ? 'link' : 'other', size: null, modified: null, ...link };
  }
  if (outside) return { name, kind: 'outside', size: null, modified: null, ...link };
  return {
    name,
    kind: stat.isDirectory() ? 'folder' : stat.isFile() ? 'file' : 'other',
    size: stat.isFile() ? stat.size : null,
    modified: stat.mtime.toISOString(),
    ...link,
  };
};

/** Folders first, then by name as Croatian orders it. */
const ordered = (entries) =>
  entries.sort((one, other) =>
    (one.kind === 'folder') !== (other.kind === 'folder') ? (one.kind === 'folder' ? -1 : 1) : BY_NAME.compare(one.name, other.name),
  );

const listed = (folder, path, folders) => {
  const base = baseOf(folder, folders);
  const directory = placed(base, path ?? '');
  if (!statSync(directory).isDirectory()) throw new Refusal(400, 'not_a_folder');
  const entries = readdirSync(directory, { withFileTypes: true })
    .filter((each) => !(directory === base && HIDDEN.has(each.name)))
    .map((each) => entryOf(base, directory, each.name, each.isSymbolicLink()));
  return { path: relative(base, directory), entries: ordered(entries) };
};

const regular = (real) => {
  const stat = statSync(real);
  if (!stat.isFile()) throw new Refusal(400, 'not_a_file');
  return stat;
};

/** Text decodes as UTF-8 throughout and holds no NUL, which no text file writes. */
const textOf = (bytes) => {
  if (bytes.includes(0)) return null;
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
};

const read = (folder, path, folders) => {
  const base = baseOf(folder, folders);
  const real = placed(base, path);
  const stat = regular(real);
  const shown = { path: relative(base, real), size: stat.size, modified: stat.mtime.toISOString() };
  if (stat.size > EDITED) return { ...shown, kind: 'large', text: null, hash: null };
  const bytes = readFileSync(real);
  const text = textOf(bytes);
  return { ...shown, kind: text === null ? 'binary' : 'text', text, hash: hashOf(bytes) };
};

/** The bytes of a text to write over a file still holding what `hash` says it held. */
const writtenBytes = (text, hash) => {
  if (typeof text !== 'string') throw new Refusal(400, 'invalid_text');
  if (typeof hash !== 'string' || !/^[0-9a-f]{64}$/.test(hash)) throw new Refusal(400, 'invalid_hash');
  const bytes = Buffer.from(text, 'utf8');
  if (bytes.length > EDITED) throw new Refusal(413, 'too_large');
  return bytes;
};

const written = ({ folder, path, text, hash }, folders) => {
  const bytes = writtenBytes(text, hash);
  const base = baseOf(folder, folders);
  const real = placed(base, path);
  const stat = regular(real);
  if (stat.size > EDITED || hashOf(readFileSync(real)) !== hash) throw new Refusal(409, 'changed');
  const kept = join(dirname(real), `.${randomUUID()}.ponistra`);
  try {
    writeFileSync(kept, bytes);
    chmodSync(kept, stat.mode & 0o7777);
    renameSync(kept, real);
  } catch (error) {
    rmSync(kept, { force: true });
    throw denied(error);
  }
  const now = statSync(real);
  return { path: relative(base, real), size: now.size, modified: now.mtime.toISOString(), hash: hashOf(bytes) };
};

/** The one range of bytes a player asks for, of a file this large; none for the whole file. */
const rangeOf = (header, size) => {
  if (!header) return null;
  const asked = /^bytes=(\d*)-(\d*)$/.exec(header);
  if (!asked || (!asked[1] && !asked[2])) throw new Refusal(416, 'unsatisfiable');
  const [start, end] = asked[1]
    ? [Number(asked[1]), asked[2] ? Math.min(Number(asked[2]), size - 1) : size - 1]
    : [Math.max(size - Number(asked[2]), 0), size - 1];
  if (start > end || start >= size) throw new Refusal(416, 'unsatisfiable');
  return { start, end };
};

/** The file's bytes as they are, or the range asked of them, for PONISTRA to hand on. */
const sent = (request, folder, path, folders, response) => {
  const base = baseOf(folder, folders);
  const real = placed(base, path);
  const stat = regular(real);
  const range = rangeOf(request.headers.range, stat.size);
  const { start, end } = range ?? { start: 0, end: stat.size - 1 };
  response.writeHead(range ? 206 : 200, {
    'content-type': 'application/octet-stream',
    'content-length': stat.size ? end - start + 1 : 0,
    'accept-ranges': 'bytes',
    ...(range ? { 'content-range': `bytes ${start}-${end}/${stat.size}` } : {}),
  });
  if (!stat.size) return void response.end();
  createReadStream(real, { start, end })
    .on('error', (error) => {
      console.error('a file of the workspace could not be sent', error);
      response.destroy(error);
    })
    .pipe(response);
};

/** A name a new entry takes, of one segment of a path. */
const nameOf = (name) => {
  if (
    typeof name !== 'string' ||
    !name.trim() ||
    Buffer.byteLength(name) > NAMED ||
    name === '.' ||
    name === '..' ||
    /[/\\\0]/.test(name)
  )
    throw new Refusal(400, 'invalid_file_name');
  return name;
};

/** The folder an entry stands in, followed to where it really lies, and the entry's own name:
    what a change touches is the entry, a link itself where the entry is one. */
const spotted = (base, path) => {
  const asked = askedPath(path).replace(/\/+$/, '');
  const name = basename(asked);
  if (!name || name === '.' || name === '..') throw new Refusal(400, 'invalid_path');
  const parent = placed(base, dirname(asked));
  return { parent, name, at: kept(base, join(parent, name)) };
};

/** A path a change may touch: never into what the listing hides at the project's top. */
const kept = (base, at) => {
  if (HIDDEN.has(relative(base, at).split(sep)[0])) throw new Refusal(403, 'outside');
  return at;
};

const present = (at) => {
  try {
    lstatSync(at);
    return true;
  } catch {
    return false;
  }
};

const missing = (at) => {
  if (!present(at)) throw new Refusal(404, 'file_missing');
};

const vacant = (at) => {
  if (present(at)) throw new Refusal(409, 'file_exists');
};

const folderOf = (base, path) => {
  const directory = placed(base, path ?? '');
  if (!statSync(directory).isDirectory()) throw new Refusal(400, 'not_a_folder');
  return directory;
};

const made = ({ folder, path, name }, folders) => {
  const base = baseOf(folder, folders);
  const at = kept(base, join(folderOf(base, path), nameOf(name)));
  vacant(at);
  mkdirSync(at);
  return { path: relative(base, at) };
};

const renamed = ({ folder, path, to }, folders) => {
  const base = baseOf(folder, folders);
  const from = spotted(base, path);
  missing(from.at);
  const into = spotted(base, to);
  nameOf(into.name);
  if (into.at === from.at || into.parent === from.at || into.parent.startsWith(`${from.at}${sep}`))
    throw new Refusal(400, 'invalid_path');
  vacant(into.at);
  renameSync(from.at, into.at);
  return { path: relative(base, into.at) };
};

const removed = ({ folder, paths }, folders) => {
  if (!Array.isArray(paths) || !paths.length || paths.length > REMOVED) throw new Refusal(400, 'invalid_paths');
  const base = baseOf(folder, folders);
  const spots = paths.map((path) => spotted(base, path));
  for (const { at } of spots) missing(at);
  for (const { at } of spots) rmSync(at, { recursive: true, force: true });
  return { removed: spots.length };
};

/** A file uploaded into a folder of the project from the request's body; one by its name already
    there is refused, and it appears whole or not at all. */
const put = async (request, address, folders) => {
  const base = baseOf(address.searchParams.get('folder'), folders);
  const directory = folderOf(base, address.searchParams.get('path'));
  const at = kept(base, join(directory, nameOf(address.searchParams.get('name'))));
  vacant(at);
  const partial = join(directory, `.${randomUUID()}.ponistra`);
  try {
    await pipeline(request, createWriteStream(partial, { flags: 'wx', mode: 0o644 }));
    linkSync(partial, at);
  } catch (error) {
    throw error.code === 'EEXIST' ? new Refusal(409, 'file_exists') : error;
  } finally {
    rmSync(partial, { force: true });
  }
  const now = statSync(at);
  return { path: relative(base, at), size: now.size, modified: now.mtime.toISOString() };
};

/** Answers a request under `/ponistra/files`, the JSON to send back, or null once the bytes of a
    file are on their way themselves. */
export const filesAnswered = async (request, path, address, bodyOf, folders, response) => {
  try {
    return await answered(request, path, address, bodyOf, folders, response);
  } catch (error) {
    throw denied(error);
  }
};

/** The names of the system's users or groups by their ids, as its file lists them. */
const namesIn = (file) => {
  const names = new Map();
  try {
    for (const line of readFileSync(file, 'utf8').split('\n')) {
      const [name, , id] = line.split(':');
      if (name && id) names.set(Number(id), name);
    }
  } catch {
    // A system without the file names nobody.
  }
  return names;
};

/** An entry itself, a link and not what it points at, with whom it belongs to and its mode. */
const statOf = (base, at) => {
  const own = lstatSync(at);
  const entry = entryOf(base, dirname(at), basename(at), own.isSymbolicLink());
  return {
    ...entry,
    path: relative(base, at),
    mode: own.mode & 0o7777,
    uid: own.uid,
    gid: own.gid,
    owner: namesIn('/etc/passwd').get(own.uid) ?? null,
    group: namesIn('/etc/group').get(own.gid) ?? null,
  };
};

const stated = (folder, path, folders) => {
  const base = baseOf(folder, folders);
  if (!askedPath(path).replace(/\/+$/, '')) return statOf(base, base);
  const { at } = spotted(base, path);
  missing(at);
  return statOf(base, at);
};

const whole = (value, most) => {
  if (!Number.isInteger(value) || value < 0 || value > most) throw new Refusal(400, 'invalid_value');
  return value;
};

/** The mode of the entry a path names, of what a link points at only where it stays inside. */
const moded = ({ folder, path, mode }, folders) => {
  const base = baseOf(folder, folders);
  const real = placed(base, path);
  kept(base, real);
  chmodSync(real, whole(mode, 0o7777));
  return statOf(base, real);
};

const owned = ({ folder, path, uid, gid }, folders) => {
  const base = baseOf(folder, folders);
  const { at } = spotted(base, path);
  missing(at);
  lchownSync(at, whole(uid, 0xffffffff), whole(gid, 0xffffffff));
  return statOf(base, at);
};

const CHANGES = {
  '/ponistra/files/folder': made,
  '/ponistra/files/rename': renamed,
  '/ponistra/files/remove': removed,
  '/ponistra/files/mode': moded,
  '/ponistra/files/owner': owned,
};

const answered = async (request, path, address, bodyOf, folders, response) => {
  const folder = address.searchParams.get('folder');
  const asked = address.searchParams.get('path');
  if (request.method === 'GET' && path === '/ponistra/files') return listed(folder, asked, folders);
  if (request.method === 'GET' && path === '/ponistra/files/read') return read(folder, asked, folders);
  if (request.method === 'GET' && path === '/ponistra/files/stat') return stated(folder, asked, folders);
  if (request.method === 'GET' && path === '/ponistra/files/raw') {
    sent(request, folder, asked, folders, response);
    return null;
  }
  if (request.method === 'POST' && path === '/ponistra/files/write') return written(await bodyOf(request, WRITE_BODY), folders);
  if (request.method === 'POST' && path === '/ponistra/files/put') return put(request, address, folders);
  if (request.method === 'POST' && CHANGES[path]) return CHANGES[path](await bodyOf(request, CHANGE_BODY), folders);
  throw new Refusal(404, 'not_found');
};
