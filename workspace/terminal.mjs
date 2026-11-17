// A terminal for PONISTRA's page of projects (KR25): a login shell in a pseudo-terminal for each
// project, in its folder, reached through a WebSocket on /ponistra/terminal. PONISTRA's backend
// opens the socket with the token and passes the browser's frames on as they come: a binary frame
// is what the owner typed, a text frame {cols, rows} resizes the terminal, {close: true} ends the
// shell, and what the shell writes comes back binary. The shell outlives its socket: a socket
// lost on the way, to an update of PONISTRA, a network or a phone asleep, leaves it running, and
// the next socket for the project is sent what it kept writing (its last KEPT) before the rest.
// A newer socket for the project takes the shell over and the older closes with TAKEN. Once the
// shell exits the socket closes with EXITED.
//
// node-pty and ws are code-server's own (both MIT), built for the node that runs this service.
import { createRequire } from 'node:module';

const vscode = createRequire('/usr/lib/code-server/lib/vscode/package.json');
const pty = vscode('node-pty');
const { WebSocketServer } = vscode('ws');

export const TERMINAL = '/ponistra/terminal';
export const EXITED = 4000;
export const TAKEN = 4409;
const REFUSED = 4403;
const UNKNOWN = 4404;
const CROWDED = 4429;
const AT_MOST = 8;
const SIDE = { min: 2, max: 1000 };
// Above this much unsent output the shell is paused, so a runaway `cat` does not fill memory.
const HIGH = 1 << 20;
const LOW = 1 << 16;
const KEPT = 2 << 20;
// A socket quiet longer than Cloudflare's 100 s is cut on the way from a workspace elsewhere.
const PINGED = 30 * 1000;

const server = new WebSocketServer({ noServer: true, maxPayload: 1 << 20 });
const shells = new Map();

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

const drained = (shell) => {
  if (shell.paused && !(shell.socket?.bufferedAmount >= LOW)) {
    shell.paused = false;
    shell.child.resume();
  }
};

const sent = (shell, text) => {
  const { socket } = shell;
  if (!socket) return;
  socket.send(Buffer.from(text, 'utf8'), { binary: true }, () => drained(shell));
  if (!shell.paused && socket.bufferedAmount > HIGH) {
    shell.paused = true;
    shell.child.pause();
  }
};

const started = (folder, cols, rows) => {
  const child = pty.spawn(process.env.SHELL || '/bin/bash', ['-l'], {
    name: 'xterm-256color',
    cols,
    rows,
    cwd: folder,
    env: environment(),
  });
  const shell = { child, written: [], size: 0, socket: null, paused: false };
  shells.set(folder, shell);
  child.onData((text) => {
    shell.written.push(text);
    shell.size += text.length;
    while (shell.size > KEPT && shell.written.length > 1) shell.size -= shell.written.shift().length;
    sent(shell, text);
  });
  child.onExit(({ exitCode }) => {
    shells.delete(folder);
    shell.socket?.close(EXITED, String(exitCode));
  });
  return shell;
};

const attached = (shell, socket, cols, rows) => {
  shell.socket?.close(TAKEN);
  shell.socket = socket;
  if (cols !== shell.child.cols || rows !== shell.child.rows) shell.child.resize(cols, rows);
  if (shell.size) sent(shell, shell.written.join(''));
  socket.on('message', (data, binary) => {
    if (shell.socket !== socket) return;
    if (binary) return shell.child.write(data);
    let given;
    try {
      given = JSON.parse(data.toString('utf8'));
    } catch {
      return;
    }
    if (!given || typeof given !== 'object') return;
    if (given.close === true) return shell.child.kill('SIGHUP');
    shell.child.resize(side(given.cols, shell.child.cols), side(given.rows, shell.child.rows));
  });
  const alive = setInterval(() => socket.ping(), PINGED);
  socket.on('close', () => {
    clearInterval(alive);
    if (shell.socket !== socket) return;
    shell.socket = null;
    drained(shell);
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
  if (!shells.has(folder) && shells.size >= AT_MOST) return refused(request, socket, head, CROWDED);
  const cols = side(address.searchParams.get('cols'), 80);
  const rows = side(address.searchParams.get('rows'), 24);
  server.handleUpgrade(request, socket, head, (opened) =>
    attached(shells.get(folder) ?? started(folder, cols, rows), opened, cols, rows),
  );
};
