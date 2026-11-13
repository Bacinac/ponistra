// The agent's memory as PONISTRA's page of code shows it (MEM1–MEM3): for each store
// `~/.claude/projects/<namespace>/memory/`, what its index `MEMORY.md` adds to every session, what is
// wrong with it read mechanically (as `.claude-config/tools/memory_health.py` reads it), and the
// fixes that need no model, each a whole new text of one file for PONISTRA to propose. A fix is
// written here only while the file is still what it was when it was read (its hash), atomically.
// Nothing here runs a model; PONISTRA hears when a store changes.
import { execFileSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import {
  existsSync,
  lstatSync,
  readdirSync,
  readFileSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  watch,
  writeFileSync,
} from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, isAbsolute, join, relative } from 'node:path';
import { Refusal } from './chats.mjs';

const ROOT = process.env.PONISTRA_ROOT;
const TOKEN = process.env.PONISTRA_WORKSPACE_TOKEN;
const TOLD = new URL('/api/memory/changed', process.env.PONISTRA_PUBLIC_URL);
const STORES = join(homedir(), '.claude', 'projects');
const INDEX = 'MEMORY.md';
// Claude Code reads this much of the index into every session and cuts the rest.
const LOADED_LINES = 200;
const LONG_INDEX = 145;
const INDEX_BLOAT = 26000;
// A rough count without a tokenizer: a token is about four bytes of UTF-8 for this mixed prose.
const BYTES_PER_TOKEN = 4;
const HOOK = 150;
const QUIET = 2000;
const LOCAL = 'Europe/Zagreb';
export const MEMORY = /^\/ponistra\/memory(\/(file|write))?$/;
const MEMORY_BODY = 512 * 1024;
const STORE = /^-[A-Za-z0-9._-]+$/;
// The global instructions, which an analysis may propose a rule for (MEM4).
const GLOBAL = 'global';
const INSTRUCTIONS = join(homedir(), '.claude', 'CLAUDE.md');
const FILE = /^[A-Za-z0-9][A-Za-z0-9._-]*\.md$/;

