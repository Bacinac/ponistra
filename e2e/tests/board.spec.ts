import { expect, test } from './fixtures';
import { newBoard } from './helpers/nodes';

const TITLE = 'Ploča prodaje e2e';
const PAGE = `<!doctype html><html><head><meta charset="utf-8"></head><body>
<h1 id="probe">…</h1><script>
const tried = {};
for (const [name, reach] of Object.entries({
  cookie: () => document.cookie,
  storage: () => localStorage.length,
  parent: () => parent.document.title,
})) {
  try { reach(); tried[name] = 'reached'; } catch (error) { tried[name] = error.name; }
}
tried.popup = window.open('https://example.com/') === null ? 'none' : 'opened';
fetch('/api/auth/session').then(() => 'reached', (error) => error.name).then((fetched) => {
  tried.fetch = fetched;
  document.getElementById('probe').textContent = JSON.stringify(tried);
});
</script></body></html>`;

test('a board runs its script sandboxed, reaching nothing of the app and going nowhere', async ({
  page,
  problems,
}) => {
  const leaving: string[] = [];
  page.context().on('request', (request) => {
    if (request.url().includes('example.com')) leaving.push(request.url());
  });
  await page.goto('/documents');
  await newBoard(page, TITLE, PAGE);
  await page.reload();
  const row = page.getByRole('row', { name: new RegExp(TITLE) });
  await expect(row).toContainText('Ploča');
  await row.getByText(TITLE, { exact: true }).dblclick();

  const board = page.frameLocator(`iframe[title="${TITLE}"]`).frameLocator('iframe');
  await expect(board.locator('#probe')).toHaveText(
    JSON.stringify({
      cookie: 'SecurityError',
      storage: 'SecurityError',
      parent: 'SecurityError',
      popup: 'none',
      fetch: 'TypeError',
    }),
  );
  const frame = page.frames().find((each) => each.url().includes('/board/page'))!;
  await frame.evaluate(() => {
    location.href = 'https://example.com/';
  });
  await expect.poll(() => problems.some((each) => each.includes('frame-src'))).toBe(true);
  expect(leaving).toEqual([]);
  expect(problems.filter((each) => !/Content Security Policy|sandboxed/.test(each))).toEqual([]);
  problems.length = 0;

  await page.getByRole('button', { name: TITLE }).click();
  await page.getByRole('menuitem', { name: 'Izvorni kod' }).click();
  await expect(page.getByText("tried.popup = window.open('https://example.com/')")).toBeVisible();
});

