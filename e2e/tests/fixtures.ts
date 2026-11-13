import {
  expect,
  request,
  test as base,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { appendFileSync, existsSync, readFileSync } from 'node:fs';
import { posix, relative } from 'node:path';

export { expect };

type Account = { own: string; colleague: string; administrator: string; name: string };

type Started = { password: string; workers: Account[][] };

/** What `manage.py e2e_session start` printed for this worker and this try of the test: the
 * session of an account of its own, of a colleague and of an administrator, so that no test meets
 * another worker's and a test tried again none of what its first try left, the colleague's name,
 * and the password they all confirm with. */
export function sessions(): Account & { password: string } {
  const session = process.env.PONISTRA_SESSION;
  if (!session) throw new Error('PONISTRA_SESSION is not set; scripts/check.sh starts one');
  const { password, workers }: Started = JSON.parse(session);
  const { parallelIndex, retry } = base.info();
  const account = workers[parallelIndex]?.[retry];
  if (!account)
    throw new Error(`PONISTRA_SESSION holds no account for worker ${parallelIndex}, try ${retry}`);
  return { ...account, password };
}

/** The session confirmed as a sign-in confirms it (D33): a run outlasts the minutes one holds. */
async function confirmed(baseURL: string, session: string): Promise<void> {
  const token = randomBytes(16).toString('hex');
  const api = await request.newContext({
    baseURL,
    extraHTTPHeaders: { Cookie: `sessionid=${session}; csrftoken=${token}`, 'X-CSRFToken': token },
  });
  const response = await api.post('/api/auth/confirm', { data: { password: sessions().password } });
  await api.dispose();
  if (!response.ok()) throw new Error(`POST /api/auth/confirm: ${response.status()}`);
}

/** An account a worker's tests share starts each test with nothing chosen, as a test's fresh browser does. */
async function unchosen(baseURL: string, session: string): Promise<void> {
  const token = randomBytes(16).toString('hex');
  const api = await request.newContext({
    baseURL,
    extraHTTPHeaders: { Cookie: `sessionid=${session}; csrftoken=${token}`, 'X-CSRFToken': token },
  });
  const { user } = await (await api.get('/api/auth/session')).json();
  const chosen = [
    user.language,
    user.theme,
    user.projects_theme,
    user.meetings_theme,
    user.sign_in,
  ];
  if (chosen.some(Boolean) || Object.keys(user.call).length > 0) {
    const response = await api.patch('/api/auth/preferences', {
      data: {
        language: '',
        theme: '',
        projects_theme: '',
        meetings_theme: '',
        sign_in: '',
        call: {},
      },
    });
    if (!response.ok()) throw new Error(`PATCH /api/auth/preferences: ${response.status()}`);
  }
  await api.dispose();
}

/** Where a full run of scripts/check.sh keeps the files each test ran (scripts/select.py). */
const MAP = process.env.PONISTRA_MAP;

/** Tells the backend which test runs from now on, or `-` for none, to note the files it runs. */
async function mark(baseURL: string, test: string): Promise<void> {
  const api = await request.newContext({ baseURL, extraHTTPHeaders: { 'X-Ponistra-Test': test } });
  const response = await api.get('/api/ping');
  await api.dispose();
  if (!response.ok()) throw new Error(`GET /api/ping: ${response.status()}`);
}

type Covered = {
  url: string;
  functions: { ranges: { startOffset: number; count: number }[] }[];
}[];

/** A built chunk as its source map tells it: where each of its lines starts, and on each line
 * the segments [column, source, line in the source] in order (source -1 where none). */
type Chunk = {
  starts: number[];
  lines: [number, number, number][][];
  files: (string | null)[];
  texts: string[][];
};

const BASE64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function segments(mappings: string): [number, number, number][][] {
  const lines: [number, number, number][][] = [];
  let source = 0;
  let line = 0;
  for (const text of mappings.split(';')) {
    const found: [number, number, number][] = [];
    let column = 0;
    for (const segment of text.split(',')) {
      if (!segment) continue;
      const values: number[] = [];
      let value = 0;
      let shift = 0;
      for (const char of segment) {
        const digit = BASE64.indexOf(char);
        value += (digit & 31) * 2 ** shift;
        if (digit & 32) {
          shift += 5;
        } else {
          values.push(value % 2 ? -(value - 1) / 2 : value / 2);
          value = shift = 0;
        }
      }
      column += values[0];
      if (values.length < 4) {
        found.push([column, -1, -1]);
      } else {
        source += values[1];
        line += values[2];
        found.push([column, source, line]);
      }
    }
    lines.push(found);
  }
  return lines;
}

const chunks = new Map<string, Promise<Chunk | null>>();

/** The chunk at `url` with its map from the site image (compose.check.yml); null for rolldown's
 * runtime, pdf.js's form sandbox (`pdf/form.ts` imports it as a `?url` asset) and the files a
 * package fetches as it runs, served as they are from a folder below `assets` (`packaged` in
 * `vite.config.ts`): the scripts without a map, as none of their code comes from a source of ours. */
function chunk(url: string): Promise<Chunk | null> {
  let found = chunks.get(url);
  if (!found) {
    found = (async () => {
      const path = new URL(url).pathname;
      if (posix.dirname(path) !== '/assets') return null;
      const name = posix.basename(path);
      const file = `/maps/${name}.map`;
      if (!existsSync(file)) {
        if (name.startsWith('rolldown-runtime-') || name.startsWith('pdf.sandbox.')) return null;
        throw new Error(
          `${file} is missing: the maps volume is an earlier build's (docker compose down --volumes)`,
        );
      }
      const map = JSON.parse(readFileSync(file, 'utf8'));
      const response = await fetch(url);
      if (!response.ok) throw new Error(`GET ${url}: ${response.status}`);
      const text = await response.text();
      const starts = [0];
      for (let at = text.indexOf('\n'); at >= 0; at = text.indexOf('\n', at + 1)) {
        starts.push(at + 1);
      }
      return {
        starts,
        lines: segments(map.mappings),
        files: (map.sources as string[]).map((source) => {
          const path = posix.join('frontend/dist/assets', source);
          return path.startsWith('frontend/src/') ? path : null;
        }),
        texts: (map.sourcesContent as (string | null)[]).map((content) =>
          (content ?? '').split('\n'),
        ),
      };
    })();
    chunks.set(url, found);
  }
  return found;
}

/** The index of the last item at or before `at` (-1 for none), in items ordered by `place`. */
function before<T>(items: T[], at: number, place: (item: T) => number): number {
  let low = 0;
  let high = items.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (place(items[middle]) <= at) low = middle + 1;
    else high = middle;
  }
  return low - 1;
}

