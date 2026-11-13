// What the workspace holds, for PONISTRA's page of code: its projects, each one's latest chats and
// its rounds of chats, read from the disk on every request, so that nothing has to be kept in step
// with it. Whether a chat is open and what it is doing comes from the agent's own register of its
// running sessions; when that or a round changes, PONISTRA is told, and its page reads again.
//
// A round is a file `~/.claude/ponistra-rounds/<round>.json` (`nastavi` makes it, `objedini` closes
// it): {round, folder, coordinator, created, started, closed, chats: [{prompt, sessionId}], named,
// ended, left, auto}. Between the two this service alone writes it: once the round is started it
// starts each chat (chats.mjs) and names its session, once it is closed it ends them, and its
// coordinator once that is idle, unless it leads another round still open. The chats' panels
// read it from the browser, behind the workspace's door and so without the token, and draw the
// round as a group of sessions.
//
// What the owner asks from PONISTRA's page of code is a command (D52), a file
// `~/.claude/ponistra-commands/<id>.json` {id, kind, folder, round, session, text, images, label,
// auto, state, error, created, at}, which this service carries out itself (KR19): a chat runs here,
// without the editor. What goes into a chat running in the editor waits there until it is idle,
// and is then taken over here. Each command moves from sent to done or failed, and PONISTRA hears
// every move with the next change. A chat says when it answered or waits on its owner through
// Claude Code's hooks (heard.mjs), kept in `~/.claude/ponistra-heard/<session>.json`.
//
// Each project also says how its gate last went (`.git/ponistra-check`, written by its check
// scripts) and each chat how much context it holds and what it has changed in the tree; the
// workspace says whether it can be restarted without cutting work short, and restarts itself. It
// also says how much of the plan's limits the owner's chats have used (KR21).
import { execFileSync } from 'node:child_process';
import { createHash, randomUUID, timingSafeEqual } from 'node:crypto';
import {
  appendFileSync,
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readdirSync,
  readFileSync,
  readlinkSync,
  readSync,
  renameSync,
  rmSync,
  statSync,
  watch,
  writeFileSync,
} from 'node:fs';
import { createServer } from 'node:http';
import { homedir } from 'node:os';
import { join, relative } from 'node:path';
import {
  answer as answered,
  askedOf,
  begun,
  choose,
  chosenOf,
  culled,
  ended,
  hostedChats,
  isHosted,
  Refusal,
  registered,
  released,
  rename,
  resumed,
  say,
  interrupt,
  measured,
  modelsOf,
  takenOver,
  usageOf,
} from './chats.mjs';
import { hostOf } from './host.mjs';
import { followMemory, MEMORY, memoryAnswered } from './memory.mjs';
import { TERMINAL, upgraded } from './terminal.mjs';