const FRONTMATTER = /^---\s*\n([\s\S]*?)\n---\s*\n/;
const WIKILINK = /\[\[([a-zA-Z0-9_][a-zA-Z0-9_\- ]*?)\]\]/g;
const POINTER = /\]\(([^)]+\.md)\)/g;
const TICKED = /`([^`\n]+)`/g;
// What a line says of its own work, not of changes in general ("necommitanih izmjena").
const UNCOMMITTED = /(na devu,? )?\bnecommitan(o|a|i|e|)\b/giu;
const UNPUSHED = /\bnepushan(o|a|i|e|)\b/giu;
// A time said in UTC, or several said together ("02:00 i 04:00 UTC"), each converted.
const UTC = /\b((?:\d{1,2}:\d{2}\s*(?:i|,|–|-|do)\s*)*\d{1,2}:\d{2})\s?UTC\b/g;
const CLOCK = /(\d{1,2}):(\d{2})/g;
const ZULU = /\b(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?Z\b/g;
const DAY = /\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b/;

export const hashOf = (text) => (text === null ? '' : createHash('sha256').update(text).digest('hex'));
const bytesOf = (text) => Buffer.byteLength(text, 'utf8');
const tokensOf = (text) => Math.ceil(bytesOf(text) / BYTES_PER_TOKEN);

const readText = (file) => {
  try {
    return readFileSync(file, 'utf8');
  } catch {
    return null;
  }
};

const git = (path, ...args) => {
  try {
    return execFileSync('git', ['-C', path, ...args], {
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'ignore'],
    });
  } catch {
    return null;
  }
};

// Each store once: the aliases of one (`-mnt-data-docker-*`) are symbolic links to it.
const storeNames = () => {
  if (!existsSync(STORES)) return [];
  return readdirSync(STORES, { withFileTypes: true })
    .filter((each) => each.isDirectory() && STORE.test(each.name) && existsSync(join(STORES, each.name, 'memory')))
    .map((each) => each.name)
    .filter((name) => !name.startsWith('-tmp'))
    .sort();
};

// A store belongs to the project whose folder its name spells, `/` written as `-`.
const projectFolders = () => {
  if (!ROOT || !existsSync(ROOT)) return [];
  const found = [ROOT];
  for (const each of readdirSync(ROOT, { withFileTypes: true }))
    if (each.isDirectory() && !each.name.startsWith('.') && existsSync(join(ROOT, each.name, '.git')))
      found.push(join(ROOT, each.name));
  return found;
};

const folderOf = (store, folders) => folders.find((path) => path.replaceAll('/', '-') === store) ?? null;

const frontOf = (text) => {
  const found = FRONTMATTER.exec(text);
  return found ? { block: found[1], end: found[0].length } : null;
};

const fieldOf = (block, key) => {
  const found = new RegExp(`^\\s*${key}:\\s*(.*)$`, 'm').exec(block);
  return found ? found[1].trim().replace(/^["']|["']$/g, '') : null;
};

const typeOf = (file) => {
  const kind = /^(user|feedback|project|reference)[_-]/.exec(file);
  return kind ? kind[1] : null;
};

const normalised = (name) => name.toLowerCase().replace(/\.md$/, '').replaceAll('_', '-').trim();

// What a repository's history says (commits, releases, the names it holds), kept for its head.
const histories = new Map();

const historyOf = (path, head) => {
  let history = histories.get(path);
  if (history?.head !== head) {
    history = { head, commits: new Map(), releases: new Map(), pushed: new Map(), words: null };
    histories.set(path, history);
  }
  return history;
};

// What a store's repository says, its tree read once for each scan.
class Repository {
  constructor(path) {
    this.path = path;
    this.head = (git(path, 'rev-parse', 'HEAD') ?? '').trim();
    this.changed = new Set();
    for (const entry of (git(path, 'status', '--porcelain=v1', '-z') ?? '').split('\0'))
      if (entry.length > 3) this.changed.add(entry.slice(3));
    this.files = (git(path, 'ls-files', '-z') ?? '').split('\0').filter(Boolean);
    // Each tail of each file's path and folder (`apps/x.py` for `backend/apps/x.py`), with the
    // first path it stands for: a memory names a path from wherever its work stood.
    this.tails = new Map();
    for (const file of this.files) {
      const parts = file.split('/');
      for (let start = 0; start < parts.length; start++)
        for (let end = start + 1; end <= parts.length; end++) {
          const tail = parts.slice(start, end).join('/');
          if (end === parts.length || start === 0 || end - start <= 2)
            if (!this.tails.has(tail)) this.tails.set(tail, end === parts.length ? file : parts.slice(0, end).join('/'));
        }
    }
    this.byName = new Map();
    for (const file of this.files) {
      const name = basename(file);
      this.byName.set(name, [...(this.byName.get(name) ?? []), file]);
    }
    this.key = `${this.head} ${createHash('sha256').update([...this.changed].sort().join('\n')).digest('hex')}`;
    this.history = historyOf(path, this.head);
    ({ commits: this.commits, releases: this.releases, pushed: this.pushed } = this.history);
  }

  // The repository's own path for a name the memory gives, relative or absolute.
  pathOf(name) {
    const inside = isAbsolute(name) ? relative(this.path, name) : name.replace(/^\.\//, '');
    if (inside.startsWith('..') || isAbsolute(inside)) return null;
    const bare = inside.replace(/\/$/, '');
    if (this.tails.has(bare)) return this.tails.get(bare);
    // What the repository ignores is still there to be named (`.env`, `volumes/`).
    return existsSync(join(this.path, bare)) ? bare : null;
  }

  isChanged(path) {
    for (const changed of this.changed) if (changed === path || changed.startsWith(`${path}/`)) return true;
    return false;
  }

  // The commit by which every path was committed since the day: the one that committed what was
  // said of them.
  committedSince(day, paths) {
    let last = null;
    for (const path of paths) {
      const key = `${day} ${path}`;
      if (!this.commits.has(key)) {
        const lines = git(this.path, 'log', '--reverse', `--since=${day}T00:00`, '--format=%h %ct', '--', path) ?? '';
        const [hash, at] = lines.split('\n')[0].split(' ');
        this.commits.set(key, hash ? { hash, at: Number(at) } : null);
      }
      const commit = this.commits.get(key);
      if (!commit) return null;
      if (!last || commit.at > last.at) last = commit;
    }
    return last?.hash ?? null;
  }

  releasedIn(hash) {
    if (!this.releases.has(hash)) {
      const tags = (git(this.path, 'tag', '--contains', hash, '--sort=v:refname', 'v*') ?? '').split('\n').filter(Boolean);
      this.releases.set(hash, tags[0]?.replace(/^v/, '') ?? null);
    }
    return this.releases.get(hash);
  }

  isPushed(hash) {
    if (!this.pushed.has(hash)) {
      const upstream = (git(this.path, 'rev-parse', '--abbrev-ref', '@{upstream}') ?? '').trim();
      this.pushed.set(hash, Boolean(upstream) && git(this.path, 'merge-base', '--is-ancestor', hash, upstream) !== null);
    }
    return this.pushed.get(hash);
  }

  // Every word and flag the repository's text holds, read once for its head.
  words() {
    if (!this.history.words) {
      const words = new Set();
      for (const file of this.files) {
        const path = join(this.path, file);
        let text;
        try {
          if (statSync(path).size > WORDS_FILE) continue;
          text = readFileSync(path, 'utf8');
        } catch {
          continue;
        }
        if (text.includes('\0')) continue;
        for (const found of text.matchAll(WORD)) words.add(found[0]);
      }
      this.history.words = words;
    }
    return this.history.words;
  }

  // Which of the names the memory gives (functions, flags) the repository still holds.
  holds(names) {
    if (!names.length) return new Set();
    const words = this.words();
    return new Set(names.filter((name) => words.has(name)));
  }
}

// A name in backticks that reads as a file's path (`deploy/`, `apps/x.py`, `start.sh`), a function
// or a flag; not a host, a dotted attribute or two words with a slash.
const PATHLIKE = /^[\w./-]+$/;
const CODE = /\.(py|pyi|ts|tsx|js|mjs|cjs|jsx|json|md|sh|ya?ml|toml|sql|css|html|svg|txt|conf|go|rs|svelte|ini|cfg|lock|in|kt|kts|xml|gradle|Dockerfile)$/;
const looksLikePath = (token) =>
  PATHLIKE.test(token) &&
  token.length > 3 &&
  !token.startsWith('.') &&
  CODE.test(token) &&
  !/\.(com|biz|hr|net|org|io)\b/.test(token);
const FUNCTION = /^([A-Za-z_][\w.]*)\(\)$/;
const WORD = /--[a-z][a-z0-9-]+|[A-Za-z_]\w*/g;
const WORDS_FILE = 2 * 1024 * 1024;
const FLAG = /^--[a-z][a-z0-9-]+$/;

const namesOf = (text) => [
  ...new Set(
    [...text.matchAll(TICKED)]
      .map((found) => found[1].trim())
      .map((token) => FUNCTION.exec(token)?.[1].split('.').pop() ?? (FLAG.test(token) ? token : null))
      .filter(Boolean),
  ),
];

const dayOf = (line) => {
  const found = DAY.exec(line);
  if (!found) return null;
  return found[1]
    ? `${found[3]}-${found[2].padStart(2, '0')}-${found[1].padStart(2, '0')}`
    : `${found[4]}-${found[5]}-${found[6]}`;
};

const localOf = (utc) => {
  if (Number.isNaN(utc.getTime())) return null;
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: LOCAL,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(utc)
      .map((part) => [part.type, part.value]),
  );
  return { day: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` };
};

