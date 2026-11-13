import { type Page, type Response, type WebSocket, expect, test } from '@playwright/test';
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { SEEDS, Walk, nodesIn } from './crawl';

/** Walks the app as the demo's user and writes what the demo answers with (frontend/demo):
    `responses.json` {"GET /api/path?query": {status, body} | {status, blob, type}}, the bodies
    that are not JSON in `blobs/<sha256>`, each room's Yjs state in `collab/<room>.bin`, the frames
    each document's grids socket sent in `grids/<document>.json`, the first state `/api/live` sent in
    `live.json`, and `meta.json`. */

const RUN = '/demo';
const OUT = `${RUN}/recorded`;
const LANGUAGE = 'en';
const OTHER_LANGUAGES = ['hr'];
const LIMIT = 1500;

/** The throwaway stack's VAPID key: public, of no use where nothing can subscribe, and read by
    gitleaks as a secret. */
const THROWAWAY_KEY = 'demo';

type Answer = { status: number; body: unknown } | { status: number; blob: string; type: string };

test('record the demo', async ({ browser, baseURL }) => {
  test.setTimeout(0);
  const started = process.env.PONISTRA_DEMO;
  if (!started) throw new Error('PONISTRA_DEMO is not set; scripts/demo.sh starts the recording');
  const sessions: Record<string, string> = JSON.parse(started);
  if (!sessions[LANGUAGE]) throw new Error(`help_seed gave no ${LANGUAGE} session`);
  const origin = new URL(baseURL!).origin;

  const at = new Date().toISOString();
  const context = await browser.newContext({
    baseURL,
    colorScheme: 'light',
    locale: 'en-GB',
    timezoneId: 'Europe/Zagreb',
    viewport: { width: 1440, height: 900 },
    // The offline worker (D45) would answer from its cache rather than the server.
    serviceWorkers: 'block',
  });
  await context.addCookies([{ name: 'sessionid', value: sessions[LANGUAGE], url: baseURL! }]);
  const page = await context.newPage();
  const walk = new Walk(page, origin, LIMIT);

  const answers: Record<string, Answer> = {};
  const writes = new Set<string>();
  const failures: string[] = [];
  const reading: Promise<void>[] = [];
  const grids: Record<string, unknown[]> = {};
  let live: unknown = null;
  const states = new Map<string, number>();
  let rooms = new Set<string>();

  const kept = async (response: Response) => {
    const url = new URL(response.url());
    if (url.origin !== origin || !url.pathname.startsWith('/api/')) return;
    const method = response.request().method();
    const key = `${method} ${url.pathname}${url.search}`;
    if (method !== 'GET' && method !== 'HEAD') writes.add(`${key} (on ${walk.here})`);
    if (key in answers) return;
    const status = response.status();
    if (status >= 500) failures.push(`${status} ${key} on ${walk.here}`);
    const type = (await response.headerValue('content-type')) ?? '';
    let bytes: Buffer;
    try {
      bytes = status >= 300 && status < 400 ? Buffer.alloc(0) : await response.body();
    } catch {
      // A body the page went away from before it came; the next visit asks for it again.
      return;
    }
    if (key in answers) return;
    const body = stored(key, status, type, bytes);
    if (body) for (const found of nodesIn(body)) walk.offer(found);
  };
  const stored = (key: string, status: number, type: string, bytes: Buffer): unknown => {
    if (type.includes('json') || bytes.length === 0) {
      const body = bytes.length ? JSON.parse(bytes.toString('utf8')) : null;
      if (key.startsWith('GET /api/push?') && body?.key) body.key = THROWAWAY_KEY;
      answers[key] = { status, body };
      return body;
    }
    const blob = createHash('sha256').update(bytes).digest('hex');
    writeFileSync(`${OUT}/blobs/${blob}`, bytes);
    answers[key] = { status, blob, type };
    return null;
  };
  page.on('response', (response) => {
    reading.push(
      kept(response).catch((error) => {
        failures.push(String(error));
      }),
    );
  });

  page.on('websocket', (socket: WebSocket) => {
    const path = new URL(socket.url()).pathname;
    if (path === '/api/live') {
      socket.on('framereceived', (frame) => {
        if (typeof frame.payload !== 'string') return;
        const said = JSON.parse(frame.payload);
        if (said?.type === 'state' && !live) live = said;
      });
    }
    const room = path.match(/^\/api\/collab\/([^/]+)$/)?.[1];
    if (room) rooms.add(room);
    const document = path.match(/^\/api\/grids\/([^/]+)$/)?.[1];
    if (document) {
      const frames = (grids[document] ??= []);
      socket.on('framereceived', (frame) => {
        if (typeof frame.payload === 'string') frames.push(JSON.parse(frame.payload));
      });
    }
  });
  page.on('pageerror', (error) => failures.push(`page error on ${walk.here}: ${error.message}`));

  /** Each room this page joined, as it holds it once the room has synced: the largest state seen
      of it, as a later visit can find a room still syncing. */
  const held = async (open: Page) => {
    for (const room of rooms) {
      let state: number[] | null = null;
      for (let tries = 0; tries < 20; tries++) {
        const now = await open.evaluate((name) => {
          const found = window.ponistraHeld?.(name);
          return found ? Array.from(found) : null;
        }, room);
        if (now && state && now.length === state.length && now.length > 2) break;
        state = now;
        await open.waitForTimeout(250);
      }
      if (!state || state.length <= (states.get(room) ?? 0)) continue;
      states.set(room, state.length);
      writeFileSync(`${OUT}/collab/${room}.bin`, Buffer.from(state));
    }
  };

  for (const each of SEEDS) walk.offer(each);
  await walk.run(
    (what) => failures.push(what),
    async () => {
      await held(page);
      rooms = new Set();
    },
  );
  await Promise.all(reading);
  // A visitor may choose another language, and what the app asks in a language (`lang=`, the
  // help) is asked of the same server in each.
  for (const key of Object.keys(answers)) {
    const [method, path] = key.split(' ');
    if (method !== 'GET' || !/[?&]lang=en(&|$)/.test(path)) continue;
    for (const other of OTHER_LANGUAGES) {
      const there = path.replace(/([?&]lang=)en(?=&|$)/, `$1${other}`);
      if (`GET ${there}` in answers) continue;
      const response = await context.request.get(there);
      if (response.status() >= 500) failures.push(`${response.status()} GET ${there}`);
      stored(
        `GET ${there}`,
        response.status(),
        response.headers()['content-type'] ?? '',
        await response.body(),
      );
    }
  }
  await context.close();

  writeFileSync(`${OUT}/responses.json`, JSON.stringify(answers));
  for (const [document, frames] of Object.entries(grids)) {
    writeFileSync(`${OUT}/grids/${document}.json`, JSON.stringify(frames));
  }
  if (!live) failures.push('/api/live sent no state');
  writeFileSync(`${OUT}/live.json`, JSON.stringify(live));
  writeFileSync(`${OUT}/meta.json`, JSON.stringify({ at, language: LANGUAGE }));
  writeFileSync(`${RUN}/pages.txt`, [...walk.pages].sort().join('\n') + '\n');
  console.log(
    `recorded ${walk.pages.size} pages, ${Object.keys(answers).length} answers, ${states.size} rooms, ${Object.keys(grids).length} grids`,
  );
  if (writes.size) console.log(`the walk wrote:\n  ${[...writes].join('\n  ')}`);
  expect(failures, 'what went wrong while recording').toEqual([]);
});

declare global {
  interface Window {
    ponistraHeld?: (room: string) => Uint8Array | null;
  }
}
