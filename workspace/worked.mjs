// The time worked (VT1): the chats' transcripts read as they grow, and each stretch of work found
// in them told to PONISTRA, which keeps it with how far each transcript was read and counts the
// time by project, day and month. A stretch is a transcript's moments no two of which lie further
// apart than IDLE; PONISTRA joins the stretches of a project's chats into its blocks of work.
// A transcript is a folder's `<session>.jsonl` under `~/.claude/projects`, the folder named after
// the path the chat ran in; the project is the folder of the root it lies in, none for the root.
//
// Run by itself, it brings in what the workspace no longer holds (PONISTRA_ROOT, PONISTRA_PUBLIC_URL
// and PONISTRA_WORKSPACE_TOKEN set as for the workspace):
//   worked.mjs <folder>                    the transcripts of a copy of `~/.claude/projects`
//   worked.mjs clockify <env> <map> <day>  Clockify's entries before that day, on the projects
//                                          the map names (`{"project": "<Clockify project id>"}`),
//                                          with the key `CLOCKIFY_API_KEY` from the env file
// Either is added to what PONISTRA holds, never counted twice, and moves no mark of a transcript.
//
// An archived chat's transcript, with the folder of what it keeps beside it, is removed as many days
// after archiving as PONISTRA says (VT3), never while it runs or belongs to a round still open, and
// only once PONISTRA holds the time worked read from it to its last line.
//
// The same reading counts the tokens each answer took (PJ3), by hour, model and the round its chat
// was in, from the chat's own transcript and those of its agents (`<session>/subagents/agent-*.jsonl`,
// which count toward its tokens but not its time). Claude Code writes an answer as one line per
// block, each with the answer's whole usage, so an answer counts once by its id, the last counted
// one kept with the mark so that an answer split across two readings counts once too.

