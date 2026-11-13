// The chats this service runs itself (KR19): one Claude Code process for each, started as the
// editor's own panel starts it, so that a chat needs no browser. What the owner says, answers or
// renames goes straight to its process; the transcript stays where Claude Code keeps it, and the
// same chat opens in the editor once this service has let it go. A session never runs in two
// processes: one started elsewhere is ended once it is idle, before a chat is taken over here, and
// of two of the same session found running the older goes once it is idle.
import { spawn } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const AGENT = join(homedir(), '.claude');
const SESSIONS = join(AGENT, 'sessions');
// What this service runs, [{session, folder}], started again when it starts after a restart.
const HOSTED = join(AGENT, 'ponistra-hosted.json');
const EXTENSIONS = join(homedir(), '.local', 'share', 'code-server', 'extensions');
const BINARY = join('resources', 'native-binary', 'claude');
const SESSION = /^[0-9a-f-]{36}$/;
const ENDED_WITHIN = 10 * 1000;
// What Claude Code exits with when ended by SIGTERM, as this service ends it.
const ENDED_BY_US = 143;
const TOOL = 120;
// The panel's own start (Claude Code's extension), without its debugging.
const ARGS = [
  '--output-format', 'stream-json',
  '--verbose',
  '--input-format', 'stream-json',
  '--max-thinking-tokens=31999',
  '--permission-prompt-tool=stdio',
  '--setting-sources=user,project,local',
  '--permission-mode', 'auto',
];
// As the editor's panel runs a chat, so that it registers as one and its hooks and messages to
// other sessions work alike.
const ENV = {
  CLAUDE_CODE_ENTRYPOINT: 'claude-vscode',
  CLAUDE_CODE_SDK_READS_SESSION_STATE: '1',
  CLAUDE_CODE_EMIT_USER_PROMPT_SUBMIT_HOOK_EVENTS: '1',
  CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING: 'true',
  MCP_CONNECTION_NONBLOCKING: 'true',
};
const DENIED = 'The owner declined this.';
// The plan's limits are read through the agent's own `get_usage`, which takes no turn and spends
// nothing, by a process of its own, so that no chat has to run for them to be known.
const MEASURE = ['--output-format', 'stream-json', '--verbose', '--input-format', 'stream-json', '--no-session-persistence', '--setting-sources='];
const MEASURED_EVERY = 5 * 60 * 1000;
const MEASURED_AFTER_TURN = 60 * 1000;
const MEASURED_WITHIN = 30 * 1000;
const WINDOWS = { five_hour: 'session', seven_day: 'week' };

export class Refusal extends Error {
  constructor(status, error) {
    super(error);
    this.status = status;
  }
}

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

const versionOf = (name) => (/-(\d+)\.(\d+)\.(\d+)/.exec(name) ?? []).slice(1).map(Number);

const newer = (one, other) => {
  const [a, b] = [versionOf(one), versionOf(other)];
  for (let at = 0; at < 3; at++) if (a[at] !== b[at]) return (b[at] ?? 0) - (a[at] ?? 0);
  return 0;
};

// The agent the editor's extension brings, its latest version, as the panel runs the same.
const agent = () => {
  const found = existsSync(EXTENSIONS)
    ? readdirSync(EXTENSIONS)
        .filter((name) => name.startsWith('anthropic.claude-code-'))
        .sort(newer)
        .map((name) => join(EXTENSIONS, name, BINARY))
        .find((path) => existsSync(path))
    : undefined;
  if (!found) throw new Refusal(409, 'no_agent');
  return found;
};

const startOf = (pid) => {
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, 'latin1');
    return stat.slice(stat.lastIndexOf(')') + 2).split(' ')[19];
  } catch {
    return null;
  }
};

let measuring = null;

// Every process the register names as running, by session, oldest first; the one measuring the
// plan's limits is none of them.
export const registered = () => {
  const found = new Map();
  for (const name of readdirSync(SESSIONS)) {
    if (!name.endsWith('.json')) continue;
    const entry = readJson(join(SESSIONS, name));
    if (!entry?.sessionId || !entry.pid || startOf(entry.pid) !== String(entry.procStart)) continue;
    if (entry.pid === measuring) continue;
    const each = found.get(entry.sessionId) ?? [];
    each.push(entry);
    found.set(entry.sessionId, each);
  }
  for (const each of found.values()) each.sort((one, other) => one.startedAt - other.startedAt);
  return found;
};

