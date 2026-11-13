// The service worker shows what the backend pushes, opens what a notification leads to and keeps
// what another app shares until the page at SHARE places it (D26-4). On a device marked to work
// without the network (D45) the page keeps the app in SHELL, which serves the built files, named
// by their content, and the app's page while the server cannot be reached; elsewhere SHELL is
// empty and the app always comes from the server.
const SHARE = '/share';
const SHARED = 'shared';
const SHELL = 'ponistra-shell';
const ASSETS = '/assets/*';

self.addEventListener('install', (event) => {
  // The share target and a page's navigation wake the worker; a built file comes from SHELL, or
  // the network where SHELL lacks it, and every other request goes to the network untouched.
  if (event.addRoutes)
    event.waitUntil(
      event.addRoutes([
        { condition: { urlPattern: new URLPattern({ pathname: SHARE }) }, source: 'fetch-event' },
        { condition: { requestMode: 'navigate' }, source: 'fetch-event' },
        { condition: { urlPattern: new URLPattern({ pathname: ASSETS }) }, source: 'cache' },
        { condition: { urlPattern: new URLPattern({ pathname: '/*' }) }, source: 'network' },
      ]),
    );
  self.skipWaiting();
});
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

// The Projects page in its window beside the app (`workspace.ts`).
const BESIDE = '/workspace/beside';

async function windows() {
  return self.clients.matchAll({ type: 'window', includeUncontrolled: true });
}

self.addEventListener('push', (event) => {
  if (!event.data) return;
  const notice = event.data.json();
  event.waitUntil(
    (async () => {
      // The open app shows new mail, messages and rings itself, and counts them on its icon.
      if ((await windows()).some((each) => each.visibilityState === 'visible')) return;
      if (self.navigator.setAppBadge)
        await (notice.unread > 0
          ? self.navigator.setAppBadge(notice.unread)
          : self.navigator.clearAppBadge());
      await self.registration.showNotification(notice.title, {
        body: notice.body,
        tag: notice.tag || undefined,
        renotify: Boolean(notice.tag),
        requireInteraction: notice.kind === 'ring',
        icon: '/icon-192.png',
        badge: '/badge-96.png',
        actions: notice.actions,
        data: { url: notice.url, session: notice.session, answer: notice.answer },
      });
    })(),
  );
});

/** Yes or No without opening the app: to what a waiting chat asks, as its panel would (KR13), or
    to a proposal for the memory at its own address (MEM5). */
async function answered(data, text) {
  // A worker reads no document.cookie; the browsers that show a notification's actions all
  // give it the cookie store.
  const csrf = self.cookieStore && (await self.cookieStore.get('csrftoken'));
  if (!csrf) return false;
  try {
    const [address, asked] = data.answer
      ? [data.answer, { text }]
      : ['/api/workspace/commands', { kind: 'answer', session: data.session, text }];
    const response = await fetch(address, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': decodeURIComponent(csrf.value),
      },
      body: JSON.stringify(asked),
    });
    return response.ok && (await response.json()).state !== 'failed';
  } catch {
    return false;
  }
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const url = data.url || '/';
  event.waitUntil(
    (async () => {
      const answer = event.action === 'yes' || event.action === 'no';
      // An answer that did not reach the chat opens the page, where the owner sees why.
      if (answer && (data.session || data.answer) && (await answered(data, event.action))) return;
      const ours = (await windows()).filter(
        (each) => new URL(each.url).origin === self.location.origin,
      );
      const isBeside = (each) => new URL(each.url).pathname === BESIDE;
      const beside = url.startsWith('/workspace') && ours.find(isBeside);
      const open = beside || ours.find((each) => !isBeside(each));
      const target = beside ? url.replace(/^\/workspace/, BESIDE) : url;
      if (open) {
        await open.focus();
        open.postMessage({ type: 'open', url: target });
      } else {
        await self.clients.openWindow(url);
      }
    })(),
  );
});

function store() {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open('ponistra', 1);
    opening.onupgradeneeded = () => opening.result.createObjectStore(SHARED);
    opening.onsuccess = () => resolve(opening.result);
    opening.onerror = () => reject(opening.error);
  });
}

async function kept(asked) {
  const database = await store();
  try {
    return await new Promise((resolve, reject) => {
      const request = asked(database.transaction(SHARED, 'readwrite').objectStore(SHARED));
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally {
    database.close();
  }
}

/** The app's page from the network, or kept in SHELL while the server cannot be reached. */
async function navigated(request) {
  try {
    return await fetch(request);
  } catch (error) {
    const kept = await caches.match('/', { cacheName: SHELL });
    if (kept) return kept;
    throw error;
  }
}

/** A built file, for a browser without the router that serves it from SHELL itself. */
async function built(request) {
  return (await caches.match(request, { cacheName: SHELL })) ?? fetch(request);
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const { pathname } = new URL(request.url);
  if (request.method === 'GET' && request.mode === 'navigate' && pathname !== SHARE) {
    event.respondWith(navigated(request));
    return;
  }
  if (request.method === 'GET' && pathname.startsWith('/assets/')) {
    event.respondWith(built(request));
    return;
  }
  if (request.method !== 'POST' || pathname !== SHARE) return;
  event.respondWith(
    (async () => {
      const form = await request.formData();
      const told = (name) => {
        const value = form.get(name);
        return typeof value === 'string' ? value : '';
      };
      const shared = {
        title: told('title'),
        text: told('text'),
        url: told('url'),
        files: form.getAll('files').filter((each) => each instanceof File && each.name),
      };
      await kept((each) => each.put(shared, SHARED));
      return Response.redirect(new URL(SHARE, self.location.origin).href, 303);
    })(),
  );
});

const ASKED = {
  shared: (each) => each.get(SHARED),
  forget: (each) => each.delete(SHARED),
};

self.addEventListener('message', (event) => {
  const asked = event.data && ASKED[event.data.type];
  if (!asked) return;
  const [port] = event.ports;
  event.waitUntil(
    kept(asked).then(
      (value) => port.postMessage({ value: value ?? null }),
      (error) => port.postMessage({ error: String(error) }),
    ),
  );
});