const ROOT = process.env.PONISTRA_ROOT;
const TOKEN = process.env.PONISTRA_WORKSPACE_TOKEN;
const TOLD = new URL('/api/workspace/changed', process.env.PONISTRA_PUBLIC_URL);
const AGENT = join(homedir(), '.claude');
const SESSIONS = join(AGENT, 'sessions');
const ROUNDS = join(AGENT, 'ponistra-rounds');
const COMMANDS = join(AGENT, 'ponistra-commands');
const HEARD = join(AGENT, 'ponistra-heard');
// The chats the owner archived, {id, label, at}, which leave the page once their tabs are closed;
// a window that loads closes the tabs it brings back with their labels.
const ARCHIVED = join(AGENT, 'ponistra-archived.json');
const KEPT_ARCHIVED = 1000;
// Longer than the window's grace for tabs it brings back (phone/extension.js, REVIVING), so a chat
// revived with them and closed again stays archived.
const REOPENED = 2 * 60 * 1000;
const CHATS = 5;
const TITLE = 100;
const TRIED = 20;
const TAIL = 512 * 1024;
const QUIET = 300;
// A closed round stays this long, so that every browser's panels take its group away.
const KEPT_CLOSED = 7 * 24 * 60 * 60 * 1000;
const SESSION = /^[0-9a-f-]{36}$/;
const TRANSCRIPT = /^[0-9a-f-]{36}\.jsonl$/;
const ROUND = '[A-Za-z0-9._-]{1,100}';
const STATES = { busy: 'working', waiting: 'waiting', idle: 'idle' };
// What the coordinator is asked to do, as the word it is sent.
const ASKED = { consolidate: 'objedini', push: 'pushaj' };
// What goes into a chat's process, which waits while the chat works in the editor.
const CARRIED = new Set(['say', 'rename', 'model', ...Object.keys(ASKED)]);
const KINDS = new Set([...CARRIED, 'chat', 'answer', 'open', 'close', 'archive', 'start', 'auto', 'restart', 'stop', 'move']);
const COMMAND = /^(\d{1,18})\.json$/;
// A command for a chat that works in the editor all this long fails.
const UNTAKEN = 60 * 60 * 1000;
const KEPT_SETTLED = 24 * 60 * 60 * 1000;
// How far back one page of a conversation reads to reach its owner's words, a chat's tools'
// output running to megabytes between them.
const PAGE_TURNS = 2;
const PAGE_READ = 16 * 1024 * 1024;
// Four images of 5 MB each, as base64, besides the words.
const COMMAND_BODY = 28 * 1024 * 1024;
const IMAGE_TYPES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp']);
const IMAGES = 4;
const TOOL = 120;
// Claude Code's own cut of a session's title for the tab that holds it.
const tabLabel = (title) => (title.length > 25 ? `${title.substring(0, 24)}…` : title);
const CHECKS = join('.git', 'ponistra-check');
// The files whose change moves what the page shows of a gate; its logs change all through a run.
const GATE_FILES = new Set(['passed', 'pushed', 'browser', 'full', 'failed.json']);
const LOGS = new Set(['full.log', 'browser.log']);
const LAG = 5000;
const OUTCOME = /^([0-9a-f]{40}) (passed|failed) (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$/;
const EDITS = new Set(['Edit', 'MultiEdit', 'Write', 'NotebookEdit']);
const SCRIPTS = { 'check-full.sh': 'check-full', 'release.sh': 'release' };
const SOCKET = '/var/run/docker.sock';

const digest = (text) => createHash('sha256').update(text).digest();
const allowed = (header) => timingSafeEqual(digest(header ?? ''), digest(`Bearer ${TOKEN}`));

const readJson = (file) => {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
};

const writeJson = (file, value) => {
  const written = `${file}.${process.pid}`;
  writeFileSync(written, `${JSON.stringify(value, null, 2)}\n`);
  renameSync(written, file);
};

const linesOf = (file, from, length) => {
  const buffer = Buffer.alloc(length);
  const handle = openSync(file, 'r');
  try {
    readSync(handle, buffer, 0, length, from);
  } finally {
    closeSync(handle);
  }
  return buffer.toString('utf8').split('\n');
};

// A transcript runs to tens of megabytes, and its title is written again with every turn.
const tailOf = (file, size) => linesOf(file, Math.max(0, size - TAIL), Math.min(size, TAIL));

const parsed = (line) => {
  try {
    return JSON.parse(line);
  } catch {
    return null;
  }
};

// The name the owner gave a session outranks the one the agent made up for it.
const titleOf = (lines) => {
  let made = null;
  let prompt = null;
  for (let at = lines.length - 1; at >= 0; at--) {
    const line = lines[at];
    if (!line.includes('-title"') && !line.includes('"last-prompt"')) continue;
    const entry = parsed(line);
    if (entry?.type === 'custom-title' && entry.customTitle) return entry.customTitle;
    if (entry?.type === 'ai-title' && entry.aiTitle) made ??= entry.aiTitle;
    if (entry?.type === 'last-prompt' && entry.lastPrompt) prompt ??= entry.lastPrompt;
  }
  return made ?? (prompt && prompt.slice(0, 80));
};

// What the session's last answer was given to read, which is what its next one costs.
const contextOf = (lines) => {
  for (let at = lines.length - 1; at >= 0; at--) {
    const line = lines[at];
    if (!line.includes('"type":"assistant"') || !line.includes('"usage"')) continue;
    const entry = parsed(line);
    const usage = entry?.message?.usage;
    if (!usage || entry.isSidechain) continue;
    return (
      (usage.input_tokens ?? 0) +
      (usage.cache_creation_input_tokens ?? 0) +
      (usage.cache_read_input_tokens ?? 0) +
      (usage.output_tokens ?? 0)
    );
  }
  return null;
};

// The model the session runs on: the one its owner last chose here, or else the one that gave its
// last answer (Claude Code writes `<synthetic>` for an answer no model gave).
const modelOf = (id, lines) => {
  const chosen = chosenOf(id);
  if (chosen) return chosen;
  for (let at = lines.length - 1; at >= 0; at--) {
    const line = lines[at];
    if (!line.includes('"type":"assistant"') || !line.includes('"model"')) continue;
    const entry = parsed(line);
    const model = entry?.message?.model;
    if (typeof model === 'string' && !model.startsWith('<') && !entry.isSidechain) return model;
  }
  return null;
};

// What the harness wraps around the owner's words is no part of what they said.
const plain = (text) =>
  String(text)
    .replace(/<(system-reminder|command-[a-z-]+|local-command-[a-z-]+|ide_[a-z_]+)>[\s\S]*?<\/\1>/g, '')
    .trim();

const toolOf = ({ name, input }) => {
  const what = input?.description ?? input?.command ?? input?.file_path ?? input?.pattern ?? input?.skill ?? '';
  const line = String(what).split('\n')[0].slice(0, TOOL);
  return line ? `${name}: ${line}` : String(name);
};

const tagged = (text, tag) => text.match(new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`))?.[1].trim() ?? '';

// What the harness puts in the owner's place: a background task's notice and another session's
// message become a line of the conversation's own; a summary of what was compacted, the
// harness's other notices and what a skill hands the agent are no part of it.
const harnessed = (entry, text) => {
  if (entry.isCompactSummary) return { kind: 'compacted' };
  if (entry.origin?.kind === 'task-notification' || text.startsWith('<task-notification>'))
    return { kind: 'task', text: tagged(text, 'summary') };
  const peer = text.match(/<cross-session-message\b[^>]*?\bfrom-name="([^"]*)"/);
  if (entry.origin?.kind === 'peer' || peer) return { kind: 'peer', text: peer?.[1] ?? '' };
  if (entry.isMeta || /^\[Cross-session [a-z ]+\]/.test(text)) return { kind: null };
  return undefined;
};

// The owner's and the agent's words in the order said, each tool the agent used by its name, what
// the harness told the agent as a line of its own, and how many images the owner sent with words.
const saidIn = (lines) => {
  const said = [];
  for (const line of lines) {
    const queued = line.includes('"type":"queued_command"');
    if (!queued && !line.includes('"type":"user"') && !line.includes('"type":"assistant"')) continue;
    let entry = parsed(line);
    if (!entry || entry.isSidechain) continue;
    // Words the owner sent while the agent worked reach it inside its turn, kept as an attachment.
    if (queued && entry.attachment?.type === 'queued_command' && entry.attachment.commandMode === 'prompt')
      entry = { type: 'user', timestamp: entry.attachment.timestamp ?? entry.timestamp, message: { content: entry.attachment.prompt } };
    if (entry.type !== 'user' && entry.type !== 'assistant') continue;
    const content = entry.message?.content;
    const blocks = typeof content === 'string' ? [{ type: 'text', text: content }] : Array.isArray(content) ? content : [];
    const at = entry.timestamp ?? null;
    if (entry.type === 'user') {
      const first = blocks.find((block) => block?.type === 'text');
      const harness = harnessed(entry, first ? String(first.text).trim() : '');
      if (harness) {
        if (harness.kind) said.push({ role: 'harness', kind: harness.kind, text: harness.text ?? '', at });
        continue;
      }
    } else if (entry.isMeta) continue;
    const images = entry.type === 'user' ? blocks.filter((block) => block?.type === 'image').length : 0;
    const before = said.length;
    for (const block of blocks) {
      if (block?.type === 'text') {
        const text = plain(block.text);
        if (text) said.push({ role: entry.type, text, at });
      } else if (block?.type === 'tool_use' && entry.type === 'assistant') {
        said.push({ role: 'tool', text: toolOf(block), at });
      }
    }
    if (images && said.length > before) said[before].images = images;
    else if (images) said.push({ role: 'user', text: '', at, images });
  }
  return said;
};

const lastSaid = (lines) => {
  for (let at = lines.length - 1; at >= 0; at--) {
    if (!lines[at].includes('"type":"assistant"') || !lines[at].includes('"type":"text"')) continue;
    const found = saidIn([lines[at]]).findLast((each) => each.role === 'assistant');
    if (found) return found.text;
  }
  return null;
};

// The files a session wrote, read on from where the last request stopped, as a transcript only grows.
const edited = new Map();

const editsOf = (file) => {
  if (!existsSync(file)) return new Set();
  const size = statSync(file).size;
  let kept = edited.get(file);
  if (!kept || kept.offset > size) {
    kept = { offset: 0, files: new Set() };
    edited.set(file, kept);
  }
  if (kept.offset === size) return kept.files;
  const buffer = Buffer.alloc(size - kept.offset);
  const handle = openSync(file, 'r');
  try {
    readSync(handle, buffer, 0, buffer.length, kept.offset);
  } finally {
    closeSync(handle);
  }
  const whole = buffer.lastIndexOf(0x0a) + 1;
  kept.offset += whole;
  for (const line of buffer.subarray(0, whole).toString('utf8').split('\n')) {
    if (!line.includes('"tool_use"')) continue;
    const entry = parsed(line);
    const content = entry?.message?.content;
    if (entry?.isSidechain || !Array.isArray(content)) continue;
    for (const block of content) {
      const path = block?.input?.file_path ?? block?.input?.notebook_path;
      if (block?.type === 'tool_use' && EDITS.has(block.name) && typeof path === 'string') kept.files.add(path);
    }
  }
  return kept.files;
};

const git = (path, ...args) =>
  execFileSync('git', ['-C', path, ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] });

// What is changed in a project's tree and not committed, by file, read once for each request.
const treeOf = (path) => {
  const changed = new Map();
  try {
    for (const line of git(path, 'diff', '--numstat', 'HEAD').split('\n')) {
      const [added, removed, file] = line.split('\t');
      if (file) changed.set(file, { added: Number(added) || 0, removed: Number(removed) || 0 });
    }
    for (const file of git(path, 'ls-files', '--others', '--exclude-standard', '-z').split('\0'))
      if (file) changed.set(file, { added: null, removed: 0 });
  } catch {
    return null;
  }
  return changed;
};

const linesIn = (file) => {
  try {
    const text = readFileSync(file);
    return text.includes(0) ? 0 : text.toString('utf8').split('\n').length - (text.at(-1) === 0x0a ? 1 : 0);
  } catch {
    return 0;
  }
};

// The share of the tree's uncommitted change that is in the files this session wrote.
const changesOf = (path, transcript, trees) => {
  if (!trees.has(path)) trees.set(path, treeOf(path));
  const tree = trees.get(path);
  if (!tree) return null;
  const changes = { files: 0, added: 0, removed: 0 };
  for (const file of editsOf(transcript)) {
    const name = relative(path, file);
    const change = tree.get(name);
    if (name.startsWith('..') || !change) continue;
    changes.files += 1;
    changes.added += change.added ?? linesIn(file);
    changes.removed += change.removed;
  }
  return changes;
};

const keptIn = (path) => join(AGENT, 'projects', path.replace(/[^a-zA-Z0-9]/g, '-'));
const transcriptOf = (folder, id) => join(keptIn(folder), `${id}.jsonl`);

// Each running session by its latest process; what a chat run here waits on, the register does not
// know, nor that a chat just started here works before it has registered or read its message.
// The sessions with a shell of their Bash tool alive: a turn ends while a command it ran in the
// background goes on, and the registry then calls the session idle.
const shelled = () => {
  const parents = new Set();
  for (const pid of readdirSync('/proc')) {
    if (!/^\d+$/.test(pid)) continue;
    try {
      if (!readFileSync(`/proc/${pid}/cmdline`, 'utf8').includes('/shell-snapshots/snapshot-')) continue;
      const stat = readFileSync(`/proc/${pid}/stat`, 'utf8');
      parents.add(Number(stat.slice(stat.lastIndexOf(')') + 2).split(' ')[1]));
    } catch {
      // Gone between the listing and the read.
    }
  }
  return parents;
};

const running = () => {
  const found = new Map();
  const here = new Map(hostedChats().map((chat) => [chat.session, chat]));
  const shells = shelled();
  for (const [session, entries] of registered()) {
    const entry = entries.at(-1);
    const asked = askedOf(session);
    const answering = here.get(session)?.answering;
    const state = asked ? 'waiting' : answering ? 'working' : (STATES[entry.status] ?? 'working');
    found.set(session, {
      name: entry.name ?? null,
      state: state === 'idle' && shells.has(entry.pid) ? 'background' : state,
      waitingFor: asked ? asked.waitingFor : entry.status === 'waiting' ? (entry.waitingFor ?? null) : null,
      at: asked ? asked.at : new Date(entry.statusUpdatedAt ?? entry.updatedAt ?? entry.startedAt ?? Date.now()).toISOString(),
      cwd: entry.cwd,
      startedAt: entry.startedAt,
      hosted: here.has(session),
    });
  }
  for (const { session, folder, asked } of here.values()) {
    if (found.has(session)) continue;
    found.set(session, {
      name: null,
      state: asked ? 'waiting' : 'working',
      waitingFor: asked?.waitingFor ?? null,
      at: asked?.at ?? new Date().toISOString(),
      cwd: folder,
      startedAt: Date.now(),
      hosted: true,
    });
  }
  return found;
};

const archivedList = () => readJson(ARCHIVED) ?? [];

// A chat archived and since started again, and left open, is no longer archived; till then it stays
// off the page though it runs, as a window that loads revives the tabs of chats archived since.
const archived = (live) => {
  const kept = archivedList();
  const since = Date.now() - REOPENED;
  const now = kept.filter(({ id, at }) => {
    const started = live.get(id)?.startedAt;
    return !(started > at && started < since);
  });
  if (now.length !== kept.length) writeJson(ARCHIVED, now);
  return new Set(now.map(({ id }) => id));
};

const archive = (chats) => {
  const ids = new Set(chats.map(({ id }) => id));
  const at = Date.now();
  const kept = archivedList().filter((each) => !ids.has(each.id));
  writeJson(ARCHIVED, [...kept, ...chats.map(({ id, label }) => ({ id, label, at }))].slice(-KEPT_ARCHIVED));
};

const labelOf = (transcript) => {
  if (!existsSync(transcript)) return null;
  const title = titleOf(tailOf(transcript, statSync(transcript).size));
  return title ? tabLabel(title) : null;
};

// Each chat of a round, closed rounds' included, by its coordinator; a chat moved on from a closed
// round is shown under the round it is in now.
const coordinators = () => {
  const found = new Map();
  for (const { round } of roundFiles().sort((one, other) => Boolean(other.round.closed) - Boolean(one.round.closed))) {
    if (typeof round.coordinator !== 'string') continue;
    for (const chat of round.chats) if (chat?.sessionId) found.set(chat.sessionId, round.coordinator);
  }
  return found;
};

// Only an open chat's changes are read: its transcript is read whole, once and then as it grows.
const chatOf = (path, id, live, trees, led) => {
  const transcript = transcriptOf(path, id);
  if (!existsSync(transcript)) return null;
  const stat = statSync(transcript);
  const lines = tailOf(transcript, stat.size);
  const title = titleOf(lines);
  if (!title) return null;
  const session = live.get(id);
  return {
    id,
    title,
    at: stat.mtime.toISOString(),
    open: Boolean(session),
    hosted: session?.hosted ?? false,
    state: session?.state ?? 'closed',
    waitingFor: session?.waitingFor ?? null,
    context: contextOf(lines),
    model: modelOf(id, lines),
    changes: session ? changesOf(path, transcript, trees) : null,
    coordinator: led.get(id) ?? null,
  };
};

// The latest chats, each with the rest of its round's group, so that a coordinator is shown with
// its chats.
const chatsOf = (path, live, trees, held) => {
  const kept = keptIn(path);
  if (!existsSync(kept)) return [];
  const gone = archived(live);
  const led = coordinators();
  const shown = (id) => !held.has(id) && !gone.has(id);
  const ids = readdirSync(kept)
    .filter((name) => TRANSCRIPT.test(name))
    .map((name) => ({ id: name.slice(0, -'.jsonl'.length), at: statSync(join(kept, name)).mtimeMs }))
    .sort((one, other) => other.at - one.at)
    .slice(0, TRIED)
    .map(({ id }) => id);
  const chats = new Map();
  for (const id of ids) {
    if (chats.size === CHATS) break;
    if (!shown(id)) continue;
    const chat = chatOf(path, id, live, trees, led);
    if (chat) chats.set(id, chat);
  }
  for (const chat of [...chats.values()]) {
    const lead = chat.coordinator ?? chat.id;
    const group = [lead, ...[...led].filter(([, coordinator]) => coordinator === lead).map(([id]) => id)];
    for (const id of group) {
      if (chats.has(id) || !shown(id)) continue;
      const found = chatOf(path, id, live, trees, led);
      if (found) chats.set(id, found);
    }
  }
  return [...chats.values()].sort((one, other) => other.at.localeCompare(one.at));
};

const roundFiles = () =>
  readdirSync(ROUNDS)
    .filter((name) => name.endsWith('.json'))
    .map((name) => ({ id: name.slice(0, -'.json'.length), file: join(ROUNDS, name) }))
    .map((each) => ({ ...each, round: readJson(each.file) }))
    .filter(({ round }) => round && typeof round.folder === 'string' && Array.isArray(round.chats));

const firstLine = (text) => (typeof text === 'string' ? text.trim().split('\n')[0] : '');

// A chat of a round has no session until its first message is sent; till then the page shows its
// task, which is how the round was divided.
const memberOf = (folder, live, trees, id, prompt) => {
  const task = typeof prompt === 'string' ? prompt.trim() : null;
  const first = firstLine(prompt);
  const told = (/^\*\*(.+?)\.?\*\*/.exec(first)?.[1] ?? first.replace(/[*`]/g, '')).slice(0, 120);
  if (typeof id !== 'string' || !SESSION.test(id))
    return { id: null, name: null, title: told, task, state: 'new', hosted: false, waitingFor: null, at: null, context: null, model: null, changes: null, heard: null };
  const transcript = transcriptOf(folder, id);
  const stat = existsSync(transcript) ? statSync(transcript) : null;
  const lines = stat ? tailOf(transcript, stat.size) : [];
  const shared = {
    id,
    title: titleOf(lines) || told,
    task,
    context: contextOf(lines),
    model: modelOf(id, lines),
    changes: changesOf(folder, transcript, trees),
    heard: heardOf(id, lines),
  };
  const session = live.get(id);
  if (session) {
    const { name, state, hosted, waitingFor, at } = session;
    return { ...shared, name, state, hosted, waitingFor, at };
  }
  // A chat given its session that has not yet written a word has done nothing, so is not finished.
  return { ...shared, name: null, state: stat ? 'closed' : 'new', hosted: false, waitingFor: null, at: stat?.mtime.toISOString() ?? null };
};

