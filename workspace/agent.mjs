// The agent reaches PONISTRA's MCP server (D18) with a key of the owner's that PONISTRA hands the
// workspace: a sign-in in the browser would send its code back to localhost on the browser's
// machine, which is never the workspace's.
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const PUBLIC = process.env.PONISTRA_PUBLIC_URL;
const TOKEN = process.env.PONISTRA_WORKSPACE_TOKEN;
const AGENT = join(homedir(), '.claude.json');
const SERVER = 'ponistra';
const BEARER = 'Bearer ';
// PONISTRA may still be starting beside the workspace.
const TRIES = 60;
const PAUSE = 5000;

function read() {
  return existsSync(AGENT) ? JSON.parse(readFileSync(AGENT, 'utf8')) : {};
}

async function asked(held) {
  for (let tried = 1; ; tried++) {
    try {
      const answer = await fetch(new URL('/api/workspace/agent', PUBLIC), {
        method: 'POST',
        headers: { authorization: `Bearer ${TOKEN}`, 'content-type': 'application/json' },
        body: JSON.stringify({ key: held }),
      });
      if (answer.ok) return (await answer.json()).key;
      if (answer.status < 500) throw new Error(`PONISTRA refused the key: ${answer.status}`);
    } catch (error) {
      if (error.message.startsWith('PONISTRA refused') || tried >= TRIES) throw error;
    }
    await new Promise((resolve) => setTimeout(resolve, PAUSE));
  }
}

const url = new URL('/api/mcp', PUBLIC).href;
const held = read().mcpServers?.[SERVER]?.headers?.Authorization;
const key = await asked(held?.startsWith(BEARER) ? held.slice(BEARER.length) : null);
// Read again: the agent may have written its own state while PONISTRA answered.
const agent = read();
const before = agent.mcpServers?.[SERVER];
if (before?.url !== url || before?.headers?.Authorization !== `${BEARER}${key}`) {
  agent.mcpServers = {
    ...agent.mcpServers,
    [SERVER]: { type: 'http', url, headers: { Authorization: `${BEARER}${key}` } },
  };
  writeFileSync(`${AGENT}.ponistra`, `${JSON.stringify(agent, null, 2)}\n`, { mode: 0o600 });
  renameSync(`${AGENT}.ponistra`, AGENT);
}
