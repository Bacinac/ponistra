import AxeBuilder from '@axe-core/playwright';
import type { Browser, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { idIn, newBoard, newDocument } from './helpers/nodes';

const WCAG = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

/** What axe finds against WCAG 2.2 AA on the page as it stands, in both schemes: one line per
 * rule and element, with its impact and the element's opening tag. A page that holds a
 * connection open (`live`) is never idle on the network, so it is taken as soon as it loads. */
async function violations(page: Page, { live = false } = {}): Promise<string[]> {
  const found: string[] = [];
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme });
    await page.waitForLoadState(live ? 'load' : 'networkidle');
    const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze();
    for (const { id, impact, nodes } of violations) {
      for (const { html } of nodes) {
        found.push(`${colorScheme} ${id} (${impact}): ${html.slice(0, html.indexOf('>') + 1)}`);
      }
    }
  }
  return found;
}

const PAGES = [
  '/',
  '/documents',
  '/notes',
  '/links',
  '/start',
  '/boards',
  '/favourites',
  '/shared',
  '/share',
  '/trash',
  '/search',
  '/help',
  '/tasks',
  '/mail',
  '/contacts',
  '/chat',
  '/calendar',
  '/vault',
  '/settings',
];

const ADMINISTRATORS = [
  '/company',
  '/users',
  '/resources',
  '/workdays',
  '/meetings',
  '/ai',
  '/providers',
  '/applications',
  '/retention',
  '/journal',
  '/health',
];

for (const address of PAGES) {
  test(`${address} meets WCAG 2.2 AA`, async ({ page }) => {
    await page.goto(address);
    await expect(page.getByRole('main')).toBeVisible();
    expect(await violations(page)).toEqual([]);
  });
}

test.describe('as an administrator', () => {
  test.use({ administrator: true });

  for (const address of ADMINISTRATORS) {
    test(`${address} meets WCAG 2.2 AA`, async ({ page }) => {
      await page.goto(address);
      await expect(page.getByRole('main')).toBeVisible();
      expect(await violations(page)).toEqual([]);
    });
  }
});

/** What the page's own session posts, the answer read as JSON. */
async function posted<T>(page: Page, path: string, data: object): Promise<T> {
  return page.evaluate(
    async ({ path, data }) => {
      const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
      const sent = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify(data),
      });
      if (!sent.ok) throw new Error(`POST ${path}: ${sent.status}`);
      return sent.json();
    },
    { path, data },
  );
}

/** A browser of someone who is not signed in. */
async function stranger(browser: Browser, baseURL: string): Promise<Page> {
  const context = await browser.newContext({
    baseURL,
    locale: 'hr-HR',
    permissions: ['camera', 'microphone'],
  });
  return context.newPage();
}

test('the open account menu meets WCAG 2.2 AA', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: /^Račun / }).click();
  await expect(page.getByRole('menu')).toBeVisible();
  expect(await violations(page)).toEqual([]);
});

test('the tree of folders within folders meets WCAG 2.2 AA, open and closed', async ({ page }) => {
  await page.goto('/');
  const title = `Mapa ${Date.now()}`;
  await page.evaluate(async (title) => {
    await fetch('/api/auth/session');
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const made = async (title: string, parent: string | null) => {
      const response = await fetch('/api/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify({ kind: 'folder', title, parent }),
      });
      if (!response.ok) throw new Error(`POST /api/nodes: ${response.status}`);
      return ((await response.json()) as { id: string }).id;
    };
    await made('Podmapa', await made(title, null));
  }, title);
  await page.goto('/documents');
  const row = page.getByRole('link', { name: title }).locator('..');
  const expand = row.getByRole('button', { name: 'Proširi' });
  await expect(expand).toBeVisible();
  expect(await violations(page)).toEqual([]);
  await expand.click();
  await expect(row.getByRole('button', { name: 'Sažmi' })).toBeVisible();
  expect(await violations(page)).toEqual([]);
});

test('the search box offering commands meets WCAG 2.2 AA', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('combobox', { name: 'Pretraži' }).fill('tema');
  await expect(page.getByRole('listbox')).toBeVisible();
  expect(await violations(page)).toEqual([]);
});