// What a chat last said through its hooks: that it answered, with its answer, or that it waits.
const heardOf = (id, lines) => {
  const heard = readJson(join(HEARD, `${id}.json`));
  if (!heard?.at) return null;
  return {
    event: heard.event,
    at: heard.at,
    message: heard.message ?? null,
    said: heard.event === 'stop' ? lastSaid(lines)?.slice(0, 500) ?? null : null,
  };
};

// The word a round's coordinator was asked and has not yet been sent, while it works in the editor.
const wordOf = (round, pending) =>
  pending.find((command) => command.round === round && Object.hasOwn(ASKED, command.kind))?.text ?? null;

const roundsOf = (live, trees, pending) =>
  roundFiles()
    .filter(({ round }) => !round.closed)
    .map(({ id, round }) => ({
      id,
      folder: round.folder,
      created: round.created ?? null,
      started: round.started ?? null,
      auto: round.auto !== false,
      asked: wordOf(id, pending),
      coordinator: memberOf(round.folder, live, trees, round.coordinator, null),
      chats: round.chats.map((chat) => memberOf(round.folder, live, trees, chat?.sessionId, chat?.prompt)),
    }))
    .sort((one, other) => String(other.created).localeCompare(String(one.created)));

// The processes of the workspace, each with what it runs and where.
const processes = () => {
  const found = [];
  for (const pid of readdirSync('/proc')) {
    if (!/^\d+$/.test(pid)) continue;
    try {
      const argv = readFileSync(`/proc/${pid}/cmdline`, 'utf8').split('\0').filter(Boolean);
      found.push({ pid: Number(pid), argv, cwd: readlinkSync(`/proc/${pid}/cwd`) });
    } catch {
      // Gone between the listing and the read, or another user's.
    }
  }
  return found;
};

