// A terminal for PONISTRA's page of projects (KR25): a login shell in a pseudo-terminal for each
// WebSocket on /ponistra/terminal, in the project's folder, ended with its socket. PONISTRA's
// backend opens the socket with the token and passes the browser's frames on as they come:
// a binary frame is what the owner typed, a text frame {cols, rows} resizes the terminal, and what
// the shell writes comes back binary. Once the shell exits the socket closes with EXITED.
//
// node-pty and ws are code-server's own (both MIT), built for the node that runs this service.
import { createRequire } from 'node:module';

const vscode = createRequire('/usr/lib/code-server/lib/vscode/package.json');
const pty = vscode('node-pty');
const { WebSocketServer } = vscode('ws');

export const TERMINAL = '/ponistra/terminal';
export const EXITED = 4000;
const REFUSED = 4403;
const UNKNOWN = 4404;
const CROWDED = 4429;
const AT_MOST = 8;
const SIDE = { min: 2, max: 1000 };
// Above this much unsent output the shell is paused, so a runaway `cat` does not fill memory.
const HIGH = 1 << 20;
const LOW = 1 << 16;
// A socket quiet longer than Cloudflare's 100 s is cut on the way from a workspace elsewhere.
const PINGED = 30 * 1000;

const server = new WebSocketServer({ noServer: true, maxPayload: 1 << 20 });
const running = new Set();

const side = (given, otherwise) => {
  const number = Number.parseInt(given ?? '', 10);
  return Number.isSafeInteger(number) ? Math.min(SIDE.max, Math.max(SIDE.min, number)) : otherwise;
};

// The shell keeps no variable of this service's own: a `docker compose` it runs would take them
// over a project's own .env.
const environment = () => ({
  ...Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith('PONISTRA_'))),
  TERM: 'xterm-256color',
  COLORTERM: 'truecolor',
});

const shell = (socket, folder, cols, rows) => {
  const child = pty.spawn(process.env.SHELL || '/bin/bash', ['-l'], {
    name: 'xterm-256color',
    cols,
    rows,
    cwd: folder,
    env: environment(),
  });
  running.add(child);
  let paused = false;
  const drained = () => {
    if (paused && socket.bufferedAmount < LOW) {
      paused = false;
      child.resume();
    }
  };
  child.onData((text) => {
    socket.send(Buffer.from(text, 'utf8'), { binary: true }, drained);
    if (!paused && socket.bufferedAmount > HIGH) {
      paused = true;
      child.pause();
    }
  });
  child.onExit(({ exitCode }) => {
    running.delete(child);
    socket.close(EXITED, String(exitCode));
  });
  socket.on('message', (data, binary) => {
    if (binary) return child.write(data);
    let size;
    try {
      size = JSON.parse(data.toString('utf8'));
    } catch {
      return;
    }
    if (size && typeof size === 'object') child.resize(side(size.cols, child.cols), side(size.rows, child.rows));
  });
  const alive = setInterval(() => socket.ping(), PINGED);
  socket.on('close', () => {
    clearInterval(alive);
    if (running.has(child)) {
      running.delete(child);
      child.kill('SIGHUP');
    }
  });
};

const refused = (request, socket, head, code) =>
  server.handleUpgrade(request, socket, head, (opened) => opened.close(code));

/** Takes the upgrade of a request to the terminal: `allowed` reads its token, `folders` lists the
 * projects a shell may start in. */
export const upgraded = (request, socket, head, address, allowed, folders) => {
  if (!allowed(request.headers.authorization)) return refused(request, socket, head, REFUSED);
  const folder = address.searchParams.get('folder');
  if (!folders().includes(folder)) return refused(request, socket, head, UNKNOWN);
  if (running.size >= AT_MOST) return refused(request, socket, head, CROWDED);
  const cols = side(address.searchParams.get('cols'), 80);
  const rows = side(address.searchParams.get('rows'), 24);
  server.handleUpgrade(request, socket, head, (opened) => shell(opened, folder, cols, rows));
};
