// Docker Compose as the workspace's shell runs it: the real plugin, but one that would change the
// workspace's own compose project is refused, as recreating the workspace from inside ends the
// command halfway, the old container stopped and the new one never started.
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const REAL = '/usr/local/libexec/docker/compose';
const CHANGES = new Set(['up', 'down', 'stop', 'restart', 'rm', 'kill', 'create', 'start', 'pause', 'unpause', 'run', 'scale', 'watch']);
const VALUED = new Set(['-f', '--file', '-p', '--project-name', '--project-directory', '--env-file', '--profile', '--ansi', '--parallel', '--progress']);

export const REASON =
  'This is the workspace\'s own compose project: changed from inside the workspace, it stops the ' +
  'terminal this runs in halfway and leaves the workspace down. Use "Restart workspace" on the ' +
  'Projects page, which recreates the workspace and its door from outside.';

/** The options before the command and the command itself, from what follows `compose`. */
export const split = (args) => {
  const options = [];
  for (let at = 0; at < args.length; at += 1) {
    const word = args[at];
    if (!word.startsWith('-')) return { options, verb: word };
    options.push(word);
    if (VALUED.has(word) && at + 1 < args.length) options.push(args[(at += 1)]);
  }
  return { options, verb: null };
};

const run = (args) => spawnSync(REAL, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });

const ownProject = () => {
  const found = /\/containers\/([0-9a-f]{64})\/hostname /.exec(readFileSync('/proc/self/mountinfo', 'utf8'));
  if (!found) return null;
  const inspected = spawnSync('docker', ['inspect', '--format', '{{index .Config.Labels "com.docker.compose.project"}}', found[1]], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'ignore'],
  });
  return inspected.status === 0 ? inspected.stdout.trim() || null : null;
};

const targetProject = (options) => {
  const config = run(['compose', ...options, 'config', '--format', 'json']);
  return config.status === 0 ? JSON.parse(config.stdout).name : null;
};

if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  if (args[0] === 'compose') {
    const { options, verb } = split(args.slice(1));
    if (CHANGES.has(verb)) {
      const own = ownProject();
      if (own && own === targetProject(options)) {
        process.stderr.write(`${REASON}\n`);
        process.exit(1);
      }
    }
  }
  const real = spawnSync(REAL, args, { stdio: 'inherit' });
  process.exit(real.status ?? 1);
}