// The check and release scripts running, once each by project and kind, however many shells they fork.
const scriptsOf = (all) => {
  const found = new Map();
  for (const { argv, cwd } of all) {
    const at = argv.findIndex((arg) => Object.hasOwn(SCRIPTS, arg.split('/').at(-1)));
    if (at < 0 || !/(^|\/)(ba)?sh$/.test(argv[0] ?? '')) continue;
    const script = SCRIPTS[argv[at].split('/').at(-1)];
    const kind = script === 'release' ? 'release' : argv.includes('--browser') ? 'browser' : 'night';
    found.set(`${cwd} ${kind}`, { script, kind, cwd });
  }
  return [...found.values()];
};

const within = (path, cwd) => cwd === path || cwd.startsWith(`${path}/`);

// The times the check scripts write are Zagreb's, whatever zone this process runs in.
const ZONE = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Zagreb',
  hourCycle: 'h23',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});
const wallOf = (moment) => {
  const part = Object.fromEntries(ZONE.formatToParts(moment).map(({ type, value }) => [type, Number(value)]));
  return Date.UTC(part.year, part.month - 1, part.day, part.hour, part.minute);
};
const zagreb = (text) => {
  const wall = Date.parse(`${text.replace(' ', 'T')}:00Z`);
  let moment = wall - (wallOf(wall) - wall);
  moment = wall - (wallOf(moment) - moment);
  return new Date(moment).toISOString();
};

const lastLines = (file) => {
  try {
    return readFileSync(file, 'utf8').trimEnd().split('\n');
  } catch {
    return [];
  }
};

const outcomeOf = (file) => {
  const lines = lastLines(file);
  for (let at = lines.length - 1; at >= 0; at--) {
    const found = OUTCOME.exec(lines[at]);
    if (found) return { tree: found[1], outcome: found[2], at: zagreb(found[3]) };
  }
  return null;
};

// Whoever runs a check holds its lock, also from outside the workspace, as the night's run does. A
// shared lock tried and let go at once only delays a run that starts meanwhile.
const held = (file) => {
  if (!existsSync(file)) return false;
  try {
    execFileSync('flock', ['--nonblock', '--shared', file, 'true'], { stdio: 'ignore' });
    return false;
  } catch {
    return true;
  }
};

const changedAt = (file) => (existsSync(file) ? statSync(file).mtimeMs : 0);

// How the project's gate last went: the check before a push, what was pushed, the browser's tests
// after it and the night's run of everything, and which of the last two runs now.
const gateOf = (path) => {
  const store = join(path, CHECKS);
  if (!existsSync(store)) return null;
  const checked = lastLines(join(store, 'passed'))
    .map((line) => /^([0-9a-f]{40}) (\d{4}-\d{2}-\d{2} \d{2}:\d{2})$/.exec(line))
    .filter(Boolean)
    .at(-1);
  let pushed = null;
  const commit = lastLines(join(store, 'pushed'))[0]?.trim();
  if (commit && /^[0-9a-f]{40}$/.test(commit)) {
    try {
      const tree = git(path, 'rev-parse', `${commit}^{tree}`).trim();
      pushed = { commit, tree, at: statSync(join(store, 'pushed')).mtime.toISOString() };
    } catch {
      pushed = null;
    }
  }
  const ran = (name) => {
    const found = outcomeOf(join(store, name));
    return found && { ...found, pushed: found.tree === pushed?.tree };
  };
  const night = ran('full');
  if (night) {
    const failed = readJson(join(store, 'failed.json'));
    night.failed =
      failed?.tree === night.tree
        ? new Set([...(failed.pytest ?? []), ...(failed.e2e ?? [])]).size
        : null;
  }
  return {
    checked: checked ? { tree: checked[1], at: zagreb(checked[2]) } : null,
    pushed,
    browser: ran('browser'),
    night,
    running: held(join(store, 'full.lock'))
      ? [changedAt(join(store, 'browser.log')) > changedAt(join(store, 'full.log')) ? 'browser' : 'night']
      : [],
  };
};

const folders = () =>
  readdirSync(ROOT, { withFileTypes: true })
    .filter((each) => each.isDirectory() && !each.name.startsWith('.') && existsSync(join(ROOT, each.name, '.git')))
    .map((each) => ({ name: each.name, path: join(ROOT, each.name) }));

const projects = () => {
  const live = running();
  const trees = new Map();
  const rounds = roundsOf(live, trees, deferred());
  const scripts = scriptsOf(processes());
  // A chat of a round is shown with its round alone.
  const entry = (name, path) => {
    const own = rounds.filter((round) => round.folder === path).map(({ folder, ...round }) => round);
    const held = new Set(own.flatMap((round) => [round.coordinator, ...round.chats]).map((member) => member.id));
    return { name, path, gate: gateOf(path), chats: chatsOf(path, live, trees, held), rounds: own };
  };
  const found = folders().map(({ name, path }) => entry(name, path));
  return { projects: [entry(null, ROOT), ...found], restart: restartOf(live, scripts), usage: usageOf(), models: modelsOf(), host: hostOf(ROOT) };
};

