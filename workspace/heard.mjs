// What a chat says through Claude Code's hooks, Stop when it has answered and Notification when it
// waits on its owner, kept for projects.mjs beside it: node heard.mjs < the hook's JSON.
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const EVENTS = { Stop: 'stop', Notification: 'notification' };

const told = JSON.parse(readFileSync(0, 'utf8'));
const session = String(told.session_id ?? '');
const event = EVENTS[told.hook_event_name];
if (event && /^[0-9a-f-]{36}$/.test(session)) {
  const kept = join(homedir(), '.claude', 'ponistra-heard');
  mkdirSync(kept, { recursive: true });
  const file = join(kept, `${session}.json`);
  const message = typeof told.message === 'string' ? told.message.slice(0, 500) : null;
  writeFileSync(`${file}.${process.pid}`, JSON.stringify({ event, message, at: new Date().toISOString() }));
  renameSync(`${file}.${process.pid}`, file);
}
