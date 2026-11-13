import type { Page, Request } from '@playwright/test';

/** The pages every walk starts from: each module's own, whatever its links lead to after. */
export const SEEDS = [
  '/',
  '/documents',
  '/shared',
  '/favourites',
  '/notes',
  '/links',
  '/boards',
  '/tasks',
  '/mail',
  '/contacts',
  '/chat',
  '/calendar',
  '/calendar/day',
  '/calendar/week',
  '/calendar/month',
  '/vault',
  '/help',
  '/search',
  '/company',
  '/share',
  '/trash',
  '/users',
  '/resources',
  '/workdays',
  '/retention',
  '/ai',
  '/providers',
  '/meetings',
  '/applications',
  '/health',
  '/journal',
  '/settings',
];

/** What a visitor of the demo never reaches: the printer's and a meeting's pages, the doors of
    outside visitors, the workspace a demo has none of. */
const AWAY = /^\/(api|print|meet|o|v|workspace|login|logout)(\/|$)/;

/** A calendar's day links lead on without end; two weeks either side of today are the demo's. */
const DAYS = 14;

export function walkable(href: string, origin: string): string | null {
  let url: URL;
  try {
    url = new URL(href, origin);
  } catch {
    return null;
  }
  if (url.origin !== origin || AWAY.test(url.pathname)) return null;
  const day = url.pathname.match(/^\/calendar\/\w+\/(\d{4}-\d\d-\d\d)/);
  if (day && Math.abs(Date.parse(day[1]) - Date.now()) > DAYS * 86_400_000) return null;
  // A node's address carries its title before its id; the page is the same by its id alone.
  const node = url.pathname.match(/^\/(d|f|p)\/(?:[a-z0-9-]*-)?([0-9A-Za-z]{22})(\/.*)?$/);
  if (node) return `/${node[1]}/${node[2]}${node[3] ?? ''}${url.search}`;
  return url.pathname + url.search;
}

const ROUTES: Record<string, string> = { folder: 'f', document: 'd', file: 'p' };
const DIGITS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';

/** A UUID as an address writes it, 22 base62 digits (frontend/src/address.ts). */
export function compact(uuid: string): string {
  let value = BigInt(`0x${uuid.replaceAll('-', '')}`);
  let digits = '';
  for (let place = 0; place < 22; place++) {
    digits = DIGITS[Number(value % 62n)] + digits;
    value /= 62n;
  }
  return digits;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** The documents, folders and files an answer names: a folder's rows open on a double click,
    not by a link, so the walk reads where they lead from what the API said of them. */
export function nodesIn(body: unknown, found: Set<string> = new Set()): Set<string> {
  if (Array.isArray(body)) {
    for (const each of body) nodesIn(each, found);
  } else if (body && typeof body === 'object') {
    const node = body as Record<string, unknown>;
    if (
      typeof node.id === 'string' &&
      UUID.test(node.id) &&
      typeof node.kind === 'string' &&
      !node.trashed_at
    ) {
      const route = ROUTES[node.kind];
      if (route) found.add(`/${route}/${compact(node.id)}`);
    }
    for (const value of Object.values(node)) nodesIn(value, found);
  }
  return found;
}

/** Scrolls every scrolling pane to its end, step by step, so what loads as it comes into view
    (a table's rows, a list's next page, a document's pictures) is asked for. */
export async function scrolled(page: Page, quiet: () => Promise<void>): Promise<void> {
  for (let step = 0; step < 60; step++) {
    const moved = await page.evaluate(() => {
      let any = false;
      for (const each of document.querySelectorAll<HTMLElement>('*')) {
        const style = getComputedStyle(each);
        for (const [overflow, size, view, at] of [
          [style.overflowY, 'scrollHeight', 'clientHeight', 'scrollTop'],
          [style.overflowX, 'scrollWidth', 'clientWidth', 'scrollLeft'],
        ] as const) {
          if (!/auto|scroll/.test(overflow) || each[size] <= each[view] + 4) continue;
          const before = each[at];
          each[at] = before + each[view];
          if (each[at] !== before) any = true;
        }
      }
      const before = window.scrollY;
      window.scrollBy(0, window.innerHeight);
      return any || window.scrollY !== before;
    });
    if (!moved) return;
    await quiet();
  }
}

/** The page's links a visitor could follow. */
export async function linksOn(page: Page, origin: string): Promise<string[]> {
  const hrefs = await page.$$eval('a[href]', (anchors) =>
    anchors.map((each) => each.getAttribute('href') ?? ''),
  );
  return hrefs.map((each) => walkable(each, origin)).filter((each): each is string => !!each);
}

const QUIET = 500;
const PATIENCE = 20_000;

/** The page's requests still unanswered, sockets aside: Playwright's networkidle fires once per
    load and was seen never to on some pages, while this is asked again after every scroll. */
export function watched(page: Page): () => Promise<void> {
  const open = new Set<Request>();
  let changed = Date.now();
  const done = (request: Request) => {
    open.delete(request);
    changed = Date.now();
  };
  page.on('request', (request) => {
    if (!/^https?:/.test(request.url())) return;
    open.add(request);
    changed = Date.now();
  });
  // What the page before asked and never heard back of, as it went away, is not this page's.
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) open.clear();
  });
  page.on('requestfinished', done);
  page.on('requestfailed', done);
  return async () => {
    const since = Date.now();
    while (open.size || Date.now() - changed < QUIET) {
      if (Date.now() - since > PATIENCE) {
        const left = [...open].map((each) => each.url());
        open.clear();
        throw new Error(`still waiting after ${PATIENCE / 1000} s for ${left.join(', ')}`);
      }
      await page.waitForTimeout(100);
    }
  };
}