// The body's lines outside fenced code, each with its offset, for fixes that go line by line.
const proseLines = (text, from) => {
  const lines = [];
  let fenced = false;
  let at = 0;
  for (const line of text.split('\n')) {
    if (/^\s*```/.test(line)) fenced = !fenced;
    else if (at >= from && !fenced) lines.push({ line, at });
    at += line.length + 1;
  }
  return lines;
};

const replacedLines = (text, from, change) => {
  let changed = false;
  let result = '';
  let last = 0;
  for (const { line, at } of proseLines(text, from)) {
    const next = change(line);
    if (next === line) continue;
    result += text.slice(last, at) + next;
    last = at + line.length;
    changed = true;
  }
  return changed ? result + text.slice(last) : text;
};

// "necommitano" where the repository holds every file the line names committed after that day.
const stateFixed = (text, from, repository, why) =>
  replacedLines(text, from, (line) => {
    const said = UNCOMMITTED.test(line) || UNPUSHED.test(line);
    UNCOMMITTED.lastIndex = 0;
    UNPUSHED.lastIndex = 0;
    const day = said && dayOf(line);
    if (!day) return line;
    const paths = [...line.matchAll(TICKED)]
      .map((found) => found[1].trim())
      .filter(looksLikePath)
      .map((token) => repository.pathOf(token))
      .filter(Boolean);
    if (!paths.length || paths.some((path) => repository.isChanged(path))) return line;
    const commit = repository.committedSince(day, [...new Set(paths)]);
    if (!commit) return line;
    const release = repository.releasedIn(commit);
    const pushed = release !== null || repository.isPushed(commit);
    let next = line.replace(UNCOMMITTED, (_all, dev, given) => {
      const ending = given.toLowerCase();
      const done = `commitan${ending} \`${commit}\``;
      if (release) return `${done}, izdan${ending || 'o'} u ${release}`;
      return dev ? `${dev}${done}` : done;
    });
    if (pushed)
      next = next.replace(UNPUSHED, (_all, given) =>
        release ? `izdan${given.toLowerCase()} u ${release}` : `pushan${given.toLowerCase()}`,
      );
    if (next !== line) why.add(commit);
    return next;
  });

