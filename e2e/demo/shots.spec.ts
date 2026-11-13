import { type Page, test } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { compact, settled, watched } from './crawl';
import { serve } from './serve';

/** The README's pictures, taken from the built demo (/site) as a visitor sees it: each screen as a
    PNG in /shots, which scripts/demo.sh turns into docs/screenshots' WebP stills and animated
    tour, and the card a link to the repository shows. */

const SITE = '/site';
const OUT = '/shots';
const RECORDED = `${SITE}/demo-recording/responses.json`;

type Holds = 'text' | 'table' | 'slides';

interface Node {
  id: string;
  kind: string;
  holds?: string;
  size?: number;
  parent?: string | null;
  trashed_at?: string | null;
}

/** Every node the recording met that is not in the trash, once. */
function recordedNodes(): Node[] {
  const answers: Record<string, { body?: unknown }> = JSON.parse(readFileSync(RECORDED, 'utf8'));
  const found = new Map<string, Node>();
  const look = (body: unknown): void => {
    if (!body || typeof body !== 'object') return;
    if (Array.isArray(body)) return body.forEach(look);
    const node = body as Record<string, unknown>;
    if (typeof node.id === 'string' && typeof node.kind === 'string' && !node.trashed_at)
      found.set(node.id, node as unknown as Node);
    Object.values(node).forEach(look);
  };
  for (const answer of Object.values(answers)) look(answer.body);
  return [...found.values()];
}

/** The largest document of this kind, the one that shows the most of it. */
function documentHolding(holds: Holds): string {
  const [largest] = recordedNodes()
    .filter((node) => node.kind === 'document' && node.holds === holds)
    .sort((one, other) => (other.size ?? 0) - (one.size ?? 0));
  if (!largest) throw new Error(`the recording holds no document of ${holds}`);
  return `/d/${compact(largest.id)}`;
}

/** The folder holding the most documents and files. */
function fullestFolder(): string {
  const counts = new Map<string, number>();
  for (const node of recordedNodes())
    if (node.kind !== 'folder' && node.parent)
      counts.set(node.parent, (counts.get(node.parent) ?? 0) + 1);
  const [fullest] = [...counts].sort((one, other) => other[1] - one[1]);
  if (!fullest) throw new Error('the recording holds no folder with documents');
  return `/f/${compact(fullest[0])}`;
}

const SCREENS: { file: string; at: () => string; ready?: (page: Page) => Promise<void> }[] = [
  { file: 'documents', at: fullestFolder },
  { file: 'text', at: () => documentHolding('text') },
  { file: 'table', at: () => documentHolding('table') },
  { file: 'slides', at: () => documentHolding('slides') },
  {
    file: 'mail',
    at: () => '/mail',
    ready: async (page) => {
      await page.locator('li[data-id] a').first().click();
      await page.locator('article').first().waitFor();
    },
  },
  { file: 'calendar', at: () => '/calendar/week' },
];

test('take the README pictures', async ({ browser }) => {
  test.setTimeout(300_000);
  const { origin, close } = await serve(SITE);
  for (const [viewport, cut] of [
    [{ width: 1440, height: 900 }, null],
    [{ width: 1280, height: 640 }, 'social-preview'],
  ] as const) {
    const context = await browser.newContext({
      baseURL: origin,
      colorScheme: 'light',
      locale: 'en-GB',
      timezoneId: 'Europe/Zagreb',
      viewport,
    });
    await context.route(
      (url) => url.origin !== origin && !/^(data|blob):$/.test(url.protocol),
      (route) => route.abort(),
    );
    const page = await context.newPage();
    const quiet = watched(page);
    for (const screen of cut ? SCREENS.filter((each) => each.file === 'text') : SCREENS) {
      console.log(`${cut ?? screen.file}`);
      await settled(page, screen.at(), quiet);
      await screen.ready?.(page);
      await quiet();
      await page.waitForTimeout(600);
      const png = await page.screenshot({ animations: 'disabled', type: 'png' });
      writeFileSync(`${OUT}/${cut ?? screen.file}.png`, png);
    }
    await context.close();
  }
  close();
});