test('a document meets WCAG 2.2 AA', async ({ page }) => {
  await page.goto(await newDocument(page, 'Pristupačnost'));
  await page.locator('.ProseMirror').click();
  await page.keyboard.type('# Naslov');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Odlomak teksta.');
  expect(await violations(page)).toEqual([]);
});

test('a document’s menu and its dialog of theme and styles meet WCAG 2.2 AA', async ({ page }) => {
  await page.goto(await newDocument(page, 'Stilovi'));
  await page.locator('header button[aria-current="page"]').click();
  await expect(page.getByRole('menu')).toBeVisible();
  expect(await violations(page)).toEqual([]);
  await page.getByRole('menuitem', { name: 'Tema i stilovi…' }).click();
  await expect(page.getByRole('dialog', { name: 'Tema i stilovi' })).toBeVisible();
  expect(await violations(page)).toEqual([]);
});

test('a show and its presenter’s window meet WCAG 2.2 AA', async ({ page }) => {
  await page.goto(await newDocument(page, 'Izlaganje'));
  await page.locator('.ProseMirror').click();
  await page.keyboard.type('# Uvod');
  await page.keyboard.press('Enter');
  await page.keyboard.type('# Cijene');
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Izlaži od početka' }).click();
  const show = page.getByRole('dialog', { name: 'Izlaganje' });
  await expect(show.getByText('Uvod')).toBeInViewport();
  expect(await violations(page)).toEqual([]);
  const opened = page.waitForEvent('popup');
  await show.getByRole('button', { name: 'Izlagački prikaz' }).click();
  const presenter = await opened;
  await expect(
    presenter.getByRole('region', { name: 'Sljedeći slajd' }).getByText('Cijene'),
  ).toBeVisible();
  expect(await violations(presenter)).toEqual([]);
});

test('the Projects page meets WCAG 2.2 AA, in the app and beside it', async ({ page }) => {
  // The routes of the context reach the window beside the app as well.
  const context = page.context();
  await context.route('**/api/workspace/projects', (route) =>
    route.fulfill({
      json: {
        projects: [
          {
            name: null,
            path: '/work',
            gate: null,
            plan: null,
            chats: [],
            rounds: [],
            aside: false,
          },
          {
            name: 'dida',
            path: '/work/dida',
            gate: null,
            plan: null,
            chats: [],
            rounds: [],
            aside: true,
          },
          {
            name: 'ponistra',
            path: '/work/ponistra',
            gate: null,
            plan: null,
            rounds: [],
            aside: false,
            chats: [
              {
                id: 'c1',
                title: 'Pristupačnost',
                at: new Date().toISOString(),
                open: false,
                state: 'closed',
                waitingFor: null,
                context: null,
                changes: null,
                coordinator: null,
              },
            ],
          },
        ],
        restart: null,
        usage: {
          at: new Date().toISOString(),
          windows: [
            { kind: 'week', name: null, percent: 61, resets: new Date().toISOString() },
            { kind: 'model', name: 'Fable', percent: 4, resets: new Date().toISOString() },
          ],
          credits: null,
          error: null,
        },
        host: {
          at: new Date().toISOString(),
          load: 2.4,
          cpus: 12,
          memory: { total: 64e9, available: 16e9 },
          swap: { total: 8e9, free: 7e9 },
          disk: { total: 800e9, free: 40e9 },
          error: null,
        },
      },
    }),
  );
  await context.route('**/api/workspace/commands', (route) =>
    route.fulfill({ json: { commands: [] } }),
  );
  await context.route('**/api/memory/waiting', (route) => route.fulfill({ json: { count: 0 } }));
  // The rail offers Projects only to the workspace's owner, which the test's account is not.
  await context.route('**/api/auth/session', async (route) => {
    const response = await route.fetch();
    const session = await response.json();
    const user = session.user && { ...session.user, workspace: { url: '/code/', here: false } };
    await route.fulfill({ response, json: { ...session, user } });
  });
  await page.goto('/workspace');
  const project = page.getByRole('region', { name: 'ponistra' });
  await expect(project).toBeVisible();
  await page.getByRole('button', { name: /Ostali/ }).click();
  await expect(page.getByRole('region', { name: 'Dida' })).toBeVisible();
  expect(await violations(page)).toEqual([]);
  await project.getByRole('heading').click({ button: 'right' });
  await expect(page.getByRole('menuitem', { name: 'Premjesti u Ostale' })).toBeVisible();
  expect(await violations(page)).toEqual([]);
  await page.keyboard.press('Escape');
  const opened = page.waitForEvent('popup');
  await page.getByRole('navigation').getByRole('link', { name: 'Projekti' }).click();
  const beside = await opened;
  await expect(beside).toHaveURL(/\/workspace\/beside$/);
  await expect(beside.getByRole('region', { name: 'ponistra' })).toBeVisible();
  await expect(beside.getByRole('meter', { name: 'Fable' })).toBeVisible();
  await expect(beside.getByRole('region', { name: 'Radni prostor' })).toContainText('95 %');
  expect(await violations(beside)).toEqual([]);
});

