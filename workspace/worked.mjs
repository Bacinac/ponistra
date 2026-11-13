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

import { closeSync, openSync, readdirSync, readFileSync, readSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const KEPT = join(homedir(), '.claude', 'projects');
const IDLE = 15 * 60 * 1000;
const EVERY = 60 * 1000;
const CHUNK = 16 * 1024 * 1024;
// Half of what PONISTRA takes in one request.
const SENT = 50;
const TRANSCRIPT = /^([0-9a-f-]{36})\.jsonl$/;
const STAMP = Buffer.from('"timestamp"');
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

const momentOf = (line) => {
  try {
    const { timestamp } = JSON.parse(line.toString('utf8'));
    if (typeof timestamp !== 'string') return null;
    const moment = Date.parse(timestamp);
    return Number.isNaN(moment) ? null : moment;
  } catch {
    return null;
  }
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

// The moments of the whole lines from a place in a transcript, and where the last of them ends.
export const readFrom = async (file, from, size) => {
  const moments = [];
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
        if (line.includes(STAMP)) {
          const moment = momentOf(line);
          if (moment !== null) moments.push(moment);
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
  return { read, moments };
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

// Reads each transcript on from its mark, or a copy's from the start, and tells PONISTRA what it
// found, the marks moving only once PONISTRA has it.
export const measure = async (kept, marks = null) => {
  const projectOf = projectsOf(process.env.PONISTRA_ROOT);
  const batch = [];
  const send = async () => {
    const sending = batch.splice(0);
    await told('POST', { transcripts: sending });
    if (marks) for (const each of sending) marks.set(`${each.namespace}/${each.session}`, each.read);
  };
  for (const space of readdirSync(kept, { withFileTypes: true })) {
    // Another name of a folder holds the same transcripts.
    if (!space.isDirectory()) continue;
    for (const name of readdirSync(join(kept, space.name))) {
      const session = name.match(TRANSCRIPT)?.[1];
      if (!session) continue;
      const file = join(kept, space.name, name);
      let size;
      try {
        size = statSync(file).size;
      } catch {
        continue;
      }
      let from = marks?.get(`${space.name}/${session}`) ?? 0;
      // Written anew from the start: what was found in it stays, and it is read once more.
      if (from > size) from = 0;
      if (from === size) continue;
      const { read, moments } = await readFrom(file, from, size);
      if (marks && read === from) continue;
      batch.push({
        namespace: space.name,
        session,
        project: projectOf(space.name),
        read: marks ? read : null,
        stretches: stretchesOf(moments),
      });
      if (batch.length === SENT) await send();
    }
  }
  if (batch.length) await send();
};

export const followWork = () => {
  let marks = null;
  let measuring = false;
  const pass = async () => {
    if (measuring) return;
    measuring = true;
    try {
      marks ??= new Map(Object.entries((await told('GET')).read));
      await measure(KEPT, marks);
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