const gone = (pid) =>
  new Promise((resolve) => {
    const since = Date.now();
    const look = () => {
      if (!existsSync(`/proc/${pid}`)) resolve(true);
      else if (Date.now() - since > ENDED_WITHIN) resolve(false);
      else setTimeout(look, 100);
    };
    look();
  });

const toolOf = (name, input) => {
  if (name === 'AskUserQuestion' && Array.isArray(input?.questions))
    return input.questions
      .map(({ question, options }) => `${question} (${(options ?? []).map(({ label }) => label).join(' / ')})`)
      .join(' ');
  const what = input?.description ?? input?.command ?? input?.file_path ?? input?.pattern ?? '';
  const line = String(what).split('\n')[0].slice(0, TOOL);
  return line ? `${name}: ${line}` : String(name);
};

// The process of one chat and what it last asked its owner.
class Chat {
  constructor(session, folder, child, model) {
    this.session = session;
    this.folder = folder;
    this.child = child;
    // The model the owner chose for it here, which a start after a restart keeps.
    this.model = model;
    this.choosing = new Map();
    this.asked = null;
    // From a message written to it until it ends the turn that message began.
    this.answering = false;
    this.ended = new Promise((resolve) => child.once('exit', resolve));
  }

  write(message) {
    this.child.stdin.write(`${JSON.stringify(message)}\n`);
  }

  said(text, images = []) {
    const content = [
      ...(text ? [{ type: 'text', text }] : []),
      ...images.map(({ media_type, data }) => ({ type: 'image', source: { type: 'base64', media_type, data } })),
    ];
    this.answering = true;
    this.write({ type: 'user', message: { role: 'user', content }, parent_tool_use_id: null, session_id: this.session });
  }

  answered(response) {
    const { request_id } = this.asked;
    this.asked = null;
    this.write({ type: 'control_response', response: { subtype: 'success', request_id, response } });
  }

  // Yes lets the tool run, No refuses it; a question is answered in the owner's own words.
  answer(yes, words = null) {
    const { tool, input } = this.asked;
    if (tool === 'AskUserQuestion') {
      const answer = words ?? (yes ? 'Yes' : 'No');
      const answers = Object.fromEntries((input.questions ?? []).map(({ question }) => [question, answer]));
      return this.answered({ behavior: 'allow', updatedInput: { ...input, answers } });
    }
    if (yes) return this.answered({ behavior: 'allow', updatedInput: input });
    this.answered({ behavior: 'deny', message: words ?? DENIED });
  }

  chose(model) {
    const request_id = `ponistra-model-${Date.now()}`;
    this.choosing.set(request_id, model);
    this.write({ type: 'control_request', request_id, request: { subtype: 'set_model', model } });
  }

  // As Esc in the editor: the turn ends, a tool waiting on its owner is refused, the process stays.
  interrupted() {
    this.write({ type: 'control_request', request_id: `ponistra-stop-${Date.now()}`, request: { subtype: 'interrupt' } });
  }

  renamed(title) {
    this.write({
      type: 'control_request',
      request_id: `ponistra-${Date.now()}`,
      request: { subtype: 'rename_session', title, source: 'host', session_id: this.session },
    });
  }
}

const hosted = new Map();
let changed = () => {};
let stopping = false;

const kept = () =>
  writeJson(HOSTED, [...hosted.values()].map(({ session, folder, model }) => ({ session, folder, model })));

const heard = (chat, line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }
  if (message.type === 'control_request' && message.request?.subtype === 'can_use_tool') {
    const { tool_name: tool, input } = message.request;
    chat.asked = { request_id: message.request_id, tool, input, at: new Date().toISOString(), waitingFor: toolOf(tool, input) };
    changed();
  } else if (message.type === 'control_response' && chat.choosing.has(message.response?.request_id)) {
    const { request_id, subtype, error } = message.response;
    const model = chat.choosing.get(request_id);
    chat.choosing.delete(request_id);
    if (subtype !== 'success') console.error(`the chat ${chat.session} did not take the model ${model}: ${error}`);
    else {
      chat.model = model;
      kept();
      changed();
    }
  } else if (message.type === 'control_request') {
    chat.write({
      type: 'control_response',
      response: { subtype: 'error', request_id: message.request_id, error: `${message.request?.subtype} is not served here` },
    });
  } else if (message.type === 'control_cancel_request' && chat.asked?.request_id === message.request_id) {
    chat.asked = null;
    changed();
  } else if (message.type === 'result') {
    chat.answering = false;
    changed();
    if (Date.now() - measuredAt > MEASURED_AFTER_TURN) void measured();
  }
};