const roundAt = (id) => {
  const file = join(ROUNDS, `${id}.json`);
  const round = readJson(file);
  if (!round) throw new Refusal(404, 'no_round');
  return { file, round };
};

// A closed round's chats end once; a round closed while this service was away keeps its chats and
// its coordinator.
const endedAway = () => {
  for (const { file, round } of roundFiles())
    if (round.closed && !round.ended) writeJson(file, { ...round, ended: round.closed, left: round.closed });
};

// The coordinator of a closed round ends once it is idle, as it goes on to push, release and restart
// after closing it; one leading or working in a round still open stays, and one ended starts again with a message.
const left = () => {
  const rounds = roundFiles();
  const live = running();
  const open = rounds.filter(({ round }) => !round.closed).map(({ round }) => round);
  const leading = new Set(open.flatMap((round) => [round.coordinator, ...round.chats.map((chat) => chat?.sessionId)]));
  const now = new Date().toISOString();
  for (const { file, round } of rounds) {
    if (!round.closed || round.left) continue;
    const id = round.coordinator;
    const state = live.get(id)?.state;
    if (SESSION.test(id ?? '') && !leading.has(id) && state) {
      if (state !== 'idle') continue;
      ended(id).catch((error) => console.error(`the coordinator of ${round.round} did not end`, error));
    }
    writeJson(file, { ...round, left: now });
  }
};

const COORDINATOR = 'Koordinator';