// Outside backticks only: what stands in them is quoted as it is (a snapshot's name, a command).
const unticked = (line, change) =>
  line
    .split(/(`[^`\n]*`)/)
    .map((part) => (part.startsWith('`') && part.endsWith('`') && part.length > 1 ? part : change(part)))
    .join('');

// Only on the day its line names: a time without one recurs, and its local hour moves with summer
// time, so no one hour is right.
const timeFixed = (text, from) =>
  replacedLines(text, from, (line) => {
    const day = dayOf(line);
    return unticked(line, (part) =>
      part
        .replace(UTC, (all, times) => {
          if (!day) return all;
          let kept = true;
          const converted = times.replace(CLOCK, (_clock, hour, minute) => {
            const local = localOf(new Date(`${day}T${hour.padStart(2, '0')}:${minute}:00Z`));
            // The line names the day, which would no longer be the local one.
            if (local?.day !== day) kept = false;
            return local?.time ?? '';
          });
          return kept ? converted : all;
        })
        .replace(ZULU, (all, year, month, date, hour, minute) => {
          const local = localOf(new Date(`${year}-${month}-${date}T${hour}:${minute}:00Z`));
          return local ? `${local.day} ${local.time}` : all;
        }),
    );
  });

const pathsFixed = (text, from, repository, stale) =>
  replacedLines(text, from, (line) =>
    line.replace(TICKED, (all, token) => {
      const name = token.trim();
      if (!looksLikePath(name) || name.includes('*') || isAbsolute(name)) return all;
      if (repository.pathOf(name)) return all;
      // The file the path meant, if one alone keeps its name under the folders it names, in order.
      const folders = name.split('/').slice(0, -1).filter((part) => !/^\.+$/.test(part));
      const candidates = (repository.byName.get(basename(name)) ?? []).filter((file) => {
        const parts = file.split('/');
        let at = 0;
        return folders.every((folder) => {
          at = parts.indexOf(folder, at) + 1;
          return at > 0;
        });
      });
      stale.add(name);
      return candidates.length === 1 ? `\`${candidates[0]}\`` : all;
    }),
  );

