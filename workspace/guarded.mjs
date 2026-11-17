// A chat's shell command refused before it runs, through Claude Code's PreToolUse hook:
// node guarded.mjs < the hook's JSON. `pgrep -f` and `pkill -f` match the command line of the
// shell the tool runs them in, which holds the same text: a wait on one never ends, keeps its chat
// in the background and the workspace from restarting, and a kill takes its own shell with it.
import { readFileSync } from 'node:fs';

const REASON =
  '`pgrep -f` and `pkill -f` match the command line of the shell this command runs in, which ' +
  'holds the same pattern, so a wait on them never ends and a kill ends this shell. Wait on the ' +
  'process id (`while kill -0 <pid> 2>/dev/null; do sleep 5; done`) or on a file the job writes ' +
  'when it ends; find a process with `ps -eo pid,args` and a filter that leaves out this shell.';

function full(flags) {
  return flags.some((flag) => flag === '--full' || /^-[a-zA-Z]*f/.test(flag));
}

export function refused(command) {
  for (const found of command.matchAll(/\bp(?:grep|kill)\b([^;|&\n)]*)/g)) {
    const flags = found[1].trim().split(/\s+/).filter((word) => word.startsWith('-'));
    if (full(flags)) return true;
  }
  return false;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const told = JSON.parse(readFileSync(0, 'utf8'));
  const command = told.tool_input?.command;
  if (told.tool_name === 'Bash' && typeof command === 'string' && refused(command)) {
    process.stdout.write(
      JSON.stringify({
        hookSpecificOutput: {
          hookEventName: 'PreToolUse',
          permissionDecision: 'deny',
          permissionDecisionReason: REASON,
        },
      }),
    );
  }
}