import { closeSync, openSync, readdirSync, readFileSync, readSync, rmSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const KEPT = join(homedir(), '.claude', 'projects');
const IDLE = 15 * 60 * 1000;
const EVERY = 60 * 1000;
const CHUNK = 16 * 1024 * 1024;
// Half of what PONISTRA takes in one request.
const SENT = 50;
const TRANSCRIPT = /^([0-9a-f-]{36})\.jsonl$/;
const AGENT = /^agent-([0-9a-z]{1,27})\.jsonl$/;
const STAMP = Buffer.from('"timestamp"');
const TITLED = Buffer.from('-title"');
const HOUR = 60 * 60 * 1000;
const DAY = 24 * 60 * 60 * 1000;
const STARTING = 60 * 60 * 1000;
// How many passes go by between asking PONISTRA again what it holds and what it removes.
const ASKED_EVERY = 10;
const CLOCKIFY = 'https://api.clockify.me/api/v1';
const ENTRIES = 1000;

const namespaceOf = (path) => path.replace(/[^a-zA-Z0-9]/g, '-');
const settled = () => new Promise((resolve) => setImmediate(resolve));

const projectsOf = (root) => {
  const own = namespaceOf(root);
  const names = readdirSync(root, { withFileTypes: true })
    .filter((each) => each.isDirectory())
    .map((each) => [each.name, namespaceOf(each.name)]);
  return (namespace) => {
    if (!namespace.startsWith(`${own}-`)) return '';
    const rest = namespace.slice(own.length + 1);
    const found = names.filter(([, kept]) => rest === kept || rest.startsWith(`${kept}-`));
    if (found.length) return found.reduce((one, other) => (other[1].length > one[1].length ? other : one))[0];
    // A folder gone since keeps the name its chats ran under, up to the first dash.
    return rest.split('-').find(Boolean) ?? '';
  };
};

const parsedOf = (line) => {
  try {
    return JSON.parse(line.toString('utf8'));
  } catch {
    return null;
  }
};

const momentOf = (entry) => {
  if (typeof entry?.timestamp !== 'string') return null;
  const moment = Date.parse(entry.timestamp);
  return Number.isNaN(moment) ? null : moment;
};

// What one reading of a transcript found: its moments, the tokens of each answer by hour and
// model, the id of the last answer counted and the chat's title, the one its owner gave first.
const finding = (last) => {
  const moments = [];
  const spent = new Map();
  const found = { last, custom: null, made: null };
  const take = (entry) => {
    const moment = momentOf(entry);
    if (moment !== null) moments.push(moment);
    if (entry.type === 'custom-title' && entry.customTitle) found.custom = String(entry.customTitle);
    if (entry.type === 'ai-title' && entry.aiTitle) found.made = String(entry.aiTitle);
    const { id, model, usage } = entry.message ?? {};
    if (entry.type !== 'assistant' || !usage || typeof id !== 'string' || id === found.last) return;
    found.last = id;
    if (moment === null || typeof model !== 'string' || model.startsWith('<')) return;
    const hour = Math.floor(moment / HOUR) * HOUR;
    const key = `${hour} ${model}`;
    const each = spent.get(key) ?? { hour, model, turns: 0, input: 0, output: 0, cache_read: 0, cache_write: 0 };
    each.turns += 1;
    each.input += usage.input_tokens ?? 0;
    each.output += usage.output_tokens ?? 0;
    each.cache_read += usage.cache_read_input_tokens ?? 0;
    each.cache_write += usage.cache_creation_input_tokens ?? 0;
    spent.set(key, each);
  };
  const result = () => ({ moments, spent: [...spent.values()], last: found.last, title: (found.custom ?? found.made)?.slice(0, 200) ?? null });
  return { take, result };
};

export const stretchesOf = (moments) => {
  const stretches = [];
  for (const moment of moments.sort((one, other) => one - other)) {
    const last = stretches.at(-1);
    if (last && moment - last[1] <= IDLE) last[1] = moment;
    else stretches.push([moment, moment]);
  }
  return stretches;
};

// What the whole lines from a place in a transcript hold, and where the last of them ends; `last`
// is the answer counted last before that place.
export const readFrom = async (file, from, size, last = null) => {
  const { take, result } = finding(last);
  const descriptor = openSync(file, 'r');
  let at = from;
  let read = from;
  let carried = Buffer.alloc(0);
  try {
    while (at < size) {
      const chunk = Buffer.allocUnsafe(Math.min(CHUNK, size - at));
      const got = readSync(descriptor, chunk, 0, chunk.length, at);
      if (!got) break;
      at += got;
      const buffer = carried.length ? Buffer.concat([carried, chunk.subarray(0, got)]) : chunk.subarray(0, got);
      let start = 0;
      for (let end = buffer.indexOf(10, start); end !== -1; end = buffer.indexOf(10, start)) {
        const line = buffer.subarray(start, end);
        if (line.includes(STAMP) || line.includes(TITLED)) {
          const entry = parsedOf(line);
          if (entry) take(entry);
        }
        start = end + 1;
      }
      read = at - (buffer.length - start);
      carried = Buffer.from(buffer.subarray(start));
      await settled();
    }
  } finally {
    closeSync(descriptor);
  }
  return { read, ...result() };
};

const told = async (method, payload) => {
  const answer = await fetch(new URL('/api/workspace/worked', process.env.PONISTRA_PUBLIC_URL), {
    method,
    headers: {
      authorization: `Bearer ${process.env.PONISTRA_WORKSPACE_TOKEN}`,
      'content-type': 'application/json',
    },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!answer.ok) throw new Error(`PONISTRA refused the time worked: ${answer.status} ${await answer.text()}`);
  return method === 'GET' ? answer.json() : null;
};

// A folder's transcripts: each chat's own, and its agents', which belong to it.
const transcriptsIn = (folder) => {
  const found = [];
  for (const name of readdirSync(folder)) {
    const session = name.match(TRANSCRIPT)?.[1];
    if (session) found.push({ session, chat: session, file: join(folder, name), own: true });
  }
  for (const { chat } of [...found]) {
    const agents = join(folder, chat, 'subagents');
    let names;
    try {
      names = readdirSync(agents);
    } catch {
      continue;
    }
    for (const name of names) {
      const agent = name.match(AGENT)?.[1];
      if (agent) found.push({ session: `${chat}-${agent}`, chat, file: join(agents, name), own: false });
    }
  }
  return found;
};

// Reads each transcript on from its mark, or a copy's from the start, and tells PONISTRA what it
// found, the marks moving only once PONISTRA has it. `marks` holds {read, last} by transcript;
// `roundOf` names the round a chat is in now.
export const measure = async (kept, marks = null, roundOf = () => '') => {
  const projectOf = projectsOf(process.env.PONISTRA_ROOT);
  const batch = [];
  const send = async () => {
    const sending = batch.splice(0);
    await told('POST', { transcripts: sending });
    if (marks) for (const each of sending) marks.set(`${each.namespace}/${each.session}`, { read: each.read, last: each.last });
  };
  for (const space of readdirSync(kept, { withFileTypes: true })) {
    // Another name of a folder holds the same transcripts.
    if (!space.isDirectory()) continue;
    for (const { session, chat, file, own } of transcriptsIn(join(kept, space.name))) {
      let size;
      try {
        size = statSync(file).size;
      } catch {
        continue;
      }
      const mark = marks?.get(`${space.name}/${session}`);
      let from = mark?.read ?? 0;
      let last = mark?.last ?? null;
      // Written anew from the start: what was found in it stays, and it is read once more.
      if (from > size) {
        from = 0;
        last = null;
      }
      if (from === size) continue;
      const found = await readFrom(file, from, size, last);
      if (marks && found.read === from) continue;
      batch.push({
        namespace: space.name,
        session,
        chat,
        project: projectOf(space.name),
        round: roundOf(chat),
        from,
        read: marks ? found.read : null,
        last: found.last,
        title: found.title,
        stretches: own ? stretchesOf(found.moments) : [],
        spent: found.spent,
      });
      if (batch.length === SENT) await send();
    }
  }
  if (batch.length) await send();
};

// The archived chats' transcripts PONISTRA holds read to their last line, removed once `after` days
// have gone by since each was archived; none while `after` is null or a chat is `held`. A chat the
// list of the archived no longer names, or never named, counts as archived when its transcript
// last changed, and not before STARTING has gone by, as one not yet running may be starting.
export const removed = (kept, marks, after, archived, held, now = Date.now()) => {
  if (!Number.isInteger(after) || after < 0) return [];
  const since = new Map(archived.map(({ id, at }) => [id, at]));
  const gone = [];
  for (const space of readdirSync(kept, { withFileTypes: true })) {
    if (!space.isDirectory()) continue;
    for (const name of readdirSync(join(kept, space.name))) {
      const id = name.match(TRANSCRIPT)?.[1];
      if (!id || held.has(id)) continue;
      const file = join(kept, space.name, name);
      let stat;
      try {
        stat = statSync(file);
      } catch {
        continue;
      }
      const at = since.get(id) ?? stat.mtimeMs;
      const wait = since.has(id) ? after * DAY : Math.max(after * DAY, STARTING);
      if (now - Math.max(at, stat.mtimeMs) < wait || marks.get(`${space.name}/${id}`)?.read !== stat.size) continue;
      rmSync(file, { force: true });
      rmSync(join(kept, space.name, id), { recursive: true, force: true });
      gone.push(`${space.name}/${id}`);
    }
  }
  return gone;
};

// `chats` says which chats are archived ({id, at}), which are held: running or in a round still
// open, and the round each chat is in (`rounds`, by session).
export const followWork = (chats) => {
  let marks = null;
  let measuring = false;
  let passes = 0;
  const pass = async () => {
    if (measuring) return;
    measuring = true;
    try {
      const asking = passes % ASKED_EVERY === 0;
      passes += 1;
      const held = asking ? await told('GET') : null;
      const marked = held && new Map(Object.entries(held.read).map(([key, read]) => [key, { read, last: held.last[key] ?? null }]));
      marks ??= marked;
      const { archived, held: running, rounds } = chats();
      await measure(KEPT, marks, (chat) => rounds.get(chat) ?? '');
      if (held) {
        const gone = removed(KEPT, marked, held.removal, archived, running);
        if (gone.length) console.log(`removed the transcripts of ${gone.length} archived chats: ${gone.join(', ')}`);
      }
    } catch (error) {
      console.error('the time worked was not measured', error);
    } finally {
      measuring = false;
    }
  };
  void pass();
  setInterval(pass, EVERY).unref();
};

// Midnight of a day in Zagreb, where the time sheets' days begin.
const midnight = (day) => {
  const wall = Date.parse(`${day}T00:00:00Z`);
  const offset = (moment) => {
    const part = Object.fromEntries(
      new Intl.DateTimeFormat('en-GB', {
        timeZone: 'Europe/Zagreb',
        hourCycle: 'h23',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
        .formatToParts(moment)
        .map(({ type, value }) => [type, Number(value)]),
    );
    return Date.UTC(part.year, part.month - 1, part.day, part.hour, part.minute, part.second) - moment;
  };
  return new Date(wall - offset(wall - offset(wall)));
};

const clockified = async (env, map, before) => {
  const key = readFileSync(env, 'utf8').match(/^CLOCKIFY_API_KEY=(.+)$/m)?.[1].trim();
  if (!key) throw new Error(`no CLOCKIFY_API_KEY in ${env}`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(before)) throw new Error(`not a day: ${before}`);
  const projects = new Map(Object.entries(JSON.parse(readFileSync(map, 'utf8'))).map(([name, id]) => [id, name]));
  const asked = async (path) => {
    const answer = await fetch(`${CLOCKIFY}${path}`, { headers: { 'x-api-key': key } });
    if (!answer.ok) throw new Error(`Clockify refused ${path}: ${answer.status} ${await answer.text()}`);
    return answer.json();
  };
  const user = await asked('/user');
  const end = midnight(before).toISOString();
  const entries = [];
  for (let page = 1; ; page += 1) {
    const found = await asked(
      `/workspaces/${user.activeWorkspace}/user/${user.id}/time-entries?start=2000-01-01T00:00:00Z&end=${end}&page-size=${ENTRIES}&page=${page}`,
    );
    entries.push(...found);
    if (found.length < ENTRIES) break;
  }
  const transcripts = [];
  for (const entry of entries) {
    const { start, end: ended } = entry.timeInterval ?? {};
    if (!projects.has(entry.projectId) || !start || !ended || Date.parse(start) >= Date.parse(end)) continue;
    // The entries the time sheets wrote name the folders they counted after a dash.
    const named = (entry.description ?? '').split(' — ')[1]?.split('/')[0]?.trim();
    transcripts.push({
      namespace: 'clockify',
      session: entry.id,
      project: named || projects.get(entry.projectId),
      read: null,
      stretches: [[Date.parse(start), Date.parse(ended)]],
    });
  }
  for (let at = 0; at < transcripts.length; at += SENT) await told('POST', { transcripts: transcripts.slice(at, at + SENT) });
  return transcripts.length;
};

if (import.meta.url === `file://${process.argv[1]}`) {
  const [what, ...rest] = process.argv.slice(2);
  if (!process.env.PONISTRA_ROOT || !what) {
    console.error('usage: PONISTRA_ROOT=<root> worked.mjs <folder> | clockify <env> <map> <day>');
    process.exit(2);
  }
  if (what === 'clockify') console.log(`brought ${await clockified(...rest)} Clockify entries`);
  else {
    await measure(what);
    console.log(`measured the transcripts in ${what}`);
  }
}
