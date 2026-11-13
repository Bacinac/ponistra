import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';

test('a task is a note: made on Today, seen on its day, done in the one list, and started from a line of a document', async ({
  page,
}) => {
  const stamp = Date.now().toString(36);
  const text = `Nazvati Anu ${stamp}`;
  await page.goto('/');
  const tile = page.getByRole('region', { name: 'Zadaci na redu' });
  await tile.getByRole('button', { name: 'Novi zadatak' }).click();
  const made = page.getByRole('dialog', { name: 'Novi zadatak' });
  await made.getByLabel('Što').fill(text);
  await expect(made.getByLabel('Rok')).not.toHaveValue('');
  await made.getByRole('button', { name: 'Izradi' }).click();
  await expect(made).toBeHidden();
  await expect(tile.getByRole('button', { name: text })).toBeVisible();

  await page
    .getByRole('navigation', { name: 'Moduli' })
    .getByRole('link', { name: 'Kalendar' })
    .click();
  const views = page.getByRole('group', { name: 'Prikaz' });
  await views.getByRole('button', { name: 'Dan', exact: true }).click();
  await page.getByRole('button', { name: text }).click();
  const edited = page.getByRole('dialog', { name: 'Uredi zadatak' });
  await edited.getByLabel('Što').fill(`${text}, poslijepodne`);
  await edited.getByRole('button', { name: 'Spremi' }).click();
  await expect(edited).toBeHidden();
  await expect(page.getByRole('button', { name: `${text}, poslijepodne` })).toBeVisible();

  await page.goto('/tasks');
  const today = page.getByRole('region', { name: 'Danas' });
  await today.getByRole('checkbox', { name: `Dovršeno: ${text}, poslijepodne` }).click();
  const done = page.getByRole('region', { name: 'Dovršeni' });
  await expect(done.getByRole('button', { name: `${text}, poslijepodne` })).toBeVisible();

  const title = `Zapisnik ${stamp}`;
  await page.goto(await newDocument(page, title));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Poslati ponudu do petka.');
  await editor.getByText('ponudu').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Zadatak iz retka' }).click();
  const lined = page.getByRole('dialog', { name: 'Novi zadatak' });
  await expect(lined.getByLabel('Što')).toHaveValue('Poslati ponudu do petka.');
  await expect(lined.getByText('Iz dokumenta')).toBeVisible();
  await lined.getByRole('button', { name: 'Izradi' }).click();
  await expect(lined).toBeHidden();

  await page.goto('/tasks');
  const undated = page.getByRole('region', { name: 'Bez roka' });
  await undated.getByRole('button', { name: /Poslati ponudu do petka\./ }).click();
  const fromLine = page.getByRole('dialog', { name: 'Uredi zadatak' });
  await fromLine.getByRole('link', { name: title }).click();
  await expect(page).toHaveURL(/\/d\//);
  await expect(page.locator('.ProseMirror').first()).toContainText('Poslati ponudu do petka.');

  await page.goto('/tasks');
  for (const name of [`${text}, poslijepodne`, /Poslati ponudu do petka\./] as const) {
    await page.getByRole('button', { name }).click();
    const dialog = page.getByRole('dialog', { name: 'Uredi zadatak' });
    await dialog.getByRole('button', { name: 'Obriši' }).click();
    await expect(dialog).toBeHidden();
  }
  await expect(page.getByRole('button', { name: /Nazvati Anu|Poslati ponudu/ })).toHaveCount(0);
});
