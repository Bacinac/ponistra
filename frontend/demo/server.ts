import { tellServerNeeded } from './banner';
import { missing, realFetch, recordedFile, type Frame, type Recorded } from './recording';
import { WRITES } from './writes';

/** What the backend answers, by "METHOD /path?query": the recorded answers, changed by what the
 * visitor does in this tab. */
export type Answers = Map<string, Recorded>;

export interface Asked {
  method: string;
  url: URL;
  key: string;
  body: unknown;
}

/** An answer a write gives: JSON, or nothing (204). */
export interface Given {
  status: number;
  body?: unknown;
}

type Told = (message: Frame) => void;

const SERVED = /^\/(api\/|dav(\/|$)|\.well-known\/(carddav|caldav|oauth-)|livekit(\/|$))/;

export function served(url: URL): boolean {
  return url.origin === location.origin && SERVED.test(url.pathname);
}

export function keyOf(method: string, url: URL): string {
  return `${method} ${url.pathname}${url.search}`;
}

function json(status: number, body: unknown, head = false): Response {
  const empty = head || status === 204 || body === undefined;
  return new Response(empty ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  });
}

/** Refuses what only the backend can do, saying so on the page. */
export function declined(key: string): Given {
  console.info('demo declines', key);
  tellServerNeeded();
  return { status: 501, body: { error: 'demo_server' } };
}

async function bodyOf(request: Request): Promise<unknown> {
  if (request.method === 'GET' || request.method === 'HEAD') return undefined;
  const type = request.headers.get('Content-Type') ?? '';
  if (type.includes('application/json')) {
    const text = await request.text();
    return text ? JSON.parse(text) : undefined;
  }
  return request.body ? await request.blob() : undefined;
}

/** The key without the time zone the page asked in: a visitor's zone is not the walk's. */
function zoneless(key: string): string {
  return key.replace(/([?&]zone=)[^&]*/, '$1');
}

export class Server {
  private told = new Set<Told>();
  private zoned = new Map<string, string>();

  /** What the live socket last said of the user's calls and conversations. */
  constructor(
    readonly answers: Answers,
    readonly live: Frame | null,
  ) {
    for (const key of answers.keys()) if (key.includes('zone=')) this.zoned.set(zoneless(key), key);
  }

  /** The recorded JSON answer to a read, which a write changes in place. */
  read<T>(key: string): T | undefined {
    const recorded = this.answers.get(key);
    return recorded && 'body' in recorded ? (recorded.body as T) : undefined;
  }

  /** Every recorded read whose key matches, with its body, for a write to change. */
  *reads<T>(pattern: RegExp): Generator<[string, T]> {
    for (const [key, recorded] of this.answers) {
      if ('body' in recorded && pattern.test(key)) yield [key, recorded.body as T];
    }
  }

  write(key: string, body: unknown, status = 200): void {
    this.answers.set(key, { status, body });
  }

  /** Tells the tab's live socket the areas a write changed, as the backend would, and the state
   * again when the write changed it. */
  tell(areas: string[], state = false): void {
    for (const each of this.told) {
      if (state && this.live) each(this.live);
      each({ type: 'changed', areas });
    }
  }

  onTell(told: Told): () => void {
    this.told.add(told);
    return () => this.told.delete(told);
  }

  async answer(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const method = request.method;
    const key = keyOf(method, url);
    const asked: Asked = { method, url, key, body: await bodyOf(request) };
    for (const write of WRITES) {
      if (write.method !== method) continue;
      const match = write.path.exec(url.pathname);
      if (!match) continue;
      const given = await write.run(this, asked, match);
      return json(given.status, given.body, method === 'HEAD');
    }
    if (method === 'GET' || method === 'HEAD') {
      const read = `GET ${url.pathname}${url.search}`;
      const recorded =
        this.answers.get(read) ?? this.answers.get(this.zoned.get(zoneless(read)) ?? '');
      if (recorded) return this.recorded(recorded, method === 'HEAD');
      missing(key);
      tellServerNeeded();
      return json(404, { error: 'demo_server' }, method === 'HEAD');
    }
    const given = declined(key);
    return json(given.status, given.body);
  }

  private async recorded(recorded: Recorded, head: boolean): Promise<Response> {
    if ('body' in recorded) return json(recorded.status, recorded.body, head);
    const file = await recordedFile(`blobs/${recorded.blob}`);
    if (!file) throw new Error(`The demo's recording has no blob ${recorded.blob}`);
    return new Response(head ? null : await file.blob(), {
      status: recorded.status,
      headers: { 'Content-Type': recorded.type, 'Cache-Control': 'no-store' },
    });
  }
}

/** Answers the page's own requests for the backend from the server in this tab. */
export function installFetch(server: Server): void {
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    if (!served(new URL(request.url))) return realFetch(input, init);
    return server.answer(request);
  };
}
