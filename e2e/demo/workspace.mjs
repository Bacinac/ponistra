// The demo's code workspace (scripts/demo.sh): the workspace's own service (projects.mjs) over the
// home help_seed wrote (backend/apps/help/seeds/workspace.py), with what only this container can
// make from its manifest: each project a git repository with the chats' uncommitted changes, a
// process for each running chat in Claude Code's register, and a stand-in for the agent that
// reports the plan's limits and models as Claude Code does, to a request of `get_usage`.
import { execFileSync, spawn } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const HOME = process.env.HOME;
const MANIFEST = join(HOME, '.demo-workspace.json');
const NODE = process.execPath;
const AGENT = join(
  HOME,
  '.local/share/code-server/extensions/anthropic.claude-code-1.0.0/resources/native-binary/claude',
);
const SESSIONS = join(HOME, '.claude/sessions');

if (!existsSync(MANIFEST))
  throw new Error(`${MANIFEST} is missing: help_seed writes the demo's workspace first`);
const manifest = JSON.parse(readFileSync(MANIFEST, 'utf8'));
if (manifest.home !== HOME)
  throw new Error(`the demo's workspace was written for ${manifest.home}, not ${HOME}`);

writeFileSync(
  '/tmp/passwd',
  readFileSync('/etc/passwd.base', 'utf8').replace(
    /^owner:.*$/m,
    `owner:x:${process.getuid()}:${process.getgid()}:Owner:${HOME}:/bin/bash`,
  ),
);

const write = (file, text, mode) => {
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, text, mode ? { mode } : undefined);
};

const committed = { GIT_AUTHOR_DATE: manifest.committed, GIT_COMMITTER_DATE: manifest.committed };
for (const project of manifest.projects) {
  const path = join(HOME, project);
  if (existsSync(join(path, '.git'))) continue;
  const git = (...args) =>
    execFileSync(
      'git',
      [
        '-C',
        path,
        '-c',
        'user.name=Sarah Miller',
        '-c',
        'user.email=sarah@lipastudio.test',
        ...args,
      ],
      {
        env: { ...process.env, ...committed },
        stdio: ['ignore', 'ignore', 'inherit'],
      },
    );
  git('init', '-q', '-b', 'main');
  git('add', '-A');
  git('commit', '-q', '-m', `${project}: as it stood before this week`);
}
for (const [file, text] of Object.entries(manifest.changed)) write(file, text);

const usage = manifest.usage;
write(
  AGENT,
  `#!${NODE}
const usage = ${JSON.stringify(usage)};
const models = ${JSON.stringify(manifest.models)};
const at = (minutes) => new Date(Date.now() + minutes * 60000).toISOString();
const window = ({ utilization, resets_in }) => ({ utilization, resets_at: at(resets_in) });
const answers = {
  initialize: () => ({ models }),
  get_usage: () => ({
    rate_limits_available: true,
    rate_limits: {
      five_hour: window(usage.five_hour),
      seven_day: window(usage.seven_day),
      model_scoped: usage.model_scoped.map((each) => ({ display_name: each.display_name, ...window(each) })),
    },
  }),
};
let rest = '';
process.stdin.on('data', (part) => {
  rest += part;
  let end;
  while ((end = rest.indexOf('\\n')) >= 0) {
    const asked = JSON.parse(rest.slice(0, end));
    rest = rest.slice(end + 1);
    const answer = answers[asked.request?.subtype];
    const response = answer
      ? { subtype: 'success', request_id: asked.request_id, response: answer() }
      : { subtype: 'error', request_id: asked.request_id, error: 'not in the demo' };
    process.stdout.write(JSON.stringify({ type: 'control_response', response }) + '\\n');
  }
});
`,
  0o755,
);

// Claude Code's register knows a session by its process and the moment that process started.
const startOf = (pid) => {
  const stat = readFileSync(`/proc/${pid}/stat`, 'latin1');
  return stat.slice(stat.lastIndexOf(')') + 2).split(' ')[19];
};
mkdirSync(SESSIONS, { recursive: true });
for (const chat of manifest.running) {
  const child = spawn('sleep', ['infinity'], { stdio: 'ignore' });
  const now = Date.now();
  writeFileSync(
    join(SESSIONS, `${child.pid}.json`),
    JSON.stringify({
      pid: child.pid,
      sessionId: chat.session,
      cwd: chat.cwd,
      startedAt: chat.since,
      procStart: startOf(child.pid),
      kind: 'interactive',
      entrypoint: 'claude-vscode',
      ...(chat.name ? { name: chat.name, nameSource: 'user' } : {}),
      status: chat.status,
      ...(chat.waitingFor ? { waitingFor: chat.waitingFor } : {}),
      updatedAt: now,
      statusUpdatedAt: now,
    }),
  );
}

process.env.PONISTRA_ROOT = HOME;
await import('/etc/ponistra/projects.mjs');
