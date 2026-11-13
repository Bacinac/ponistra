import { type Page, expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { SEEDS, Walk } from './crawl';
import { serve } from './serve';

/** Walks the built demo (/site) through every page the recording walked and every link on them,
    then makes and writes a new document, in a container without a network: a request reaching
    /api, any socket, a request leaving the site, a file it does not have, a blank page, a page
    error or an answer the demo did not record fails it. */

const SITE = '/site';
const PAGES = '/demo/pages.txt';
const LIMIT = 3000;

/** A new document, made and written in as a visitor would: the template and the room the demo
    makes for it have no recording to fall back on. */
async function written(page: Page, note: (what: string) => void): Promise<void> {
  const words = 'Written in the demo';
  try {
    await page.goto('/documents');
    await page.getByRole('button', { name: 'New', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'New document' });
    const item = page.getByRole('menuitem', { name: 'New document' });
    await expect(dialog.or(item)).toBeVisible();
    if (await item.isVisible()) await item.click();
    await dialog.getByRole('textbox').fill('A new document');
    await page.keyboard.press('Enter');
    await page.waitForURL(/\/d\//);
    const editor = page.locator('.ProseMirror').first();
    await editor.click();
    await page.keyboard.type(words);
    await expect(editor).toContainText(words);
  } catch (error) {
    note(`a new document: ${String(error).split('\n')[0].slice(0, 200)}`);
  }
}

test('walk the built demo', async ({ browser }) => {
  test.setTimeout(0);
  const { origin, reached, close } = await serve(SITE);
  const context = await browser.newContext({
    baseURL: origin,
    colorScheme: 'light',
    locale: 'en-GB',
    timezoneId: 'Europe/Zagreb',
    viewport: { width: 1440, height: 900 },
  });
  const found = new Map<string, string>();
  let walk: Walk | null = null;
  const note = (what: string) => {
    if (!found.has(what)) found.set(what, walk?.here ?? '/');
  };
  await context.route(
    (url) => url.origin !== origin && !/^(data|blob):$/.test(url.protocol),
    (route) => {
      note(`left the site: ${route.request().url().slice(0, 160)}`);
      return route.abort();
    },
  );
  const page = await context.newPage();
  page.on('websocket', (socket) => note(`opened a socket: ${socket.url()}`));
  page.on('response', (response) => {
    // What the demo's worker answers is the recording's, a 404 among them; a gap says demo-missing.
    if (!response.fromServiceWorker() && response.status() >= 400)
      note(`${response.status()} ${new URL(response.url()).pathname}`);
  });
  page.on('pageerror', (error) => note(`page error: ${error.message.slice(0, 200)}`));
  page.on('console', (message) => {
    const text = message.text();
    if (text.startsWith('demo-missing ')) note(`not recorded: ${text.slice(13)}`);
    else if (message.type() === 'error') note(`console: ${text.slice(0, 200)}`);
  });

  walk = new Walk(page, origin, LIMIT);
  for (const each of [...SEEDS, ...readFileSync(PAGES, 'utf8').split('\n').filter(Boolean)]) {
    walk.offer(each);
  }
  await walk.run(note, async () => {
    for (const each of reached.splice(0)) note(`reached the server: ${each}`);
    if (!(await page.locator('body').innerText()).trim()) note('a blank page');
  });
  await written(page, note);
  await context.close();
  close();
  console.log(`walked ${walk.pages.size} pages of the demo`);
  expect(
    [...found].map(([what, where]) => `${what}  (on ${where})`),
    'what the demo could not answer by itself',
  ).toEqual([]);
});
