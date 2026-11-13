import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function sent<T>(page: Page, calls: [string, object][]): Promise<T[]> {
  return page.evaluate(async (calls) => {
    await fetch('/api/auth/session');
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const answers = [];
    for (const [path, data] of calls) {
      const response = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify(data),
      });
      if (!response.ok) throw new Error(`POST ${path}: ${response.status}`);
      answers.push(response.status === 204 ? null : await response.json());
    }
    return answers;
  }, calls);
}

async function boards(page: Page, titles: string[], group: string) {
  await page.evaluate(
    async ({ titles, group }) => {
      await fetch('/api/auth/session');
      const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
      const json = { 'Content-Type': 'application/json', 'X-CSRFToken': token };
      const data = new TextEncoder().encode('<!doctype html><p>Ploča</p>');
      let upload = await (
        await fetch('/api/uploads', {
          method: 'POST',
          headers: json,
          body: JSON.stringify({ size: data.length }),
        })
      ).json();
      while (upload.blob === null) {
        const part = await fetch(`/api/uploads/${upload.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/octet-stream',
            'X-CSRFToken': token,
            'Upload-Offset': String(upload.received),
          },
          body: data.slice(upload.received, upload.received + upload.chunk),
        });
        upload = await part.json();
      }
      for (const title of titles) {
        const made = await fetch('/api/nodes', {
          method: 'POST',
          headers: json,
          body: JSON.stringify({
            kind: 'file',
            title,
            blob: upload.blob.sha256,
            extension: 'html',
          }),
        });
        if (!made.ok) throw new Error(`POST /api/nodes: ${made.status}`);
        const { id } = (await made.json()) as { id: string };
        const filed = await fetch('/api/nodes/boards', {
          method: 'POST',
          headers: json,
          body: JSON.stringify({ node: id, group }),
        });
        if (!filed.ok) throw new Error(`POST /api/nodes/boards: ${filed.status}`);
      }
    },
    { titles, group },
  );
}

const documents = (titles: string[]): [string, object][] =>
  titles.map((title) => ['/api/nodes', { kind: 'document', title, parent: null }]);

const LISTS: {
  name: string;
  url: string;
  fill: (page: Page, titles: string[], stamp: number) => Promise<unknown>;
  deleted: 'gone' | 'dialog';
}[] = [
  {
    name: 'a folder',
    url: '/documents',
    fill: (page, titles) => sent(page, documents(titles)),
    deleted: 'gone',
  },
  {
    name: 'boards',
    url: '/boards',
    fill: (page, titles, stamp) => boards(page, titles, `Skupina ${stamp}`),
    deleted: 'gone',
  },
  {
    name: 'notes',
    url: '/notes',
    fill: (page, titles) =>
      sent(
        page,
        titles.map((text) => ['/api/notes', { text }]),
      ),
    deleted: 'gone',
  },
  {
    name: 'links',
    url: '/links',
    fill: async (page, titles) => {
      const [place] = await sent<{ id: string }>(page, [['/api/links', {}]]);
      await sent(
        page,
        titles.map((title, at) => [
          '/api/nodes',
          { kind: 'link', title, href: `https://example.com/${at}`, parent: place.id },
        ]),
      );
    },
    deleted: 'gone',
  },
  {
    name: 'the trash',
    url: '/trash',
    fill: async (page, titles) => {
      const made = await sent<{ id: string }>(page, documents(titles));
      await sent(page, [['/api/nodes/trash', { nodes: made.map((each) => each.id) }]]);
    },
    deleted: 'dialog',
  },
  {
    name: 'contacts',
    url: '/contacts',
    fill: (page, titles) =>
      sent(
        page,
        titles.map((given) => [
          '/api/contacts',
          {
            fields: { given, family: '' },
            points: [{ kind: 'email', label: '', value: `${given}@example.com`, parts: [] }],
          },
        ]),
      ),
    deleted: 'dialog',
  },
];

const COUNT = 40;

/** The titles of the list, the lowest first, with the lowest brought to the foot of the view. */
function lowest(page: Page, titles: string[]): Promise<string[]> {
  return page.evaluate((titles) => {
    const wanted = new Set(titles);
    const found = [...document.querySelectorAll<HTMLElement>('body *')]
      .filter((element) => element.childElementCount === 0 && wanted.has(element.textContent ?? ''))
      .sort((one, other) => other.getBoundingClientRect().top - one.getBoundingClientRect().top);
    found[0].scrollIntoView({ block: 'end' });
    return found.map((element) => element.textContent ?? '');
  }, titles);
}