// select.py's units(): a top-level part starts on a line that does not start with a blank or a
// closing bracket, and a function, class or binding is known by its name, which the map's keys
// must match for select.py to find them.
const IMPORT = /^(import[\s{*]|export\s*(type\s*)?[{*])/;
const DECLARATION =
  /^(?:export\s+(?:default\s+)?)?(?:declare\s+)?(?:async\s+)?(?:abstract\s+)?(function\*?|const\s+enum|const|let|var|class|enum|type|interface)\s+([\w$]+)/;

function part(lines: string[], line: number): string | null {
  for (let at = line; at >= 0; at--) {
    const text = lines[at];
    if (!text || ' \t)]}/*'.includes(text[0])) continue;
    if (IMPORT.test(text)) return null;
    const declaration = DECLARATION.exec(text);
    return declaration && !['type', 'interface'].includes(declaration[1]) ? declaration[2] : null;
  }
  return null;
}

/** Adds the app's own source files in which a page ran a function, each also with the name of
 * the top-level part the function belongs to (`file#name`), read through the build's maps. */
async function note(scripts: Covered, files: Set<string>): Promise<void> {
  for (const { url, functions } of scripts) {
    if (!url.startsWith('http') || !new URL(url).pathname.startsWith('/assets/')) continue;
    const built = await chunk(url);
    if (!built) continue;
    // The first is the chunk's own top level.
    for (const { ranges } of functions.slice(1)) {
      if (!ranges[0].count) continue;
      const offset = ranges[0].startOffset;
      const line = before(built.starts, offset, (start) => start);
      const found =
        built.lines[line]?.[
          before(built.lines[line], offset - built.starts[line], ([column]) => column)
        ];
      if (!found || found[1] < 0) continue;
      const file = built.files[found[1]];
      if (!file) continue;
      files.add(file);
      const name = part(built.texts[found[1]], found[2]);
      if (name) files.add(`${file}#${name}`);
    }
  }
}

/** Notes into `files` what every page of the test's browser runs, its other contexts' included.
 * V8 forgets a document's counts once its page leaves it, and DevTools answers nothing while a
 * navigation is under way, so they are taken before each of the test's own navigations, before a
 * page or its context closes, and when the returned function is called; a document the app itself
 * leaves takes its counts with it. */
function noting(browser: Browser, files: Set<string>) {
  const takes = new Map<Page, () => Promise<void>>();
  const cover = async (page: Page) => {
    if (takes.has(page)) return;
    const cdp = await page.context().newCDPSession(page);
    const take = async () => {
      try {
        const { result } = await cdp.send('Profiler.takePreciseCoverage');
        await note(result, files);
      } catch (error) {
        if (!page.isClosed()) throw error;
      }
    };
    await cdp.send('Profiler.enable');
    await cdp.send('Profiler.startPreciseCoverage', { callCount: true, detailed: false });
    takes.set(page, take);
    for (const name of ['goto', 'reload', 'goBack', 'goForward', 'close'] as const) {
      const leave = page[name].bind(page) as (...args: unknown[]) => Promise<never>;
      page[name] = async (...args: unknown[]) => {
        await take();
        return leave(...args);
      };
    }
  };
  const covering = (page: Page) =>
    void cover(page).catch((error) => {
      if (!page.isClosed()) throw error;
    });
  const watch = (context: BrowserContext) => {
    context.on('page', covering);
    const close = context.close.bind(context);
    context.close = async (options) => {
      await Promise.all(context.pages().map((page) => takes.get(page)?.()));
      return close(options);
    };
  };
  browser.contexts().forEach(watch);
  browser.on('context', watch);
  return {
    cover,
    async taken() {
      browser.off('context', watch);
      await Promise.all([...takes.values()].map((take) => take()));
    },
  };
}

export const test = base.extend<{ administrator: boolean; problems: string[]; mapped: void }>({
  administrator: [false, { option: true }],
  mapped: [
    async ({ browser, page, baseURL }, use, testInfo) => {
      if (!MAP) return use();
      const test = `${relative('/e2e', testInfo.file)}:${testInfo.line}`;
      const files = new Set<string>();
      const pages = noting(browser, files);
      await pages.cover(page);
      await mark(baseURL!, test);
      await use();
      await pages.taken();
      await mark(baseURL!, '-');
      appendFileSync(
        `${MAP}/e2e-frontend.jsonl`,
        `${JSON.stringify({ test, files: [...files] })}\n`,
      );
    },
    { auto: true },
  ],
  problems: async ({}, use) => {
    const problems: string[] = [];
    await use(problems);
    expect(problems).toEqual([]);
  },
  context: async ({ context, baseURL, problems, administrator }, use) => {
    const account = sessions();
    const { colleague } = account;
    const session = administrator ? account.administrator : account.own;
    await Promise.all([confirmed(baseURL!, session), confirmed(baseURL!, colleague)]);
    await unchosen(baseURL!, session);
    // A browser signs in holding a CSRF cookie; without one, each request the page starts at
    // once is given a different secret, and a token read from one fails beside another's cookie.
    await context.addCookies([
      { name: 'sessionid', value: session, url: baseURL! },
      { name: 'csrftoken', value: randomBytes(16).toString('hex'), url: baseURL! },
    ]);
    context.on('page', (page) => {
      page.on('pageerror', (error) => problems.push(`${page.url()} ${error.message}`));
      page.on('console', (message) => {
        if (message.type() === 'error' || message.type() === 'warning') {
          problems.push(`${page.url()} ${message.type()}: ${message.text()}`);
        }
      });
    });
    await use(context);
  },
});
