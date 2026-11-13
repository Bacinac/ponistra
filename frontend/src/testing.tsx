import { QueryClientProvider } from '@tanstack/react-query';
import { cleanup, configure, render, screen, waitFor } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { StrictMode } from 'react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { expect, onTestFinished, vi } from 'vitest';
import { SESSION_KEY, type Me } from './auth';
import { newQueryClient, ROUTES } from './root';

// As long as the browser's tests wait (e2e/playwright.config.ts): a page waits on its timers and
// on the host's other work alike.
configure({ asyncUtilTimeout: 10_000 });
vi.setConfig({ testTimeout: 60_000 });

/** jsdom lays nothing out and lacks what the browser gives Radix and the app: a page is as wide
 * as the browser's tests make it. */
const WIDTH = 1500;
globalThis.matchMedia = (query: string) =>
  ({
    matches: Number(query.match(/min-width:\s*(\d+)px/)?.[1] ?? Infinity) <= WIDTH,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  }) as MediaQueryList;
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
Object.defineProperty(navigator, 'locks', {
  configurable: true,
  value: {
    // One page alone: each lock asked for is its at once.
    request: (name: string, ...rest: unknown[]) => {
      const granted = rest[rest.length - 1] as LockGrantedCallback<unknown>;
      return Promise.resolve(granted({ name, mode: 'exclusive' }));
    },
  },
});
Element.prototype.scrollIntoView ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;
Element.prototype.releasePointerCapture ??= () => {};

type Handler = (request: Request, params: Record<string, string>) => unknown;

let signedIn: ReturnType<typeof session> | null = null;

/** What the shell around every page asks for, as an installation with nothing in it answers. */
const SHELL: Record<string, Handler> = {
  'GET /api/version': () => ({
    version: '0.0.0',
    sha: '0000000',
    committed_at: '2026-01-01T00:00:00Z',
    dirty: false,
  }),
  'GET /api/actions': () => ({ actions: [], ai: false }),
  'GET /api/nodes/favourites': () => ({ children: [] }),
  'GET /api/speech/consent': () => ({ enabled: false, understands: false, given_at: null }),
  'GET /api/mail/mailboxes': () => ({ mailboxes: [] }),
  'GET /api/mail/accounts': () => ({
    mailboxes: [],
    role: null,
    accounts: [],
    signature: '',
    folders: [],
    images: [],
    rules: [],
    plain: [],
    app_passwords: {},
    providers: {},
  }),
  'GET /api/nodes': () => ({
    path: [],
    root: 'mine',
    role: 'own',
    confined: false,
    folder: null,
    children: [],
  }),
  'GET /api/nodes/company': () => ({ children: [] }),
  'GET /api/vault': () => null,
  'GET /api/nodes/shared': () => ({ children: [] }),
  'GET /api/calendar/events': () => ({
    events: [],
    bookings: [],
    holidays: [],
    days_off: [],
    birthdays: [],
  }),
};

/** The socket the page hears its live changes over, which a served test's backend holds connecting:
 * the server is there, so what needs it stays enabled (D45). Every other socket is jsdom's own. */
class Connecting extends EventTarget {
  readonly readyState = WebSocket.CONNECTING;
  close(): void {}
  send(): void {}
}

function reached(socket: typeof WebSocket, given: unknown[]): object {
  return new URL(String(given[0])).pathname === '/api/live'
    ? new Connecting()
    : Reflect.construct(socket, given);
}

/** The backend a component test talks to: each `METHOD /path` (a `:name` segment matches any) is
 * answered by its handler, as JSON unless it returns a Response, and the session by the user
 * `open` signed in. A request none takes fails the test, as does anything the page logs as an
 * error or a warning. */
export function serve(handlers: Record<string, Handler>): void {
  const routes = Object.entries({ ...SHELL, ...handlers }).map(([key, handler]) => {
    const [method, path] = key.split(' ');
    return { method, parts: path.split('/'), handler };
  });
  const unserved: string[] = [];
  const problems: unknown[][] = [];
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(new URL(String(input), location.href), init);
    const parts = new URL(request.url).pathname.split('/');
    for (const route of routes) {
      if (route.method !== request.method || route.parts.length !== parts.length) continue;
      const params: Record<string, string> = {};
      const matched = route.parts.every((part, at) => {
        if (part.startsWith(':')) params[part.slice(1)] = parts[at];
        return part.startsWith(':') || part === parts[at];
      });
      if (!matched) continue;
      const answer = await route.handler(request, params);
      if (answer instanceof Response) return answer;
      return answer === undefined
        ? new Response(null, { status: 204 })
        : Response.json(answer, { status: request.method === 'POST' ? 201 : 200 });
    }
    if (signedIn && request.method === 'GET' && request.url.endsWith('/api/auth/session')) {
      return Response.json(signedIn);
    }
    unserved.push(`${request.method} ${new URL(request.url).pathname}`);
    return new Response(null, { status: 404 });
  });
  vi.stubGlobal('WebSocket', new Proxy(WebSocket, { construct: reached }));
  for (const level of ['error', 'warn'] as const) {
    vi.spyOn(console, level).mockImplementation((...args) => void problems.push(args));
  }
  onTestFinished(() => {
    cleanup();
    signedIn = null;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    expect(unserved).toEqual([]);
    expect(problems).toEqual([]);
  });
}

/** The files the page hands the user to save, by the name it gives them: jsdom has no blob URLs
 * and navigates nowhere. */
export function downloads(): { name: string; file: Blob }[] {
  const saved: { name: string; file: Blob }[] = [];
  const blobs = new Map<string, Blob>();
  Object.assign(URL, {
    createObjectURL: (blob: Blob) => {
      const url = `blob:${location.origin}/${blobs.size}`;
      blobs.set(url, blob);
      return url;
    },
    revokeObjectURL: () => {},
  });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push({ name: this.download, file: blobs.get(this.href)! });
  });
  return saved;
}

function session(user: Partial<Me> = {}) {
  return {
    user: {
      id: 1,
      email: 'ja@example.com',
      name: 'Ja',
      is_admin: false,
      workspace: null,
      language: '' as const,
      theme: '' as const,
      projects_theme: '' as const,
      meetings_theme: '' as const,
      call: {},
      backdrop: null,
      ...user,
    },
    passkey_due: false,
    setup: false,
    site: location.origin,
    providers: [],
  };
}

/** The user's actions refuse an element the page has replaced since it was found, which they
 * would otherwise reach silently and to no effect. */
function connected(user: UserEvent): UserEvent {
  return new Proxy(user, {
    get(target, key) {
      const action = Reflect.get(target, key);
      if (typeof action !== 'function') return action;
      return (element: unknown, ...rest: unknown[]) => {
        if (element instanceof Element && !element.isConnected)
          throw new Error(`${String(key)}: the page has replaced this element since it was found`);
        return action.call(target, element, ...rest);
      };
    },
  });
}

/** Renders the app at `path` as main.tsx renders it, once the user is signed in; `settled` waits
 * until what it asked for has come, as parts of the page are laid out anew once it does. */
export function open(path: string, user: Partial<Me> = {}) {
  const queryClient = newQueryClient();
  signedIn = session(user);
  queryClient.setQueryData(SESSION_KEY, signedIn);
  const router = createMemoryRouter(ROUTES, { initialEntries: [path] });
  render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>,
  );
  const settled = () =>
    waitFor(() => {
      expect(queryClient.isFetching() + queryClient.isMutating()).toBe(0);
      expect(screen.queryAllByText('Učitavanje…')).toEqual([]);
    });
  return { user: connected(userEvent.setup()), router, settled };
}
