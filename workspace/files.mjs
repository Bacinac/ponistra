// A project's files for PONISTRA's page of code (PJ6): a folder's entries, a file's text or its
// bytes, and a file written anew. Every path is taken relative to one of the workspace's project
// folders and followed to where it really lies, so neither `..` nor a symbolic link leads out of
// the project. A file is written only while it is still what the editor read (its hash), as a
// chat or another session may be writing the same tree.
import { createHash, randomUUID } from 'node:crypto';
import { chmodSync, createReadStream, readdirSync, readFileSync, realpathSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, sep } from 'node:path';
import { Refusal } from './chats.mjs';

export const FILES = /^\/ponistra\/files(\/(read|raw|write))?$/;
// Larger than this a file is only downloaded; the editor would hold it all in the page.
export const EDITED = 1024 * 1024;
export const WRITE_BODY = 4 * EDITED + 64 * 1024;
export const PATH = 4096;
const HIDDEN = new Set(['.git']);
const BY_NAME = new Intl.Collator('hr', { numeric: true, sensitivity: 'base' });

export const denied = (error) => (error.code === 'EACCES' || error.code === 'EPERM' ? new Refusal(403, 'not_permitted') : error);

export const hashOf = (bytes) => createHash('sha256').update(bytes).digest('hex');

const inside = (base, real) => real === base || real.startsWith(`${base}${sep}`);

/** The project's folder as the disk has it, only for a folder the workspace lists. */
const baseOf = (folder, folders) => {
  if (typeof folder !== 'string' || !folders().includes(folder)) throw new Refusal(404, 'unknown_folder');
  return realpathSync(folder);
};

/** A path asked within a place, which a text of no more than PATH characters names. */
export const askedPath = (path) => {
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

const entryOf = (base, directory, each) => {
  const at = join(directory, each.name);
  let stat;
  let outside = false;
  try {
    stat = statSync(at);
    if (each.isSymbolicLink()) outside = !inside(base, realpathSync(at));
  } catch {
    return { name: each.name, kind: 'broken', size: null, modified: null };
  }
  if (outside) return { name: each.name, kind: 'outside', size: null, modified: null };
  return {
    name: each.name,
    kind: stat.isDirectory() ? 'folder' : stat.isFile() ? 'file' : 'other',
    size: stat.isFile() ? stat.size : null,
    modified: stat.mtime.toISOString(),
  };
};

/** Folders first, then by name as Croatian orders it. */
export const ordered = (entries) =>
  entries.sort((one, other) =>
    (one.kind === 'folder') !== (other.kind === 'folder') ? (one.kind === 'folder' ? -1 : 1) : BY_NAME.compare(one.name, other.name),
  );

const listed = (folder, path, folders) => {
  const base = baseOf(folder, folders);
  const directory = placed(base, path ?? '');
  if (!statSync(directory).isDirectory()) throw new Refusal(400, 'not_a_folder');
  const entries = readdirSync(directory, { withFileTypes: true })
    .filter((each) => !(directory === base && HIDDEN.has(each.name)))
    .map((each) => entryOf(base, directory, each));
  return { path: relative(base, directory), entries: ordered(entries) };
};

const regular = (real) => {
  const stat = statSync(real);
  if (!stat.isFile()) throw new Refusal(400, 'not_a_file');
  return stat;
};

/** Text decodes as UTF-8 throughout and holds no NUL, which no text file writes. */
export const textOf = (bytes) => {
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
export const writtenBytes = (text, hash) => {
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

/** The file's bytes as they are, for PONISTRA to hand on as a download. */
const sent = (folder, path, folders, response) => {
  const base = baseOf(folder, folders);
  const real = placed(base, path);
  const stat = regular(real);
  response.writeHead(200, { 'content-type': 'application/octet-stream', 'content-length': stat.size });
  createReadStream(real)
    .on('error', (error) => {
      console.error('a file of the workspace could not be sent', error);
      response.destroy(error);
    })
    .pipe(response);
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

const answered = async (request, path, address, bodyOf, folders, response) => {
  const folder = address.searchParams.get('folder');
  const asked = address.searchParams.get('path');
  if (request.method === 'GET' && path === '/ponistra/files') return listed(folder, asked, folders);
  if (request.method === 'GET' && path === '/ponistra/files/read') return read(folder, asked, folders);
  if (request.method === 'GET' && path === '/ponistra/files/raw') {
    sent(folder, asked, folders, response);
    return null;
  }
  if (request.method === 'POST' && path === '/ponistra/files/write') return written(await bodyOf(request, WRITE_BODY), folders);
  throw new Refusal(404, 'not_found');
};