// The coordinator bears the round's name, given by whoever divided it.
const coordinatorName = (round) => {
  const name = typeof round.title === 'string' ? firstLine(round.title).replace(/[*`]/g, '').trim() : '';
  return name.slice(0, TITLE) || COORDINATOR;
};

const named = (round) => {
  if (!SESSION.test(round.coordinator ?? '')) return;
  const name = coordinatorName(round);
  if (isHosted(round.coordinator)) {
    takenOver(round.coordinator, round.folder)
      .then((chat) => chat && rename(chat, name))
      .catch((error) => console.error(`the coordinator of ${round.round} was not named`, error));
    return;
  }
  const transcript = transcriptOf(round.folder, round.coordinator);
  if (existsSync(transcript)) retitled(transcript, round.coordinator, name);
};

// A round's chats start once it is started, each a session named here before it starts, and end
// once it is closed; its coordinator is named once. A closed round's chats are archived once, so
// that one the owner opens again stays on the page.
const led = () => {
  const now = new Date().toISOString();
  for (const { file, round } of roundFiles()) {
    if (round.closed) {
      if (round.ended && round.archived) continue;
      const chats = round.chats.map((chat) => chat?.sessionId).filter((id) => SESSION.test(id ?? ''));
      if (!round.ended)
        for (const id of chats)
          ended(id).catch((error) => console.error(`a chat of ${round.round} did not end`, error));
      if (!round.archived)
        archive(chats.map((id) => ({ id, label: labelOf(transcriptOf(round.folder, id)) })));
      writeJson(file, { ...round, ended: round.ended ?? now, archived: round.archived ?? now });
      continue;
    }
    const starting = round.started
      ? round.chats.filter((chat) => chat && !chat.sessionId && typeof chat.prompt === 'string' && chat.prompt.trim())
      : [];
    const naming = !round.named;
    if (!starting.length && !naming) continue;
    for (const chat of starting) chat.sessionId = randomUUID();
    if (naming) round.named = now;
    writeJson(file, round);
    if (naming) named(round);
    for (const chat of starting) {
      try {
        begun(chat.sessionId, round.folder, chat.prompt.trim());
      } catch (error) {
        console.error(`a chat of ${round.round} did not start`, error);
      }
    }
  }
  left();
};

const commandAt = (id) => join(COMMANDS, `${id}.json`);

const commandFiles = () =>
  readdirSync(COMMANDS)
    .filter((name) => COMMAND.test(name))
    .map((name) => readJson(join(COMMANDS, name)))
    .filter((command) => command && Number.isSafeInteger(command.id) && KINDS.has(command.kind));

// What waits for its chat to stop working in the editor.
const deferred = () => commandFiles().filter((command) => command.state === 'sent' && CARRIED.has(command.kind));

// What a command carried leaves behind is its outcome, not its images.
const settle = (command, state, error = null) => {
  const { images: _images, ...kept } = command;
  const settled = { ...kept, images: command.images?.length ?? 0, state, error, at: new Date().toISOString() };
  writeJson(commandAt(command.id), settled);
  return settled;
};

// A command waits no longer than this for its chat to stop working in the editor.
const swept = () => {
  const now = Date.now();
  for (const { file, round } of roundFiles())
    if (round.closed && now - Date.parse(round.closed) > KEPT_CLOSED) rmSync(file, { force: true });
  for (const command of commandFiles()) {
    const since = now - Date.parse(command.at);
    if (command.state === 'done' || command.state === 'failed') {
      if (since > KEPT_SETTLED && reported.get(command.id) === movedTo(command)) rmSync(commandAt(command.id), { force: true });
    } else if (command.state === 'sent' && since > UNTAKEN) settle(command, 'failed', 'chat_busy');
  }
};

const openRound = (id) => {
  if (typeof id !== 'string' || !new RegExp(`^${ROUND}$`).test(id)) throw new Refusal(400, 'invalid_round');
  const found = roundAt(id);
  if (found.round.closed) throw new Refusal(409, 'round_closed');
  return found;
};

const RULES = '`~/.claude/skills/nastavi/SKILL.md`, odjeljak „3. Zadatak svakog chata”';

const leaderOf = (round) => `sesija \`coordinator\` iz \`~/.claude/ponistra-rounds/${round}.json\``;

const titleIn = (folder, id) => {
  const transcript = transcriptOf(folder, id);
  return (existsSync(transcript) && titleOf(tailOf(transcript, statSync(transcript).size))) || id;
};

// A chat dropped on a round's coordinator joins that round; the coordinator of another round
// brings its whole round along and stays in it as one of its chats. What each of them is told
// waits in the round it joined until that chat can read it.
const moved = (session, target, live) => {
  const { file, round } = openRound(target);
  if (folderOf(session, live) !== round.folder) throw new Refusal(409, 'other_project');
  if (round.coordinator === session || round.chats.some((chat) => chat?.sessionId === session))
    throw new Refusal(409, 'same_round');
  const pending = deferred();
  if (wordOf(target, pending)) throw new Refusal(409, 'asked');
  const open = roundFiles().filter((each) => !each.round.closed && each.id !== target);
  const led = open.find((each) => each.round.coordinator === session);
  const from = open.find((each) => each.round.chats.some((chat) => chat?.sessionId === session));
  const told = [...(round.tell ?? [])];
  const said = (to, text) => SESSION.test(to ?? '') && told.push({ session: to, text });
  const name = titleIn(round.folder, session);
  let chats = round.chats;
  if (led) {
    if (wordOf(led.id, pending)) throw new Refusal(409, 'asked');
    const brought = led.round.chats.map((chat) =>
      chat?.sessionId || typeof chat?.prompt !== 'string'
        ? chat
        : { ...chat, prompt: chat.prompt.replaceAll(led.id, target) },
    );
    chats = [...chats, { prompt: null, sessionId: session }, ...brought];
    rmSync(led.file, { force: true });
    const members = brought.map((chat) => chat?.sessionId).filter((id) => SESSION.test(id ?? ''));
    said(
      session,
      `Tvoj krug \`${led.id}\` spojen je u krug \`${target}\`. Više ne koordiniraš ni ne objedinjuješ: od sada si chat kruga \`${target}\` po pravilima iz ${RULES}, s oznakom \`${target}\`, a koordinator ti je ${leaderOf(target)}. Jednom porukom mu predaj stanje: svoje korake i područje, i za svaki chat kruga \`${led.id}\` korake, područje i što čeka. Ispravi \`round\` na \`${target}\` u retku \`sessions/\` za sebe i za chatove kruga \`${led.id}\` na ploči plana.`,
    );
    for (const id of members)
      said(
        id,
        `Krug \`${led.id}\` spojen je u krug \`${target}\`. Koordinator ti je od sada ${leaderOf(target)}; ime mu čitaš istom naredbom iz zadatka, s oznakom \`${target}\`. Sve ostalo vrijedi kao dosad.`,
      );
    said(
      round.coordinator,
      `U tvoj krug \`${target}\` spojen je krug \`${led.id}\` („${name}”): njegovi chatovi i njegov dosadašnji koordinator (sesija \`${session}\`) od sada su tvoji, kao chatovi kruga. On će ti porukom predati stanje. Pazi da im se područja ne sudaraju s područjima tvojih chatova i uključi ih u \`objedini\`.`,
    );
  } else {
    chats = [...chats, { prompt: null, sessionId: session }];
    if (from) {
      writeJson(from.file, {
        ...from.round,
        chats: from.round.chats.filter((chat) => chat?.sessionId !== session),
      });
      said(
        from.round.coordinator,
        `Chat „${name}” (sesija \`${session}\`) premješten je u krug \`${target}\`. Više nije tvoj: ne koordiniraš ga i ne uključuješ ga u \`objedini\` ovog kruga.`,
      );
    }
    said(
      session,
      `Premješten si u krug \`${target}\`. Od sada radiš kao chat tog kruga po pravilima iz ${RULES}, s oznakom \`${target}\`; koordinator ti je ${leaderOf(target)}. Tvoji koraci i područje ostaju ono na čemu si dosad radio. Upiši ili ispravi \`sessions/<svoje ime iz ListAgents>\` na ploči plana s \`round: ${target}\`, pa koordinatoru porukom javi koje korake i područje držiš i što si dosad promijenio.`,
    );
    said(
      round.coordinator,
      `U tvoj krug \`${target}\` premješten je chat „${name}” (sesija \`${session}\`)${from ? ` iz kruga \`${from.id}\`` : ''}. Od sada ga koordiniraš kao ostale: javit će ti svoje korake i područje. Pazi da se ne sudara s područjima drugih chatova kruga i uključi ga u \`objedini\`.`,
    );
  }
  writeJson(file, { ...round, chats, tell: told });
  return round.folder;
};

// What a round's chats were told when one joined it, given once the chat can take it: one chat at
// a time, as two takeovers of it would start it twice, and never while it waits on a question, as
// what it is told then would answer it.
const telling = new Set();

const toldOf = () => {
  for (const { id, round } of roundFiles()) {
    if (round.closed || !Array.isArray(round.tell)) continue;
    for (const session of new Set(round.tell.map((each) => each.session))) {
      if (telling.has(session)) continue;
      telling.add(session);
      takenOver(session, round.folder)
        .then((chat) => {
          if (!chat || chat.asked) return;
          const now = roundAt(id);
          const texts = (now.round.tell ?? []).filter((each) => each.session === session);
          for (const { text } of texts) chat.said(text, []);
          writeJson(now.file, { ...now.round, tell: now.round.tell.filter((each) => each.session !== session) });
        })
        .catch((error) => console.error(`a chat of ${id} was not told it joined`, error))
        .finally(() => telling.delete(session));
    }
  }
};

const sessionGiven = (session) => {
  if (typeof session !== 'string' || !SESSION.test(session)) throw new Refusal(400, 'invalid_session');
  return session;
};

const titleGiven = (text) => {
  if (!text || text.length > TITLE || text.includes('\n')) throw new Refusal(400, 'invalid_text');
  return text;
};

const imagesGiven = (images) => {
  if (images === undefined) return [];
  if (!Array.isArray(images) || images.length > IMAGES) throw new Refusal(400, 'invalid_images');
  for (const image of images)
    if (!IMAGE_TYPES.has(image?.media_type) || typeof image.data !== 'string' || !image.data)
      throw new Refusal(400, 'invalid_images');
  return images.map(({ media_type, data }) => ({ media_type, data }));
};

// A closed chat takes its name as Claude Code itself writes it, which a session resumed reads back.
const retitled = (transcript, id, title) =>
  appendFileSync(transcript, `${JSON.stringify({ type: 'custom-title', customTitle: title, sessionId: id })}\n`);

const projectFolders = () => [ROOT, ...folders().map(({ path }) => path)];

// Where a chat runs, or else the project whose folder keeps its transcript.
const folderOf = (session, live) => {
  const folder = live.get(session)?.cwd ?? projectFolders().find((path) => existsSync(transcriptOf(path, session)));
  if (!folder) throw new Refusal(404, 'no_chat');
  return folder;
};

// What goes into a chat waits while it works in the editor, and is tried again with each change.
const carrying = new Set();

const carry = async (command) => {
  if (carrying.has(command.id)) return;
  carrying.add(command.id);
  try {
    // What was asked of a round's coordinator is no longer its to do once the round has closed.
    if (command.round && roundAt(command.round).round.closed) throw new Refusal(409, 'round_closed');
    const chat = await takenOver(command.session, command.folder);
    if (!chat) return;
    if (command.kind === 'rename') rename(chat, command.text);
    else if (command.kind === 'model') choose(chat, command.text);
    else say(chat, command.text, command.images ?? []);
    settle(command, 'done');
  } catch (error) {
    if (!(error instanceof Refusal)) console.error(`the command ${command.id} failed`, error);
    settle(command, 'failed', error instanceof Refusal ? error.message : 'unread');
  } finally {
    carrying.delete(command.id);
  }
};

// Carries out what the owner asked, at once or, for a chat working in the editor, once it is idle.
const ordered = async (given) => {
  const { id, kind } = given;
  if (!Number.isSafeInteger(id) || id < 1 || !KINDS.has(kind)) throw new Refusal(400, 'invalid_command');
  if (existsSync(commandAt(id))) throw new Refusal(409, 'known_command');
  const now = new Date().toISOString();
  const text = typeof given.text === 'string' ? given.text.trim() : null;
  let command = {
    id,
    kind,
    folder: null,
    round: null,
    session: null,
    text: null,
    images: [],
    label: null,
    auto: given.auto === true,
    state: 'sent',
    error: null,
    created: now,
    at: now,
  };
  const live = running();
  if (kind === 'chat') {
    if (!projectFolders().includes(given.folder)) throw new Refusal(404, 'no_project');
    if (!text) throw new Refusal(400, 'invalid_text');
    const images = imagesGiven(given.images);
    const session = randomUUID();
    begun(session, given.folder, text, images);
    command = { ...command, folder: given.folder, session, text, images, state: 'done' };
  } else if (kind === 'say' || kind === 'rename' || kind === 'model') {
    const session = sessionGiven(given.session);
    const folder = folderOf(session, live);
    if (kind === 'rename') titleGiven(text);
    if (kind === 'model' && !modelsOf().some(({ value }) => value === text)) throw new Refusal(400, 'invalid_model');
    if (!text) throw new Refusal(400, 'invalid_text');
    command = { ...command, folder, session, text, images: kind === 'say' ? imagesGiven(given.images) : [] };
    if (kind === 'rename' && !live.has(session)) {
      retitled(transcriptOf(folder, session), session, text);
      command.state = 'done';
    }
  } else if (kind === 'push' && given.round === undefined) {
    const session = sessionGiven(given.session);
    command = { ...command, folder: folderOf(session, live), session, text: ASKED.push };
  } else if (kind === 'answer') {
    const session = sessionGiven(given.session);
    if (text !== 'yes' && text !== 'no') throw new Refusal(400, 'invalid_text');
    answered(session, text === 'yes');
    command = { ...command, folder: live.get(session)?.cwd ?? null, session, text, state: 'done' };
  } else if (kind === 'stop') {
    const session = sessionGiven(given.session);
    interrupt(session);
    command = { ...command, folder: live.get(session)?.cwd ?? null, session, state: 'done' };
  } else if (kind === 'move') {
    const session = sessionGiven(given.session);
    command = { ...command, folder: moved(session, given.round, live), round: given.round, session, state: 'done' };
  } else if (kind === 'open' || kind === 'close' || kind === 'archive') {
    const session = sessionGiven(given.session);
    const folder = folderOf(session, live);
    command = { ...command, folder, session, label: labelOf(transcriptOf(folder, session)) };
    if (kind === 'open') await released(session);
    else {
      if (kind === 'archive') archive([{ id: session, label: command.label }]);
      await ended(session);
    }
    command.state = 'done';
  } else if (kind !== 'restart') {
    const { file, round } = openRound(given.round);
    command = { ...command, folder: round.folder, round: given.round };
    if (kind === 'start') {
      round.started ??= now;
      writeJson(file, round);
      command.state = 'done';
    } else if (kind === 'auto') {
      round.auto = text === 'on';
      writeJson(file, round);
      command = { ...command, text, state: 'done' };
    } else {
      if (wordOf(given.round, deferred())) throw new Refusal(409, 'asked');
      command = { ...command, session: round.coordinator, text: text || ASKED[kind] };
    }
  }
  if (kind === 'restart') {
    command.state = 'taken';
    writeJson(commandAt(id), command);
    try {
      restarted();
    } catch (error) {
      settle(command, 'failed', error instanceof Refusal ? error.message : 'unread');
      throw error;
    }
    return { state: command.state };
  }
  if (command.state === 'sent') {
    writeJson(commandAt(id), command);
    await carry(command);
  } else settle(command, command.state);
  const after = readJson(commandAt(id));
  return { state: after?.state ?? command.state, error: after?.error ?? null, session: command.session };
};

// What was said in a chat, wherever its transcript is kept.
const chatAt = (id, place = {}) => {
  const live = running().get(id);
  const kept = join(AGENT, 'projects');
  const transcript = live
    ? transcriptOf(live.cwd, id)
    : readdirSync(kept)
        .map((folder) => join(kept, folder, `${id}.jsonl`))
        .find((file) => existsSync(file));
  if (!transcript || !existsSync(transcript)) throw new Refusal(404, 'no_chat');
  const size = statSync(transcript).size;
  const page = pageOf(transcript, size, place);
  return {
    id,
    title: titleOf(tailOf(transcript, size)),
    state: live?.state ?? 'closed',
    waitingFor: live?.waitingFor ?? null,
    ...page,
  };
};

// One page of what was said: from `from` to the end, or else back from `before` (the end by
// default) until the owner's words of PAGE_TURNS turns are in it. `earlier` is where the page
// begins, the `before` of the page ahead of it, null at the transcript's start.
const pageOf = (transcript, size, { before, from }) => {
  if (from !== undefined) {
    const start = Math.min(from, size);
    return { said: saidIn(linesOf(transcript, start, size - start)), earlier: start || null };
  }
  const end = Math.min(before ?? size, size);
  let span = TAIL;
  for (;;) {
    const start = Math.max(0, end - span);
    const buffer = Buffer.alloc(end - start);
    const handle = openSync(transcript, 'r');
    try {
      readSync(handle, buffer, 0, buffer.length, start);
    } finally {
      closeSync(handle);
    }
    const cut = start ? buffer.indexOf(10) + 1 : 0;
    const whole = start && !cut ? end : start + cut;
    const said = saidIn(buffer.subarray(whole - start).toString('utf8').split('\n'));
    const turns = said.filter((each) => each.role === 'user').length;
    if (!start || turns >= PAGE_TURNS || span >= PAGE_READ) return { said, earlier: whole || null };
    span *= 2;
  }
};

const placeOf = (address) => {
  const place = {};
  for (const name of ['before', 'from']) {
    const value = address.searchParams.get(name);
    if (value === null) continue;
    if (!/^\d{1,15}$/.test(value)) throw new Refusal(400, `invalid_${name}`);
    place[name] = Number(value);
  }
  return place;
};

// A restart ends every chat of the workspace, so it waits while one works or waits on its owner,
// or while a check or a release runs here.
const restartOf = (live, scripts) => {
  if (!existsSync(SOCKET)) return null;
  const working = [...live]
    .filter(([, session]) => session.state !== 'idle')
    .map(([id, { name, state, cwd }]) => {
      const transcript = transcriptOf(cwd, id);
      const stat = existsSync(transcript) ? statSync(transcript) : null;
      return { id, name, state, title: (stat && titleOf(tailOf(transcript, stat.size))) || null };
    });
  const projectOf = (cwd) => folders().find(({ path }) => within(path, cwd))?.name ?? null;
  return {
    sessions: live.size,
    working,
    scripts: scripts.map(({ script, kind, cwd }) => ({ script, kind, project: projectOf(cwd) })),
  };
};

const docker = (...args) =>
  execFileSync('docker', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();

// This container's id, from the hostname file Docker mounts into it whatever the hostname is.
const selfId = () => {
  const found = /\/containers\/([0-9a-f]{64})\/hostname /.exec(readFileSync('/proc/self/mountinfo', 'utf8'));
  if (!found) throw new Refusal(409, 'not_in_docker');
  return found[1];
};

// The workspace is made again by its own compose project, from a container of its own image beside
// it, as a command run in here ends with the container it stops. The image goes by its name: a
// rebuild under containerd's store drops the running image's id, the one a restart is for.
const restarted = () => {
  const busy = restartOf(running(), scriptsOf(processes()));
  if (!busy) throw new Refusal(409, 'no_docker');
  if (busy.working.length || busy.scripts.length) throw new Refusal(409, 'workspace_busy');
  const [self] = JSON.parse(docker('inspect', selfId()));
  const label = (name) => self.Config.Labels?.[`com.docker.compose.${name}`];
  const project = label('project');
  const service = label('service');
  const directory = label('project.working_dir');
  if (!project || !service || !directory) throw new Refusal(409, 'not_from_compose');
  const files = (label('project.config_files') ?? '').split(',').filter(Boolean);
  const helper = `${self.Name.replace(/^\//, '')}_restart`;
  try {
    if (docker('inspect', '--format', '{{.State.Running}}', helper) === 'true') throw new Refusal(409, 'restart_running');
    docker('rm', helper);
  } catch (error) {
    if (error instanceof Refusal) throw error;
  }
  const mounts = [...new Set([directory, ...files.map((file) => file.slice(0, file.lastIndexOf('/')))])];
  docker(
    'run', '--detach', '--name', helper, '--user', '0', '--entrypoint', 'docker',
    '--volume', `${SOCKET}:${SOCKET}`,
    ...mounts.flatMap((mount) => ['--volume', `${mount}:${mount}:ro`]),
    '--workdir', directory,
    self.Config.Image,
    'compose', '--project-name', project, '--project-directory', directory,
    ...files.flatMap((file) => ['--file', file]),
    'up', '--detach', '--no-deps', '--force-recreate', service,
  );
  return { ok: true };
};

const bodyOf = (request, most = 4096) =>
  new Promise((resolve, reject) => {
    const parts = [];
    let size = 0;
    request.on('data', (part) => {
      size += part.length;
      if (size > most) reject(new Refusal(413, 'too_large'));
      else parts.push(part);
    });
    request.on('end', () => {
      try {
        resolve(JSON.parse(Buffer.concat(parts).toString('utf8') || '{}'));
      } catch {
        reject(new Refusal(400, 'invalid_json'));
      }
    });
    request.on('error', reject);
  });

// A panel follows the rounds of its folder, to draw each as a group of its sessions.
const keptOf = (folder) =>
  JSON.stringify({
    rounds: roundFiles()
      .filter(({ round }) => round.folder === folder)
      .map(({ round }) => round),
  });

// Each panel's stream, by the folder it follows and what it was last sent.
const streams = new Set();

const sent = (stream) => {
  const now = keptOf(stream.folder);
  if (now === stream.last) return;
  stream.last = now;
  stream.response.write(`data: ${now}\n\n`);
};

// What the page shows of the register, the rounds and the gates.
const shown = (live) =>
  JSON.stringify([
    [...live].map(([id, { state, waitingFor }]) => [id, state, waitingFor]),
    roundFiles().map(({ id, round }) => [id, round]),
    commandFiles().map((command) => [command.id, command.state]),
    readdirSync(HEARD).map((name) => [name, changedAt(join(HEARD, name))]),
    folders().map(({ path }) => [path, gateOf(path)]),
    scriptsOf(processes()),
    { ...usageOf(), at: null },
    modelsOf(),
    hostedChats().map(({ session, model }) => [session, model]),
  ]);

let last = null;
let waiting = null;

// What PONISTRA last heard of each command, so that it hears each move once.
const reported = new Map();
const movedTo = ({ state, error }) => `${state} ${error ?? ''}`;

const tell = async () => {
  waiting = null;
  let now;
  let moved;
  try {
    swept();
    led();
    culled();
    toldOf();
    for (const command of deferred()) void carry(command);
    const live = running();
    for (const stream of streams) sent(stream);
    now = shown(live);
    moved = commandFiles().filter((command) => reported.get(command.id) !== movedTo(command));
  } catch (error) {
    console.error('the workspace could not read its sessions and rounds', error);
    return;
  }
  if (now === last && !moved.length) return;
  last = now;
  const commands = moved.map(({ id, state, error }) => ({ id, state, error }));
  try {
    const answer = await fetch(TOLD, {
      method: 'POST',
      headers: { authorization: `Bearer ${TOKEN}`, 'content-type': 'application/json' },
      body: JSON.stringify({ commands }),
    });
    if (!answer.ok) console.error(`PONISTRA refused the change of the workspace: ${answer.status}`);
    else for (const command of moved) reported.set(command.id, movedTo(command));
  } catch (error) {
    console.error('PONISTRA was not told of the change of the workspace', error);
  }
};

const follow = (directory, matters = () => true) =>
  watch(directory, (_event, name) => {
    if (matters(name)) waiting ??= setTimeout(tell, QUIET);
  });

// A run's log is written all through it, and only its start and end matter here.
let lagging = null;
const followGate = (store) =>
  watch(store, (_event, name) => {
    if (GATE_FILES.has(name)) waiting ??= setTimeout(tell, QUIET);
    else if (LOGS.has(name))
      lagging ??= setTimeout(() => {
        lagging = null;
        void tell();
      }, LAG);
  });

mkdirSync(SESSIONS, { recursive: true });
mkdirSync(ROUNDS, { recursive: true });
mkdirSync(COMMANDS, { recursive: true });
mkdirSync(HEARD, { recursive: true });
follow(SESSIONS);
follow(ROUNDS);
follow(COMMANDS, (name) => COMMAND.test(name ?? ''));
follow(HEARD);
// A restart asked of the workspace is done once it runs again.
for (const command of commandFiles())
  if (command.kind === 'restart' && command.state === 'taken') settle(command, 'done');
endedAway();
resumed(() => {
  waiting ??= setTimeout(tell, QUIET);
});

// A project's gate is followed from when its store first appears, which the next change reveals.
const gates = new Map();
const followGates = () => {
  for (const { path } of folders()) {
    const store = join(path, CHECKS);
    if (gates.has(store) || !existsSync(store)) continue;
    const watcher = followGate(store);
    watcher.on('error', () => {
      watcher.close();
      gates.delete(store);
    });
    gates.set(store, watcher);
  }
};
followGates();
setInterval(followGates, 60 * 1000).unref();
followMemory();
void tell();

const CHAT = /^\/ponistra\/chats\/([0-9a-f-]{36})$/;

createServer(async (request, response) => {
  const answer = (status, body) => {
    response.writeHead(status, { 'content-type': 'application/json' });
    response.end(JSON.stringify(body));
  };
  const address = new URL(request.url, 'http://workspace');
  const path = address.pathname;
  const folder = address.searchParams.get('folder');
  const chat = request.method === 'GET' && CHAT.exec(path);
  try {
    if (request.method === 'GET' && path === '/ponistra/projects') {
      if (!allowed(request.headers.authorization)) return answer(403, { error: 'refused' });
      if (address.searchParams.has('measured')) await measured();
      return answer(200, projects());
    }
    if (chat) {
      if (!allowed(request.headers.authorization)) return answer(403, { error: 'refused' });
      return answer(200, chatAt(chat[1], placeOf(address)));
    }
    if (MEMORY.test(path)) {
      if (!allowed(request.headers.authorization)) return answer(403, { error: 'refused' });
      return answer(200, await memoryAnswered(request, path, address, bodyOf));
    }
    if (request.method === 'POST' && path === '/ponistra/commands') {
      if (!allowed(request.headers.authorization)) return answer(403, { error: 'refused' });
      return answer(200, await ordered(await bodyOf(request, COMMAND_BODY)));
    }
    // What a chat's panel asks, from the browser that came through the workspace's door.
    if (request.method === 'GET' && path === '/ponistra/rounds' && folder)
      return answer(200, JSON.parse(keptOf(folder)));
    if (request.method === 'GET' && path === '/ponistra/rounds/events' && folder) {
      response.writeHead(200, {
        'content-type': 'text/event-stream',
        'cache-control': 'no-store',
        'x-accel-buffering': 'no',
      });
      const stream = { folder, response, last: null };
      streams.add(stream);
      request.on('close', () => streams.delete(stream));
      return sent(stream);
    }
    answer(404, { error: 'not_found' });
  } catch (error) {
    if (error instanceof Refusal) return answer(error.status, { error: error.message });
    console.error(error);
    answer(500, { error: 'unread' });
  }
})
  .on('upgrade', (request, socket, head) => {
    const address = new URL(request.url, 'http://workspace');
    if (address.pathname !== TERMINAL) return socket.destroy();
    upgraded(request, socket, head, address, allowed, projectFolders);
  })
  .listen(8081, '0.0.0.0');