// The child keeps no variable of this service's own: a shell it opens would pass them on.
const environment = () => {
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('PONISTRA_')));
  return { ...env, ...ENV };
};

const started = (session, folder, fresh, model = null) => {
  const chosen = model ? [`--model=${model}`] : [];
  const child = spawn(agent(), [...ARGS, ...chosen, fresh ? `--session-id=${session}` : `--resume=${session}`], {
    cwd: folder,
    env: environment(),
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const chat = new Chat(session, folder, child, model);
  hosted.set(session, chat);
  kept();
  let rest = '';
  child.stdout.on('data', (part) => {
    rest += part;
    let at;
    while ((at = rest.indexOf('\n')) >= 0) {
      const line = rest.slice(0, at);
      rest = rest.slice(at + 1);
      if (line) heard(chat, line);
    }
  });
  let errors = '';
  child.stderr.on('data', (part) => {
    errors = (errors + part).slice(-2000);
  });
  child.stdin.on('error', () => {});
  child.once('error', (error) => console.error(`the chat ${session} did not start`, error));
  child.once('exit', (code, signal) => {
    if (hosted.get(session) === chat) {
      hosted.delete(session);
      if (!stopping) kept();
    }
    if (code && code !== ENDED_BY_US && !stopping) console.error(`the chat ${session} ended with ${code}: ${errors.trim()}`);
    else if (signal && signal !== 'SIGTERM') console.error(`the chat ${session} ended by ${signal}`);
    changed();
  });
  changed();
  return chat;
};

// The register's processes of a session other than this service's own.
const others = (session, all = registered()) =>
  (all.get(session) ?? []).filter((entry) => entry.pid !== hosted.get(session)?.child.pid);

/** Ends the processes of the session running elsewhere, once each is idle; false while one works. */
const freed = async (session) => {
  const elsewhere = others(session);
  if (elsewhere.some((entry) => entry.status !== 'idle')) return false;
  for (const { pid } of elsewhere) {
    try {
      process.kill(pid, 'SIGTERM');
    } catch {
      continue;
    }
    if (!(await gone(pid))) throw new Refusal(409, 'not_ended');
  }
  return true;
};

/** The chat's process here, started when it is not running and ended elsewhere when it runs idle
    there; null while it works elsewhere. */
export const takenOver = async (session, folder) => {
  if (hosted.has(session)) return hosted.get(session);
  if (!(await freed(session))) return null;
  return hosted.get(session) ?? started(session, folder, false);
};

/** A new chat in the folder, with its first message. */
export const begun = (session, folder, text, images = []) => {
  if (!SESSION.test(session)) throw new Refusal(400, 'invalid_session');
  const chat = started(session, folder, true);
  chat.said(text, images);
  return chat;
};

/** What the owner says to the chat: an answer to what it waits on, or a message it reads next. */
export const say = (chat, text, images = []) => {
  if (chat.asked && text) {
    chat.answer(false, text);
    if (images.length) chat.said(null, images);
    return;
  }
  chat.said(text, images);
};

export const answer = (session, yes) => {
  const chat = hosted.get(session);
  if (!chat?.asked) throw new Refusal(409, 'not_waiting');
  chat.answer(yes);
};

export const rename = (chat, title) => chat.renamed(title);

/** Stops what the chat run here is doing; it waits for its next message. A chat the editor runs
    is stopped there, as this service cannot reach its process. */
export const interrupt = (session) => {
  const chat = hosted.get(session);
  if (!chat) throw new Refusal(409, 'not_hosted');
  chat.interrupted();
};

/** The models a chat may run on, as Claude Code names them; empty until it was first asked. */
export const modelsOf = () => models;

export const choose = (chat, model) => {
  if (!models.some(({ value }) => value === model)) throw new Refusal(400, 'invalid_model');
  chat.chose(model);
};

/** The model a chat run here was given by its owner, by the name Claude Code answers with. */
export const chosenOf = (session) => {
  const model = hosted.get(session)?.model;
  return model ? (models.find(({ value }) => value === model)?.resolved ?? null) : null;
};

/** Ends the chat wherever it runs, here or elsewhere. */
export const ended = async (session) => {
  const chat = hosted.get(session);
  const pids = [...(chat ? [chat.child.pid] : []), ...others(session).map(({ pid }) => pid)];
  for (const pid of pids) {
    try {
      process.kill(pid, 'SIGTERM');
    } catch {
      // Gone already.
    }
  }
  if (chat && !(await Promise.race([chat.ended.then(() => true), gone(chat.child.pid)]))) throw new Refusal(409, 'not_ended');
};

/** Lets the chat go for the editor to open, unless it works or waits on its owner. */
export const released = async (session) => {
  const chat = hosted.get(session);
  if (!chat) return;
  if (chat.asked || registered().get(session)?.find((entry) => entry.pid === chat.child.pid)?.status !== 'idle')
    throw new Refusal(409, 'chat_working');
  await ended(session);
};

/** What the chat waits on here, which the register cannot know: a tool or a question asked through
    this service rather than a panel. */
export const askedOf = (session) => hosted.get(session)?.asked ?? null;

export const isHosted = (session) => hosted.has(session);

/** The chats this service runs: what each waits on, and whether it is in the middle of a turn,
    which the register learns only once the process has registered and read the message. */
export const hostedChats = () =>
  [...hosted.values()].map(({ session, folder, asked, answering, model, child }) => ({
    session,
    folder,
    asked,
    answering,
    model,
    pid: child.pid,
  }));

class Unread extends Error {}

const percentOf = (value) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Unread('utilization');
  return value;
};

// A window's end comes a little different with every answer, so it is kept to the minute.
const windowOf = (kind, name, given) => {
  const resets = Date.parse(given?.resets_at);
  if (!Number.isFinite(resets)) throw new Unread(`${kind} resets_at`);
  return { kind, name, percent: percentOf(given.utilization), resets: new Date(Math.round(resets / 60000) * 60000).toISOString() };
};

// What `get_usage` answers, read strictly: a shape this service does not know is said aloud.
// The models by Claude Code's own short names, as its picker offers them first; a dated name or
// the account's default is no choice of its own.
const modelsFrom = (response) =>
  (response?.models ?? [])
    .filter(({ value }) => typeof value === 'string' && value !== 'default' && !value.startsWith('claude-'))
    .map(({ value, displayName, resolvedModel }) => ({ value, name: String(displayName ?? value), resolved: String(resolvedModel ?? value) }));

const usageFrom = (response) => {
  const limits = response?.rate_limits;
  if (response?.rate_limits_available === false) throw new Unread('rate_limits_available');
  if (!limits || typeof limits !== 'object') throw new Unread('rate_limits');
  const windows = Object.entries(WINDOWS)
    .filter(([key]) => limits[key] != null)
    .map(([key, kind]) => windowOf(kind, null, limits[key]));
  const models = limits.model_scoped ?? [];
  if (!Array.isArray(models)) throw new Unread('model_scoped');
  for (const model of models) {
    if (typeof model?.display_name !== 'string') throw new Unread('model_scoped display_name');
    windows.push(windowOf('model', model.display_name, model));
  }
  if (!windows.some(({ kind }) => kind === 'week')) throw new Unread('seven_day');
  const spend = limits.spend;
  let credits = null;
  if (spend?.enabled === true) {
    const { amount_minor: minor, exponent, currency } = spend.used ?? {};
    if (!Number.isInteger(minor) || !Number.isInteger(exponent) || typeof currency !== 'string') throw new Unread('spend used');
    credits = { used: minor / 10 ** exponent, currency, using: windows.some(({ kind, percent }) => kind !== 'session' && percent >= 100) };
  }
  return { windows, credits };
};

let usage = null;
let models = [];
let measuredAt = 0;

/** The plan's limits as last measured, {at, windows, credits, error}, null before the first. */
export const usageOf = () => usage;

const asked = (child, id) =>
  new Promise((resolve, reject) => {
    let rest = '';
    const late = setTimeout(() => reject(new Unread('unanswered')), MEASURED_WITHIN);
    child.once('error', (error) => {
      clearTimeout(late);
      reject(error);
    });
    child.once('exit', () => {
      clearTimeout(late);
      reject(new Unread('ended'));
    });
    child.stdout.on('data', (part) => {
      rest += part;
      let at;
      while ((at = rest.indexOf('\n')) >= 0) {
        const line = rest.slice(0, at);
        rest = rest.slice(at + 1);
        let message;
        try {
          message = JSON.parse(line);
        } catch {
          continue;
        }
        if (message.type !== 'control_response' || message.response?.request_id !== id) continue;
        clearTimeout(late);
        if (message.response.subtype !== 'success') reject(new Unread(String(message.response.error ?? 'refused')));
        else resolve(message.response.response);
      }
    });
  });

let asking = null;

/** Measures the plan's limits once, and says so; a measure already running is the one awaited. */
export const measured = () =>
  (asking ??= measure().finally(() => {
    asking = null;
  }));

const measure = async () => {
  measuredAt = Date.now();
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('PONISTRA_')));
  let child;
  let found;
  try {
    child = spawn(agent(), MEASURE, { cwd: homedir(), env, stdio: ['pipe', 'pipe', 'ignore'] });
    measuring = child.pid ?? null;
    child.stdin.on('error', () => {});
    const offered = asked(child, 'models');
    const read = asked(child, 'usage');
    child.stdin.write(`${JSON.stringify({ type: 'control_request', request_id: 'models', request: { subtype: 'initialize' } })}\n`);
    child.stdin.write(`${JSON.stringify({ type: 'control_request', request_id: 'usage', request: { subtype: 'get_usage', skip_behaviors: true } })}\n`);
    const [initialized] = await Promise.allSettled([offered, read]);
    if (initialized.status === 'fulfilled') {
      const offering = modelsFrom(initialized.value);
      if (JSON.stringify(offering) !== JSON.stringify(models)) {
        models = offering;
        changed();
      }
    } else console.error('the models a chat may run on were not read', initialized.reason);
    found = { ...usageFrom(await read), error: null };
  } catch (error) {
    const reason = error instanceof Unread ? `unread: ${error.message}` : error instanceof Refusal ? error.message : 'unread';
    console.error(`the plan's limits were not read (${reason})`, error instanceof Unread ? '' : error);
    found = { windows: usage?.windows ?? [], credits: usage?.credits ?? null, error: reason.slice(0, 60) };
  } finally {
    child?.kill('SIGTERM');
    measuring = null;
  }
  const before = JSON.stringify(usage);
  usage = { ...found, at: found.error ? (usage?.at ?? null) : new Date().toISOString() };
  if (JSON.stringify(usage) !== before) changed();
};