/** Opens a page and waits for it to settle: its requests answered, a moment for what follows. */
export async function settled(page: Page, path: string, quiet: () => Promise<void>): Promise<void> {
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await quiet();
}

/** What the app says, in English, when an answer it needed failed. */
const BROKEN = ['This item does not exist or is in the trash.', 'Unexpected error'];

/** A walk over the app's pages: each page offered once, opened, scrolled to its end and its links
    offered on; `visited` hears of each page as it settles. What a page fails at, an error it shows
    among it, is noted and the walk goes on, so one run names every page that went wrong. */
export class Walk {
  readonly pages = new Set<string>();
  private readonly offered = new Set<string>();
  private readonly queue: string[] = [];
  here = '/';

  constructor(
    private readonly page: Page,
    private readonly origin: string,
    private readonly limit: number,
  ) {}

  offer(path: string): void {
    if (this.offered.has(path)) return;
    this.offered.add(path);
    this.queue.push(path);
  }

  async run(
    failed: (what: string) => void,
    visited: () => Promise<void> = async () => {},
  ): Promise<void> {
    const quiet = watched(this.page);
    while (this.queue.length) {
      const next = this.queue.shift()!;
      if (this.pages.has(next)) continue;
      if (this.pages.size >= this.limit)
        throw new Error(`more than ${this.limit} pages; the walk is running away`);
      this.pages.add(next);
      this.here = next;
      console.log(`${this.pages.size} ${next} (${this.queue.length} waiting)`);
      try {
        await settled(this.page, next, quiet);
        await scrolled(this.page, quiet);
        await visited();
        const shown = await this.page.locator('body').innerText();
        for (const broken of BROKEN)
          if (shown.includes(broken)) failed(`${next}: shows "${broken}"`);
        for (const link of await linksOn(this.page, this.origin)) this.offer(link);
        const landed = walkable(this.page.url(), this.origin);
        if (landed) this.pages.add(landed);
      } catch (error) {
        failed(`${next}: ${error instanceof Error ? error.message.split('\n')[0] : error}`);
      }
    }
  }
}
