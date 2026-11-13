import { tellServerNeeded } from './banner';
import { grids } from './grids';
import { joinRoom } from './rooms';
import type { Server } from './server';

/** The other side of a socket, in the tab. */
export interface Peer {
  /** Hears what the page sends. */
  take(data: string | ArrayBufferLike | Blob | ArrayBufferView): void;
  /** The page closed the socket. */
  left(): void;
}

type Handler = ((event: Event) => void) | null;

/** A WebSocket the demo answers in the tab, closed as a refusal where the backend alone could. */
export class DemoSocket extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;

  readyState: 0 | 1 | 2 | 3 = 0;
  binaryType: BinaryType = 'blob';
  readonly protocol = '';
  readonly extensions = '';
  readonly bufferedAmount = 0;
  onopen: Handler = null;
  onmessage: Handler = null;
  onclose: Handler = null;
  onerror: Handler = null;
  private peer: Peer | null = null;

  constructor(readonly url: string) {
    super();
    setTimeout(() => {
      if (this.readyState !== 0) return;
      this.readyState = 1;
      this.peer = connect(new URL(url), this);
      if (this.readyState === 1) this.fire(new Event('open'));
    });
  }

  private fire(event: Event): void {
    const handler = this[`on${event.type}` as 'onopen'];
    handler?.call(this, event);
    this.dispatchEvent(event);
  }

  /** What the other side says to the page. */
  deliver(data: string | Uint8Array): void {
    if (this.readyState !== 1) return;
    let given: string | ArrayBuffer | Blob;
    if (typeof data === 'string') given = data;
    else {
      const copy = data.slice().buffer as ArrayBuffer;
      given = this.binaryType === 'arraybuffer' ? copy : new Blob([copy]);
    }
    setTimeout(() => this.fire(new MessageEvent('message', { data: given })));
  }

  send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
    if (this.readyState === 0) throw new DOMException('Still connecting', 'InvalidStateError');
    if (this.readyState === 1) this.peer?.take(data);
  }

  close(code = 1000, reason = ''): void {
    if (this.readyState >= 2) return;
    this.readyState = 2;
    const peer = this.peer;
    this.peer = null;
    peer?.left();
    setTimeout(() => {
      this.readyState = 3;
      this.fire(new CloseEvent('close', { code, reason, wasClean: true }));
    });
  }
}

/** A refusal in the backend's codes: 4403 tells the app no one may have this socket. */
const REFUSED = 4403;

let server: Server;

function connect(url: URL, socket: DemoSocket): Peer | null {
  const path = url.pathname;
  if (path === '/api/live') return liveSocket(socket);
  const room = /^\/api\/collab\/([^/]+)$/.exec(path);
  if (room) return joinRoom(decodeURIComponent(room[1]), socket);
  const grid = /^\/api\/grids\/([^/]+)$/.exec(path);
  if (grid) return grids(grid[1], socket);
  tellServerNeeded();
  console.info('demo declines the socket', path);
  socket.close(REFUSED, 'demo');
  return null;
}

/** The live socket: what the walk last heard on it, and the areas the tab's writes change. */
function liveSocket(socket: DemoSocket): Peer {
  if (server.live) socket.deliver(JSON.stringify(server.live));
  const leave = server.onTell((message) => socket.deliver(JSON.stringify(message)));
  return { take: () => {}, left: leave };
}

const SERVED_SOCKETS = /^\/(api\/|livekit(\/|$)|code(\/|$))/;

/** Answers the sockets the page opens to the backend in the tab. */
export function installSockets(given: Server): void {
  server = given;
  const RealSocket = window.WebSocket;
  const Socket = function (this: unknown, url: string | URL, protocols?: string | string[]) {
    const parsed = new URL(url, location.href);
    if (parsed.host !== location.host || !SERVED_SOCKETS.test(parsed.pathname)) {
      return new RealSocket(url, protocols);
    }
    return new DemoSocket(parsed.href);
  } as unknown as typeof WebSocket;
  Object.assign(Socket, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
  Socket.prototype = DemoSocket.prototype;
  window.WebSocket = Socket;
}