const gapAbove = (page: Page) =>
  page.evaluate(() => {
    const bar = document.querySelector<HTMLElement>('[data-choice-bar]')!;
    let scroller: HTMLElement | null = bar.parentElement;
    while (scroller && !/auto|scroll/.test(getComputedStyle(scroller).overflowY))
      scroller = scroller.parentElement;
    return Math.round(bar.getBoundingClientRect().top - scroller!.getBoundingClientRect().top);
  });

for (const list of LISTS) {
  test(`${list.name} are chosen the same way as every other list`, async ({ page }) => {
    await page.goto('/');
    const stamp = Date.now();
    const titles = Array.from({ length: COUNT }, (_, at) => `Red${stamp}x${at}`);
    await list.fill(page, titles, stamp);

    for (const width of [1500, 390]) {
      await page.setViewportSize({ width, height: 800 });
      await page.goto(list.url);
      await expect(page.getByText(titles[0], { exact: true }).first()).toBeAttached();
      await page.waitForTimeout(200);
      const [pressed, other] = await lowest(page, titles);
      await page.waitForTimeout(200);
      const row = page.getByText(pressed, { exact: true }).first();
      await row.hover();
      await page.waitForTimeout(200);
      const before = (await row.boundingBox())!.y;

      await page.mouse.down();
      await expect(page.getByText('Odabrano: 1')).toBeVisible();
      await page.mouse.up();
      await expect(page.getByText('Odabrano: 1')).toBeInViewport();
      expect(await gapAbove(page)).toBe(0);
      expect(Math.abs((await row.boundingBox())!.y - before)).toBeLessThanOrEqual(1);

      const second = page.getByText(other, { exact: true }).first();
      await second.click();
      await expect(page.getByText('Odabrano: 2')).toBeVisible();
      await second.click();
      await expect(page.getByText('Odabrano: 1')).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(page.getByText('Odabrano: 1')).toBeHidden();

      await row.click({ button: 'right' });
      await expect(page.getByRole('menu')).toBeVisible();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('menu')).toBeHidden();
    }

    await page.setViewportSize({ width: 1500, height: 800 });
    await page.goto(list.url);
    await expect(page.getByText(titles[0], { exact: true }).first()).toBeAttached();
    const [doomed] = await lowest(page, titles);
    const row = page.getByText(doomed, { exact: true }).first();
    await row.click({ modifiers: ['ControlOrMeta'] });
    await expect(page.getByText('Odabrano: 1')).toBeVisible();
    await page.keyboard.press('Delete');
    if (list.deleted === 'gone') await expect(row).toHaveCount(0);
    else await expect(page.getByRole('alertdialog')).toBeVisible();
  });
}

test('a click opens a row once, and only a preview beside the list keeps the list', async ({
  page,
  context,
}) => {
  await page.goto('/');
  const stamp = Date.now();
  const title = `Otvori ${stamp}`;
  const board = `Ploča ${stamp}`;
  const site = `Stranica ${stamp}`;
  const [place] = await sent<{ id: string }>(page, [['/api/links', {}]]);
  await sent(page, [
    ['/api/nodes', { kind: 'document', title, parent: null }],
    ['/api/nodes', { kind: 'link', title: site, href: 'https://example.com/', parent: place.id }],
  ]);
  await boards(page, [board], `Skupina ${stamp}`);
  await context.route('https://example.com/**', (route) => route.fulfill({ body: 'x' }));

  await page.goto('/documents');
  const row = page.getByRole('row', { name: new RegExp(title) });
  const [tab] = await Promise.all([context.waitForEvent('page'), row.click({ button: 'middle' })]);
  await expect(tab).toHaveURL(/\/d\//);
  await tab.close();
  await expect(page).toHaveURL(/\/documents$/);
  await row.click();
  await expect(page).toHaveURL(/\/d\//);

  await page.goto('/documents');
  await row.click({ modifiers: ['ControlOrMeta'] });
  await expect(page.getByText('Odabrano: 1')).toBeVisible();
  await row.dblclick();
  await expect(page).toHaveURL(/\/d\//);

  await page.goto('/links');
  const pages: Page[] = [];
  context.on('page', (opened) => pages.push(opened));
  const [popup] = await Promise.all([
    context.waitForEvent('page'),
    page.getByText(site, { exact: true }).dblclick(),
  ]);
  await popup.waitForLoadState();
  await page.waitForTimeout(300);
  expect(pages).toHaveLength(1);

  await page.goto('/boards');
  const shown = page.getByRole('row', { name: new RegExp(board) });
  await shown.click();
  await expect(shown).toHaveAttribute('aria-current', 'true');
  await expect(page).toHaveURL(/\/boards$/);
  await shown.dblclick();
  await expect(page).toHaveURL(/\/p\//);
});
