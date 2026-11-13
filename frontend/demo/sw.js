/* The demo's service worker, in place of the app's (src/sw.js). The page answers its own fetches
 * to the backend (demo/server.ts); this worker answers what the page loads otherwise (images,
 * frames, media, downloads) from the walk's recording. It keeps nothing of the visitor's: what
 * they change lives in the page. */
const RECORDING = '/demo-recording';
const SERVED =
  /^\/(api\/|dav(\/|$)|\.well-known\/(carddav|caldav|oauth-)|livekit(\/|$)|code(\/|$))/;

let answers = null;

function recorded() {
  answers ??= fetch(`${RECORDING}/responses.json`).then((response) => {
    if (!response.ok) throw new Error(`The demo's recording has no answers: ${response.status}`);
    return response.json();
  });
  return answers;
}

self.addEventListener('install', (event) => {
  event.waitUntil(recorded().then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

async function told(message) {
  for (const client of await self.clients.matchAll({ type: 'window' })) client.postMessage(message);
}

async function answer(request, url) {
  const key = `${request.method} ${url.pathname}${url.search}`;
  const found =
    request.method === 'GET' || request.method === 'HEAD'
      ? (await recorded())[`GET ${url.pathname}${url.search}`]
      : undefined;
  if (!found) {
    void told({ demo: request.method === 'GET' ? 'missing' : 'declined', key });
    return new Response(JSON.stringify({ error: 'demo_server' }), {
      status: request.method === 'GET' ? 404 : 501,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  if ('body' in found) {
    return new Response(JSON.stringify(found.body), {
      status: found.status,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  const blob = await kept(found.blob);
  if (BOARD.test(url.pathname) && request.method === 'GET') {
    return new Response(await framed(await blob.text()), {
      status: found.status,
      headers: { 'Content-Type': found.type },
    });
  }
  return new Response(request.method === 'HEAD' ? null : blob.body, {
    status: found.status,
    headers: { 'Content-Type': found.type },
  });
}

async function kept(sha) {
  const blob = await fetch(`${RECORDING}/blobs/${sha}`);
  if (!blob.ok) throw new Error(`The demo's recording has no blob ${sha}`);
  return blob;
}

async function recordedText(path) {
  const found = (await recorded())[`GET ${path}`];
  if (!found || !('blob' in found)) {
    void told({ demo: 'missing', key: `GET ${path}` });
    return null;
  }
  return (await kept(found.blob)).text();
}

const BOARD = /^\/api\/nodes\/[0-9a-f-]{36}\/board$/;
const RUNTIME = /<script\s+src=["']\/api\/boards\/runtime\.js["']\s*>\s*<\/script>/gi;
const unescaped = (text) =>
  text
    .replace(/&quot;/g, '"')
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
const escaped = (text) => text.replace(/&/g, '&amp;').replace(/"/g, '&quot;');

/* A board's page runs in a sandbox of its own origin, which no service worker controls, so the
 * frame that holds it gets the recorded page inline, with the runtime it loads inlined too. */
async function framed(frame) {
  const source = frame.match(/<iframe src="([^"]*)"/);
  if (!source) throw new Error('A recorded board frame holds no page');
  const page = await recordedText(unescaped(source[1]));
  if (page === null) return frame;
  const runtime = page.search(RUNTIME) >= 0 ? await recordedText('/api/boards/runtime.js') : null;
  const whole =
    runtime === null ? page : page.replace(RUNTIME, () => `<script>${runtime}</script>`);
  return frame.replace(source[0], `<iframe srcdoc="${escaped(whole)}"`);
}

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== location.origin || !SERVED.test(url.pathname)) return;
  event.respondWith(answer(event.request, url));
});
