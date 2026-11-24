// What a chat says through Claude Code's hooks, Stop when it has answered and Notification when it
// waits on its owner, kept for projects.mjs beside it: node heard.mjs < the hook's JSON. PreCompact
// and PostCompact bracket a compaction, whose length is kept so that the next one can be foretold.
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const EVENTS = { Stop: 'stop', Notification: 'notification' };
const KEPT_DURATIONS = 20;
// A compaction that reuses a summary made beforehand ends at once, and foretells none that is made.
const INSTANT = 5000;

const kept = join(homedir(), '.claude', 'ponistra-heard');

const readJson = (file) => {
  try {
    return JSON.parse(readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
};

const write = (file, value) => {
  writeFileSync(`${file}.${process.pid}`, JSON.stringify(value));
  renameSync(`${file}.${process.pid}`, file);
};

const told = JSON.parse(readFileSync(0, 'utf8'));
const session = String(told.session_id ?? '');
if (/^[0-9a-f-]{36}$/.test(session)) {
  mkdirSync(kept, { recursive: true });
  const compacting = join(kept, `${session}.compacting.json`);
  const event = EVENTS[told.hook_event_name];
  if (told.hook_event_name === 'PreCompact') {
    write(compacting, { at: new Date().toISOString(), trigger: told.trigger ?? null });
  } else if (told.hook_event_name === 'PostCompact') {
    const began = Date.parse(readJson(compacting)?.at ?? '');
    rmSync(compacting, { force: true });
    const took = Date.now() - began;
    if (took > INSTANT) {
      const durations = join(kept, 'compactions.json');
      const known = readJson(durations);
      write(durations, [...(Array.isArray(known) ? known : []), took].slice(-KEPT_DURATIONS));
    }
  } else if (event) {
    if (event === 'stop') rmSync(compacting, { force: true });
    const message = typeof told.message === 'string' ? told.message.slice(0, 500) : null;
    write(join(kept, `${session}.json`), { event, message, at: new Date().toISOString() });
  }
}