// A link is fixed only where its name, spelt loosely, leads to one memory alone.
const linksFixed = (text, targets) => {
  const byNormal = new Map();
  for (const [target, file] of targets) {
    const key = normalised(target);
    byNormal.set(key, byNormal.has(key) && byNormal.get(key) !== file ? null : file);
  }
  return text.replace(WIKILINK, (all, name) => {
    const link = name.trim();
    if (targets.has(link)) return all;
    const file = byNormal.get(normalised(link));
    return file ? `[[${targets.canonical.get(file)}]]` : all;
  });
};

const frontFixed = (text, file) => {
  const front = frontOf(text);
  const stem = file.replace(/\.md$/, '');
  const kind = typeOf(file);
  if (!front) return text;
  let block = front.block;
  if (!(fieldOf(block, 'name') ?? '')) block = `name: ${stem.replaceAll('_', '-')}\n${block}`;
  if (!fieldOf(block, 'type') && kind) {
    block = /^metadata:\s*$/m.test(block)
      ? block.replace(/^metadata:\s*$/m, `metadata:\n  type: ${kind}`)
      : `${block}\nmetadata:\n  type: ${kind}`;
  }
  return block === front.block ? text : `---\n${block}\n---\n${text.slice(front.end)}`;
};

// Only what recall needs most earns a line of its own (`memory_health.py`): the index is curated,
// read into every session and cut at LOADED_LINES.
const INDEXED = /^(feedback|reference|user)[_-]/;

const pointsAt = (directory, pointer) => existsSync(join(directory, pointer));

const indexFixed = (directory, index, files, texts) => {
  const lines = index.split('\n');
  const kept = lines.filter((line) => {
    const pointers = [...line.matchAll(POINTER)].map((found) => found[1]);
    return !pointers.length || pointers.some((pointer) => pointsAt(directory, pointer));
  });
  while (kept.length && kept[kept.length - 1] === '') kept.pop();
  const missing = files
    .filter((file) => INDEXED.test(file) && !index.includes(`](${file})`))
    .slice(0, Math.max(0, LONG_INDEX - kept.length));
  for (const file of missing) {
    const front = frontOf(texts.get(file) ?? '');
    const said = (front && fieldOf(front.block, 'description')) || '';
    const hook = said.length > HOOK ? `${said.slice(0, HOOK - 1)}…` : said;
    const title = (front && fieldOf(front.block, 'name')) || file.replace(/\.md$/, '');
    kept.push(hook ? `- [${title}](${file}) — ${hook}` : `- [${title}](${file})`);
  }
  const fixed = `${kept.join('\n')}\n`;
  return fixed.trimEnd() === index.trimEnd() ? index : fixed;
};

// What one file proposes and finds is kept while it, and its repository, stay as they were.
const known = new Map();

