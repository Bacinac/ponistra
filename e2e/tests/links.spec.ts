import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function created(page: Page, item: string, fields: Record<string, string>) {
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: item }).click();
  const dialog = page.getByRole('dialog', { name: item });
  for (const [label, value] of Object.entries(fields)) {
    await dialog.getByLabel(label, { exact: true }).fill(value);
  }
  await dialog.getByRole('button', { name: 'Izradi' }).click();
  await expect(dialog).toBeHidden();
}

test('a link is kept in a folder, opens its page in a tab of its own, is edited and found', async ({
  page,
  context,
}) => {
  const stamp = Date.now();
  await context.route('https://stranica.example/**', (route) =>
    route.fulfill({ contentType: 'text/html', body: '<title>Stranica</title>' }),
  );
  await page.goto('/documents');
  await created(page, 'Nova mapa', { Naziv: `Oznake ${stamp}` });
  await page
    .getByRole('row', { name: new RegExp(`Oznake ${stamp}`) })
    .getByText(`Oznake ${stamp}`, { exact: true })
    .dblclick();
  await expect(page.getByText('Ova mapa je prazna.')).toBeVisible();

  await created(page, 'Nova poveznica', { Adresa: `stranica.example/katalog-${stamp}` });
  const row = page.getByRole('row', { name: /stranica\.example/ });
  await expect(row).toContainText('Poveznica');

  const [tab] = await Promise.all([
    page.waitForEvent('popup'),
    row.getByText('stranica.example', { exact: true }).dblclick(),
  ]);
  await expect(tab).toHaveURL(`https://stranica.example/katalog-${stamp}`);
  await tab.close();
  await expect(page).toHaveURL(/\/f\/oznake-/);

  await row.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Uredi poveznicu' }).click();
  const dialog = page.getByRole('dialog', { name: 'Uredi poveznicu' });
  await expect(dialog.getByLabel('Adresa', { exact: true })).toHaveValue(
    `https://stranica.example/katalog-${stamp}`,
  );
  await dialog
    .getByLabel('Adresa', { exact: true })
    .fill(`https://stranica.example/radno-${stamp}`);
  await dialog.getByLabel('Naziv', { exact: true }).fill(`Knjižnica ${stamp}`);
  await dialog.getByRole('button', { name: 'Spremi' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('row', { name: new RegExp(`Knjižnica ${stamp}`) })).toBeVisible();

  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await search.fill(`Knjižnica ${stamp}`);
  const found = page.getByRole('option', { name: new RegExp(`Knjižnica ${stamp}`) });
  const [again] = await Promise.all([page.waitForEvent('popup'), found.click()]);
  await expect(again).toHaveURL(`https://stranica.example/radno-${stamp}`);
  await again.close();
});

const SERVICES = (stamp: number) => `- Nadzor ${stamp}:
    - Grafana:
        href: https://grafana.example/${stamp}
        description: Grafikoni
        widget:
          type: grafana
          password: tajna
`;

test('the page of links keeps its own groups, outside the documents, and loads a Homepage dashboard', async ({
  page,
  context,
}) => {
  const stamp = Date.now();
  await context.route('https://*.example/**', (route) =>
    route.fulfill({ contentType: 'text/html', body: '<title>Stranica</title>' }),
  );
  await page.goto('/documents');
  await page.getByRole('link', { name: 'Poveznice', exact: true }).click();
  await expect(page).toHaveURL(/\/links$/);
  await expect(page.getByRole('heading', { name: 'Poveznice', level: 1 })).toBeVisible();

  await created(page, 'Nova grupa', { Naziv: `Grupa ${stamp}` });
  const group = page.getByRole('region', { name: `Grupa ${stamp}` });
  const heading = group.getByRole('heading', { name: `Grupa ${stamp}` });
  await heading.hover();
  await page.mouse.down();
  const adds = page.getByRole('menuitem', { name: 'Nova poveznica' });
  await expect(adds).toBeVisible();
  await page.mouse.up();
  await expect(page.getByRole('menuitem', { name: 'Stupci' })).toBeVisible();
  await adds.click();
  for (const name of ['Prvo', 'Drugo']) {
    const adding = page.getByRole('dialog', { name: 'Nova poveznica' });
    await adding.getByLabel('Adresa', { exact: true }).fill(`stranica.example/${name}-${stamp}`);
    await adding.getByLabel('Naziv', { exact: true }).fill(`${name} ${stamp}`);
    await adding.getByRole('button', { name: 'Izradi' }).click();
    await expect(group.getByRole('link', { name: new RegExp(`${name} ${stamp}`) })).toBeVisible();
    if (name === 'Prvo') {
      await heading.click({ button: 'right' });
      await adds.click();
    }
  }
  const first = group.getByRole('link', { name: new RegExp(`Prvo ${stamp}`) });
  const second = group.getByRole('link', { name: new RegExp(`Drugo ${stamp}`) });
  const [fromTile] = await Promise.all([page.waitForEvent('popup'), first.click()]);
  await expect(fromTile).toHaveURL(`https://stranica.example/Prvo-${stamp}`);
  await fromTile.close();
  await expect(group.getByRole('link')).toHaveText([/Prvo/, /Drugo/]);

  await second.dragTo(first, { targetPosition: { x: 4, y: 4 } });
  await expect(group.getByRole('link')).toHaveText([/Drugo/, /Prvo/]);
  await page.reload();
  await expect(group.getByRole('link')).toHaveText([/Drugo/, /Prvo/]);

  await heading.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Stupci' }).click();
  await page.getByRole('menuitemcheckbox', { name: '3', exact: true }).click();
  await expect
    .poll(() =>
      group
        .getByRole('list')
        .evaluate((list) => getComputedStyle(list).gridTemplateColumns.split(' ').length),
    )
    .toBe(3);

  await first.hover();
  await page.mouse.down();
  await expect(page.getByText('Odabrano: 1')).toBeVisible();
  await page.mouse.up();
  await page.getByRole('button', { name: 'Premjesti u grupu' }).click();
  await page.getByRole('menuitem', { name: 'Bez grupe' }).click();
  await expect(
    page
      .getByRole('region', { name: 'Bez grupe' })
      .getByRole('link', { name: new RegExp(`Prvo ${stamp}`) }),
  ).toBeVisible();
  await expect(first).toBeHidden();

  await page.getByRole('button', { name: 'Novo' }).click();
  const [chooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.getByRole('menuitem', { name: 'Učitaj poveznice…' }).click(),
  ]);
  await chooser.setFiles({
    name: 'services.yaml',
    mimeType: 'text/yaml',
    buffer: Buffer.from(SERVICES(stamp)),
  });
  const loaded = page.getByRole('region', { name: `Nadzor ${stamp}` });
  await expect(loaded.getByRole('link', { name: /Grafana/ })).toContainText('Grafikoni', {
    timeout: 30_000,
  });

  await page.goto('/documents');
  await expect(
    page.getByRole('columnheader', { name: /Naziv/ }).or(page.getByText('Ova mapa je prazna.')),
  ).toBeVisible();
  const listed = page.getByRole('row', { name: new RegExp(`Poveznice.*Mapa|${stamp}`) });
  await expect(listed).toHaveCount(0);
});
