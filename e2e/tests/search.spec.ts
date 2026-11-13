import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';
import { cellAt, insertTable, tab, writing } from './helpers/tables';

test('a search hit in the text opens its tab at the block', async ({ page }) => {
  await page.goto(await newDocument(page, 'Probna pretraga'));
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('# Troškovi');
  await page.keyboard.press('Enter');
  for (let line = 1; line <= 40; line++) {
    await page.keyboard.type(`Redak ${line}`);
    await page.keyboard.press('Enter');
  }
  await page.keyboard.type('Dostava kamionom na gradilište');

  await expect
    .poll(
      async () => {
        const response = await page.request.get('/api/search?q=kamionom');
        return (await response.json()).documents.length;
      },
      { timeout: 20_000 },
    )
    .toBe(1);

  await page.goto('/');
  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await search.fill('kamionom');
  const hit = page.getByRole('option', { name: /Probna pretraga/ });
  await expect(hit).toContainText('Odjeljak 1 · Odlomak 41');
  await hit.click();
  const found = page.locator('.ProseMirror .ponistra-found');
  await expect(found).toHaveText('Dostava kamionom na gradilište');
  await expect(found).toBeInViewport();
  await expect(page.locator('.ponistra-found')).toHaveCount(0);
});

test('a search hit in a cell opens its table at the cell, chosen', async ({ page }) => {
  await page.goto(await newDocument(page, 'Pretraga u tablici'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  for (let line = 1; line <= 40; line++) {
    await page.keyboard.type(`Redak ${line}`);
    await page.keyboard.press('Enter');
  }
  await insertTable(page, '3 × 3');
  const table = page.locator('.ponistra-table');
  for (const address of ['B1', 'C1', 'A2', 'B2', 'C2', 'A3', 'B3', 'C3']) {
    await tab(page, address);
  }
  await expect(writing(table, 'C3')).toBeFocused();
  await page.keyboard.type('Dizalica');
  await page.keyboard.press('ArrowUp');
  await expect(cellAt(table, 'C3')).toHaveText('Dizalica');

  await expect
    .poll(
      async () => {
        const response = await page.request.get('/api/search?q=dizalica');
        const { documents } = await response.json();
        return documents
          .filter((result: { title: string }) => result.title === 'Pretraga u tablici')
          .map((result: { address: object }) => result.address);
      },
      { timeout: 20_000 },
    )
    .toEqual([{ table: 1, cell: 'C3' }]);

  await page.goto('/');
  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await search.fill('dizalica');
  const hit = page.getByRole('option', { name: /Pretraga u tablici/ });
  await expect(hit).toContainText('Tablica 1 · Ćelija C3');
  await hit.click();
  await expect(page).toHaveURL(/[?&]cell=C3/);
  const cell = cellAt(page.locator('.ponistra-table'), 'C3');
  await expect(cell).toHaveAttribute('aria-selected', 'true');
  await expect(cell).toBeInViewport();
});

test('versions of a document are searched when asked for by kind, and a hit opens the version', async ({
  page,
}) => {
  const stamp = String(Date.now());
  await page.goto('/');
  await page.evaluate(async (stamp) => {
    await fetch('/api/auth/session');
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const post = async (url: string, body: unknown) => {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(`POST ${url}: ${response.status}`);
      return response.json();
    };
    const node = await post('/api/nodes', { kind: 'document', title: `Ugovor ${stamp}` });
    await post(`/api/nodes/${node.id}/versions`, { title: `Prije popusta ${stamp}` });
  }, stamp);

  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await search.fill(`ugovor ${stamp}`);
  await expect(page.getByRole('option', { name: new RegExp(`Ugovor ${stamp}`) })).toBeVisible();
  const version = page.getByRole('option', { name: new RegExp(`Prije popusta ${stamp}`) });
  await search.fill(`popusta ${stamp}`);
  await expect(version).toBeHidden();
  await search.fill(`vrsta:verzija popusta ${stamp}`);
  await expect(version).toContainText(`Ugovor ${stamp} · Verzija 1`);
  await version.click();
  await expect(page).toHaveURL(/\/d\/.+\/versions\/[0-9A-Za-z]+$/);
  await expect(page.getByText(`Prije popusta ${stamp}`).first()).toBeVisible();
});