const fileRead = (store, file, text, targets, repository) => {
  const key = `${hashOf(text)} ${repository?.key ?? ''} ${targets.key}`;
  const kept = known.get(`${store}/${file}`);
  if (kept?.key === key) return kept;
  const findings = [];
  const proposals = [];
  const front = frontOf(text);
  const from = front?.end ?? 0;
  if (!front) findings.push({ kind: 'frontmatter', detail: 'none' });
  else {
    const absent = ['name', 'description', 'type'].filter((field) => !(fieldOf(front.block, field) ?? ''));
    if (absent.length) findings.push({ kind: 'frontmatter', detail: absent.join(', ') });
  }
  for (const found of text.matchAll(WIKILINK)) {
    const link = found[1].trim();
    if (!targets.has(link)) findings.push({ kind: 'link', detail: link });
  }
  const limit = /^(feedback|reference)[_-]/.test(file) ? 8000 : 25000;
  if (bytesOf(text) > limit) findings.push({ kind: 'oversize', detail: String(bytesOf(text)) });
  const propose = (kind, after, detail = '') => {
    if (after !== text) proposals.push({ kind, after, detail });
  };
  propose('frontmatter', frontFixed(text, file));
  propose('link', linksFixed(text, targets));
  propose('time', timeFixed(text, from));
  if (repository) {
    const why = new Set();
    propose('state', stateFixed(text, from, repository, why), [...why].join(' '));
    const stale = new Set();
    propose('path', pathsFixed(text, from, repository, stale), [...stale].join(' '));
    for (const name of stale) findings.push({ kind: 'stale', detail: name });
    const named = namesOf(text.slice(from));
    const held = repository.holds(named);
    for (const name of named) if (!held.has(name)) findings.push({ kind: 'stale', detail: name });
  }
  const read = { key, findings, proposals };
  known.set(`${store}/${file}`, read);
  return read;
};

const storeRead = (store, folders, repositories) => {
  const directory = join(STORES, store, 'memory');
  const folder = folderOf(store, folders);
  let repository = null;
  if (folder) {
    repository = repositories.get(folder) ?? new Repository(folder);
    repositories.set(folder, repository);
  }
  const files = readdirSync(directory)
    .filter((name) => FILE.test(name) && name !== INDEX && !name.startsWith('_'))
    .sort();
  const texts = new Map();
  const hashes = {};
  const findings = [];
  const proposals = [];
  // Each name a link may give, the file's stem and its `name`, with the file it leads to.
  const targets = new Map();
  targets.canonical = new Map();
  let bytes = 0;
  for (const file of files) {
    const text = readText(join(directory, file));
    if (text === null) {
      findings.push({ file, kind: 'unreadable', detail: '' });
      continue;
    }
    texts.set(file, text);
    hashes[file] = hashOf(text);
    bytes += bytesOf(text);
    const stem = file.replace(/\.md$/, '');
    const front = frontOf(text);
    const name = front && fieldOf(front.block, 'name');
    targets.set(stem, file);
    if (name) targets.set(name, file);
    targets.canonical.set(file, name || stem);
  }
  targets.key = hashOf([...targets.keys()].sort().join('\n'));
  for (const [file, text] of texts) {
    const read = fileRead(store, file, text, targets, repository);
    for (const finding of read.findings) findings.push({ file, ...finding });
    for (const proposal of read.proposals) proposals.push({ store, file, hash: hashes[file], before: text, ...proposal });
  }
  const index = readText(join(directory, INDEX));
  hashes[INDEX] = hashOf(index);
  let shown = null;
  if (index !== null) {
    const lines = index.split('\n');
    while (lines.length && lines[lines.length - 1] === '') lines.pop();
    const loaded = lines.slice(0, LOADED_LINES).join('\n');
    shown = {
      lines: lines.length,
      bytes: bytesOf(index),
      tokens: tokensOf(loaded),
      cut: Math.max(0, lines.length - LOADED_LINES),
    };
    for (const file of files) if (!index.includes(`](${file})`)) findings.push({ file, kind: 'orphan', detail: '' });
    for (const found of index.matchAll(POINTER))
      if (!pointsAt(directory, found[1])) findings.push({ file: INDEX, kind: 'dangling', detail: found[1] });
    if (lines.length > LONG_INDEX || bytesOf(index) > INDEX_BLOAT)
      findings.push({ file: INDEX, kind: 'long', detail: String(lines.length) });
    const after = indexFixed(directory, index, [...texts.keys()], texts);
    if (after !== index) proposals.push({ store, file: INDEX, hash: hashes[INDEX], before: index, kind: 'index', after, detail: '' });
    const linked = linksFixed(index, targets);
    if (linked !== index) proposals.push({ store, file: INDEX, hash: hashes[INDEX], before: index, kind: 'link', after: linked, detail: '' });
  }
  return {
    summary: { store, folder, files: texts.size, bytes, index: shown, findings, hashes },
    proposals,
  };
};

