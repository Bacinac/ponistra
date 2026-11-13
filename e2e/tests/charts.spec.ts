import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';
import { cellAt, cellTexts, insertTable, tab, tableCommand } from './helpers/tables';

test("a chart is drawn over a table's cells, edited and follows its rows", async ({ page }) => {
  await page.goto(await newDocument(page, 'Grafikon'));
  await page.locator('.ProseMirror').first().click();
  await insertTable(page, '3 × 4');
  const table = page.locator('.ponistra-table');
  const typed = ['', 'Prihod', 'Rashod', 'Sij', '10', '4', 'Velj', '20', '6', 'Ožu', '15', '8'];
  for (const [index, text] of typed.entries()) {
    if (text) await page.keyboard.type(text);
    const next = index + 1;
    if (next < typed.length) await tab(page, `${'ABC'[next % 3]}${Math.floor(next / 3) + 1}`);
  }
  await expect.poll(() => cellTexts(table)).toEqual(typed);

  await tableCommand(page, 'Grafikon iz tablice');
  const chart = page.locator('figure.ponistra-chart');
  await expect(chart).toHaveAttribute('aria-label', 'Stupčasti');
  const texts = chart.locator('svg text');
  await expect(texts.filter({ hasText: 'Prihod' })).toHaveCount(1);
  await expect(texts.filter({ hasText: 'Velj' })).toHaveCount(1);
  await expect(chart.locator('svg path[fill]')).not.toHaveCount(0);

  await chart.dblclick();
  const edit = page.getByRole('dialog', { name: 'Uređivanje grafikona' });
  await expect(edit.getByLabel('Raspon')).toHaveValue('A1:C4');
  await edit.getByLabel('Raspon').fill('A1:C9');
  await expect(edit.getByRole('button', { name: 'Spremi' })).toBeDisabled();
  await edit.getByLabel('Raspon').fill('A1:C4');
  await edit.getByLabel('Naslov').fill('Prvi kvartal');
  await edit.getByRole('button', { name: 'Spremi' }).click();
  await expect(chart).toHaveAttribute('aria-label', 'Prvi kvartal');
  await expect(texts.filter({ hasText: 'Prvi kvartal' })).toHaveCount(1);

  await chart.dblclick();
  await expect(edit.getByLabel('Naslov')).toHaveValue('Prvi kvartal');
  await edit.getByRole('button', { name: 'Kružni' }).click();
  await edit.getByRole('button', { name: 'Spremi' }).click();
  await expect(chart).toHaveAttribute('data-chart', 'pie');
  await expect(texts.filter({ hasText: 'Rashod' })).toHaveCount(0);

  await cellAt(table, 'A3').click();
  await tableCommand(page, 'Obriši redak');
  await expect(table.getByRole('grid')).toHaveAttribute('aria-rowcount', '4');
  await expect(texts.filter({ hasText: 'Velj' })).toHaveCount(0);
  await expect(texts.filter({ hasText: 'Ožu' })).not.toHaveCount(0);

  await page.reload();
  await expect(chart).toHaveAttribute('data-chart', 'pie');
  await expect(texts.filter({ hasText: 'Ožu' })).not.toHaveCount(0);

  await cellAt(table, 'A1').click();
  await tableCommand(page, 'Obriši tablicu');
  await expect(chart.locator('.ponistra-chart-note')).toHaveText(
    'Tablica ili ćelije koje ovaj grafikon prikazuje više ne postoje.',
  );
});