test('the page of boards shows theirs under their groups, and nothing of them in the documents', async ({
  page,
  problems,
}) => {
  const shows = (name: string) =>
    `<!doctype html><html><body><h1>${name} prikazana</h1></body></html>`;
  await page.goto('/documents');
  await newBoard(page, 'Prva ploča e2e', shows('Prva'), 'Baba e2e');
  await newBoard(page, 'Druga ploča e2e', shows('Druga'), 'Dida e2e');
  await newBoard(page, 'Treća ploča e2e', shows('Treća'), 'Baba e2e');
  await newBoard(page, 'Stranica e2e', shows('Stranica'));

  await page.reload();
  const main = page.getByRole('main');
  await expect(main.getByText('Stranica e2e', { exact: true })).toBeVisible();
  await expect(main.getByText('Ploče', { exact: true })).toHaveCount(0);
  await expect(main.getByText('Prva ploča e2e', { exact: true })).toHaveCount(0);

  await page.getByRole('link', { name: 'Ploče', exact: true }).click();
  await expect(page).toHaveURL(/\/boards$/);
  const shownRows = main.getByRole('row');
  await expect(main.getByText('Stranica e2e', { exact: true })).toHaveCount(0);
  await expect(main.getByRole('heading', { level: 2 })).toHaveText(['Baba e2e', 'Dida e2e']);
  const order = (await shownRows.allInnerTexts()).join(' | ');
  expect(order.indexOf('Baba e2e')).toBeLessThan(order.indexOf('Prva ploča e2e'));
  expect(order.indexOf('Treća ploča e2e')).toBeLessThan(order.indexOf('Dida e2e'));
  expect(order.indexOf('Dida e2e')).toBeLessThan(order.indexOf('Druga ploča e2e'));

  const panel = page.getByRole('complementary', { name: 'Pregled' });
  const shown = (name: string) =>
    panel.frameLocator(`iframe[title="${name}"]`).frameLocator('iframe').locator('h1');
  await expect(panel.locator('iframe')).toHaveCount(1);
  for (const name of ['Prva', 'Druga']) {
    const title = `${name} ploča e2e`;
    await page
      .getByRole('row', { name: new RegExp(title) })
      .getByText(title, { exact: true })
      .click();
    await expect(shown(title)).toHaveText(`${name} prikazana`);
  }

  await main.getByRole('heading', { name: 'Dida e2e' }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Preimenuj' }).click();
  const named = page.getByRole('dialog', { name: 'Preimenuj' });
  await named.getByRole('textbox').fill('Opus e2e');
  await named.getByRole('button', { name: 'Spremi' }).click();
  await expect(main.getByRole('heading', { name: 'Opus e2e' })).toBeVisible();
  await expect(main.getByRole('heading', { name: 'Dida e2e' })).toHaveCount(0);

  await page.goto('/documents');
  const row = page.getByRole('row', { name: /Stranica e2e/ });
  await row.getByText('Stranica e2e', { exact: true }).click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Grupa na Pločama…' }).click();
  const grouped = page.getByRole('dialog', { name: 'Grupa na Pločama…' });
  await grouped.getByRole('textbox').fill('baba E2E');
  await grouped.getByRole('button', { name: 'Premjesti' }).click();
  await expect(row).toHaveCount(0);

  await page.getByRole('link', { name: 'Ploče', exact: true }).click();
  await expect(page.getByRole('row', { name: /Stranica e2e/ })).toBeVisible();
  await expect(main.getByRole('heading', { level: 2 })).toHaveText(['Baba e2e', 'Opus e2e']);
  expect(problems.filter((each) => !/Content Security Policy|sandboxed/.test(each))).toEqual([]);
  problems.length = 0;
});

const KEEPING = `<!doctype html><html><body>
<script src="/api/boards/runtime.js"></script>
<ul id="rows"></ul><p id="failed"></p><p id="can"></p>
<button id="add">Dodaj</button>
<script>
window.ponistra.db.canWrite().then((can) => {
  document.getElementById('can').textContent = can;
});
const steps = window.ponistra.db.collection('koraci');
steps.onSnapshot((rows) => {
  document.getElementById('rows').textContent = rows.docs
    .map((row) => row.id + '=' + row.data().n)
    .join(',');
});
document.getElementById('add').onclick = () =>
  steps.doc('a').set({ n: 1 }).catch((error) => {
    document.getElementById('failed').textContent = error.code;
  });
</script></body></html>`;

test('a board keeps its data, hears it change and reads it through a link without an account', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const title = 'Ploča s bazom e2e';
  await page.goto('/documents');
  await newBoard(page, title, KEEPING);
  await page.reload();
  await page
    .getByRole('row', { name: new RegExp(title) })
    .getByText(title, { exact: true })
    .dblclick();

  const board = page.frameLocator(`iframe[title="${title}"]`).frameLocator('iframe');
  await expect(board.locator('#can')).toHaveText('true');
  await board.locator('#add').click();
  await expect(board.locator('#rows')).toHaveText('a=1');
  const held = await page.locator(`iframe[title="${title}"]`).getAttribute('src');
  const id = held!.match(/\/api\/nodes\/([^/]+)\/board/)![1]!;
  const written = await page.evaluate(async (id) => {
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const sent = await fetch(`/api/nodes/${id}/board/data?collection=koraci&key=b`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ data: { n: 2 } }),
    });
    return sent.status;
  }, id);
  expect(written).toBe(200);
  await expect(board.locator('#rows')).toHaveText('a=1,b=2');

  await page.getByRole('button', { name: 'Dijeli' }).click();
  const panel = page.getByRole('complementary', { name: 'Pristup' });
  await panel.getByRole('button', { name: 'Izradi poveznicu' }).click();
  await panel.getByLabel('Lozinka').fill('tajna-rijec');
  await panel.getByRole('button', { name: 'Izradi poveznicu' }).click();
  const shown = panel.getByText(/\/o\//);
  await expect(shown).toBeVisible();
  const url = (await shown.textContent())!;

  const stranger = await browser.newContext({ baseURL });
  const outside = await stranger.newPage();
  await outside.goto(new URL(url).pathname);
  await expect(outside.getByText(title)).toBeHidden();
  await outside.getByLabel('Lozinka').fill('kriva');
  await outside.getByRole('button', { name: 'Otvori' }).click();
  await expect(outside.getByText('Lozinka nije točna.')).toBeVisible();
  await outside.getByLabel('Lozinka').fill('tajna-rijec');
  await outside.getByRole('button', { name: 'Otvori' }).click();
  const seen = outside.frameLocator(`iframe[title="${title}"]`).frameLocator('iframe');
  await expect(seen.locator('#rows')).toHaveText('a=1,b=2');
  await expect(seen.locator('#can')).toHaveText('false');
  await seen.locator('#add').click();
  await expect(seen.locator('#failed')).toHaveText('read_only');

  await panel.getByRole('button', { name: 'Ukini poveznicu' }).click();
  await expect(shown).toBeHidden();
  await outside.reload();
  await expect(outside.getByText('Ova poveznica više ne vrijedi.')).toBeVisible();
  await stranger.close();
  expect(problems.filter((each) => !/Content Security Policy|sandboxed|40[34]/.test(each))).toEqual(
    [],
  );
  problems.length = 0;
});