export const memoryRead = () => {
  const folders = projectFolders();
  const repositories = new Map();
  const stores = [];
  const proposals = [];
  for (const store of storeNames()) {
    const read = storeRead(store, folders, repositories);
    stores.push(read.summary);
    proposals.push(...read.proposals);
  }
  return { root: ROOT, stores, proposals, global: { hash: hashOf(readText(INSTRUCTIONS)) } };
};

// A store's file by the names PONISTRA gives, refused unless it is one of the store's own.
const fileAt = (store, file) => {
  if (store === GLOBAL && file === 'CLAUDE.md') return realpathSync(INSTRUCTIONS);
  if (typeof store !== 'string' || !STORE.test(store) || typeof file !== 'string' || !FILE.test(file))
    throw new Refusal(400, 'invalid_file');
  const directory = join(STORES, store, 'memory');
  if (!existsSync(directory) || lstatSync(join(STORES, store)).isSymbolicLink()) throw new Refusal(404, 'no_store');
  const path = join(directory, file);
  if (existsSync(path) && (lstatSync(path).isSymbolicLink() || dirname(realpathSync(path)) !== realpathSync(directory)))
    throw new Refusal(400, 'invalid_file');
  return path;
};

const fileOf = (store, file) => {
  const text = readText(fileAt(store, file));
  return { text, hash: hashOf(text) };
};

// The new text in place of the one PONISTRA read, or the file gone for null; a file that changed
// since is left as it is and refused.
const written = ({ store, file, hash, text }) => {
  const path = fileAt(store, file);
  if (typeof hash !== 'string' || (text !== null && typeof text !== 'string')) throw new Refusal(400, 'invalid_write');
  if (hashOf(readText(path)) !== hash) throw new Refusal(409, 'changed');
  if (text === null) {
    rmSync(path, { force: true });
    return { hash: '' };
  }
  const temporary = join(dirname(path), `.${basename(path)}.${randomUUID()}`);
  writeFileSync(temporary, text, { mode: existsSync(path) ? statSync(path).mode : 0o644 });
  renameSync(temporary, path);
  return { hash: hashOf(text) };
};

export const memoryAnswered = async (request, path, address, bodyOf) => {
  if (request.method === 'GET' && path === '/ponistra/memory') return memoryRead();
  if (request.method === 'GET' && path === '/ponistra/memory/file')
    return fileOf(address.searchParams.get('store'), address.searchParams.get('file'));
  if (request.method === 'POST' && path === '/ponistra/memory/write') return written(await bodyOf(request, MEMORY_BODY));
  throw new Refusal(404, 'not_found');
};

// PONISTRA hears that a store changed, once the writing settles.
let waiting = null;
const tell = async () => {
  waiting = null;
  try {
    const answer = await fetch(TOLD, { method: 'POST', headers: { authorization: `Bearer ${TOKEN}` } });
    if (!answer.ok) console.error(`PONISTRA refused the change of the memory: ${answer.status}`);
  } catch (error) {
    console.error('PONISTRA was not told of the change of the memory', error);
  }
};

const watched = new Map();
const followStores = () => {
  for (const store of storeNames()) {
    const directory = join(STORES, store, 'memory');
    if (watched.has(directory)) continue;
    const watcher = watch(directory, (_event, name) => {
      if (name && FILE.test(name)) waiting ??= setTimeout(tell, QUIET);
    });
    watcher.on('error', () => {
      watcher.close();
      watched.delete(directory);
    });
    watched.set(directory, watcher);
  }
};

export const followMemory = () => {
  followStores();
  setInterval(followStores, 60 * 1000).unref();
};