// Two processes of one session write one transcript: the older goes once it is idle, whichever
// started it, as the newer is the one the owner turned to last.
export const culled = (all = registered()) => {
  for (const [session, entries] of all) {
    if (entries.length < 2) continue;
    const newest = entries.at(-1);
    for (const entry of entries) {
      if (entry === newest || entry.status !== 'idle') continue;
      if (entry.pid === hosted.get(session)?.child.pid && hosted.get(session).asked) continue;
      try {
        process.kill(entry.pid, 'SIGTERM');
      } catch {
        // Gone already.
      }
    }
  }
};

/** Starts again what ran here before this service last stopped. */
export const resumed = (onChange) => {
  changed = onChange;
  const before = readJson(HOSTED) ?? [];
  const all = registered();
  for (const { session, folder, model } of before) {
    if (typeof session !== 'string' || !SESSION.test(session) || typeof folder !== 'string' || !existsSync(folder)) continue;
    if (all.has(session) || hosted.has(session)) continue;
    try {
      started(session, folder, false, typeof model === 'string' ? model : null);
    } catch (error) {
      console.error(`the chat ${session} was not started again`, error);
    }
  }
  kept();
  void measured();
  setInterval(() => void measured(), MEASURED_EVERY).unref();
};

// The chats end with this service, and start again with it.
const stop = () => {
  stopping = true;
  for (const chat of hosted.values()) chat.child.kill('SIGTERM');
  process.exit(0);
};
process.once('SIGTERM', stop);
process.once('SIGINT', stop);