test('a link for someone outside meets WCAG 2.2 AA, locked and open', async ({
  page,
  browser,
  baseURL,
}) => {
  await page.goto('/');
  const id = await newBoard(
    page,
    'Za vanjske',
    '<!doctype html><html lang="hr"><head><title>Za vanjske</title></head><body><main><h1>Za vanjske</h1></main></body></html>',
  );
  const { url } = await posted<{ url: string }>(page, `/api/nodes/${id}/outside-links`, {
    expires_on: null,
    password: 'tajna-rijec',
  });
  const outside = await stranger(browser, baseURL!);
  await outside.goto(new URL(url).pathname);
  await expect(outside.getByLabel('Lozinka')).toBeVisible();
  expect(await violations(outside)).toEqual([]);
  await outside.getByLabel('Lozinka').fill('tajna-rijec');
  await outside.getByRole('button', { name: 'Otvori' }).click();
  await expect(
    outside.frameLocator('iframe[title="Za vanjske"]').frameLocator('iframe').getByRole('heading'),
  ).toHaveText('Za vanjske');
  expect(await violations(outside, { live: true })).toEqual([]);
  await outside.context().close();
});

test('a document through a link for someone outside meets WCAG 2.2 AA', async ({
  page,
  browser,
  baseURL,
}) => {
  const address = await newDocument(page, 'Dokument za vanjske');
  await page.goto(address);
  await page.locator('.ProseMirror').click();
  await page.keyboard.type('Tekst za vanjske.');
  const id = idIn(address.split('/')[2]);
  const { url } = await posted<{ url: string }>(page, `/api/nodes/${id}/outside-links`, {
    expires_on: null,
  });
  const outside = await stranger(browser, baseURL!);
  await outside.goto(new URL(url).pathname);
  await expect(outside.getByText('Tekst za vanjske.')).toBeVisible();
  expect(await violations(outside, { live: true })).toEqual([]);
  await outside.context().close();
});

test('the door of a meeting for a guest meets WCAG 2.2 AA', async ({ page, browser, baseURL }) => {
  await page.goto('/');
  const { id } = await posted<{ id: string }>(page, '/api/meetings', { title: 'Pristupačnost' });
  const guest = await stranger(browser, baseURL!);
  await guest.goto(`/meet/${id}`);
  await expect(guest.getByLabel('Vaše ime')).toBeVisible();
  expect(await violations(guest)).toEqual([]);
  await guest.context().close();
});

test('the sign-in page meets WCAG 2.2 AA', async ({ browser, baseURL }) => {
  const outside = await browser.newContext({ baseURL, locale: 'hr-HR' });
  const page = await outside.newPage();
  await page.goto('/');
  await expect(page.getByLabel('Lozinka')).toBeVisible();
  expect(await violations(page)).toEqual([]);
  await page.evaluate(() => localStorage.setItem('ponistra.signIn', 'passkey'));
  await page.reload();
  await expect(page.getByRole('button', { name: 'Prijavi se pristupnim ključem' })).toBeVisible();
  await expect(page.getByLabel('E-pošta')).toHaveCount(0);
  expect(await violations(page)).toEqual([]);
  await outside.close();
});
