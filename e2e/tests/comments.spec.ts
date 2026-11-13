import { expect, test } from './fixtures';
import { selectBack } from './helpers/editor';
import { newDocument } from './helpers/nodes';

test('a comment is a thread on selected words, live for everyone who has the document open', async ({
  page,
  context,
}) => {
  const selectThirtyDays = async () => {
    await page.keyboard.press('End');
    for (const _ of ' od primitka računa.') await page.keyboard.press('ArrowLeft');
    await selectBack(page, '30 dana');
  };
  const address = await newDocument(page, 'Probni komentari');
  await page.goto(address);
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Rok plaćanja je 30 dana od primitka računa.');

  const other = await context.newPage();
  await other.goto(address);
  await expect(other.locator('.ProseMirror').first()).toContainText('primitka računa');

  await page.bringToFront();
  await editor.click();
  await selectThirtyDays();
  await page.keyboard.press('Control+Alt+m');
  const panel = page.getByRole('complementary', { name: 'Komentari' });
  const field = panel.getByRole('textbox', { name: 'Napišite komentar' });
  await expect(field).toBeFocused();
  await expect(panel.getByRole('region', { name: 'Novi komentar' })).toContainText('30 dana');
  await page.keyboard.type('Može li rok biti 45 dana uz jamstvo?');
  await page.keyboard.press('Control+Enter');
  const thread = panel.getByRole('article', { name: '30 dana' });
  await expect(thread).toContainText('Može li rok biti 45 dana uz jamstvo?');
  await expect(thread).toHaveAttribute('aria-current', 'true');
  await expect(page).toHaveURL(/\?panel=comments&comment=/);
  await expect(editor.locator('.ponistra-comment')).toHaveText('30 dana');

  const marked = other.locator('.ProseMirror .ponistra-comment');
  await expect(marked).toHaveText('30 dana');
  await expect(other.getByRole('button', { name: 'Komentari 1' })).toBeVisible();
  await other.bringToFront();
  await marked.click();
  const theirs = other.getByRole('complementary', { name: 'Komentari' });
  const reply = theirs.getByRole('textbox', { name: 'Napišite odgovor' });
  await reply.fill('Može, uz bankovno jamstvo.');
  await theirs.getByRole('button', { name: 'Odgovori' }).click();
  await expect(thread.getByRole('listitem')).toHaveText([
    /Može li rok biti 45 dana uz jamstvo\?$/,
    /Može, uz bankovno jamstvo\.$/,
  ]);

  await page.bringToFront();
  await thread.getByRole('listitem').first().getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Uredi' }).click();
  const edited = thread.getByRole('textbox', { name: 'Napišite komentar' });
  await expect(edited).toBeFocused();
  await edited.fill('Može li rok biti 60 dana uz jamstvo?');
  await thread.getByRole('button', { name: 'Spremi' }).click();
  await expect(thread.getByRole('listitem').first()).toContainText('uređeno');
  await expect(theirs.getByRole('article', { name: '30 dana' })).toContainText('60 dana');

  await editor.getByText('Rok plaćanja').click({ position: { x: 1, y: 1 } });
  await expect(thread).not.toHaveAttribute('aria-current');
  await selectThirtyDays();
  await page.keyboard.press('Backspace');
  await expect(thread).toContainText('Tekst na koji se komentar odnosi obrisan je.');
  await expect(editor.locator('.ponistra-comment')).toHaveCount(0);
  await page.keyboard.press('Control+z');
  await expect(editor.locator('.ponistra-comment')).toHaveText('30 dana');
  await expect(thread).not.toContainText('obrisan je');

  await thread.getByRole('button', { name: 'Riješi' }).click();
  await expect(thread).toHaveCount(0);
  await expect(editor.locator('.ponistra-comment')).toHaveCount(0);
  await expect(other.locator('.ProseMirror .ponistra-comment')).toHaveCount(0);
  await panel.getByRole('checkbox', { name: 'Prikaži riješene (1)' }).check();
  await expect(thread).toContainText('Riješeno');
  await thread.getByRole('button', { name: 'Ponovno otvori' }).click();
  await expect(thread.getByRole('button', { name: 'Riješi' })).toBeVisible();

  const search = page.getByRole('combobox', { name: 'Pretraži' });
  await search.fill('bankovno');
  await page.getByRole('option', { name: /Probni komentari/ }).click();
  await expect(page).toHaveURL(/\?panel=comments&comment=/);
  await expect(thread).toHaveAttribute('aria-current', 'true');

  const comments = thread.getByRole('listitem');
  for (const left of [1, 0]) {
    await comments.first().getByRole('button', { name: 'Radnje' }).click();
    await page.getByRole('menuitem', { name: 'Obriši' }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Obriši' }).click();
    await expect(comments).toHaveCount(left);
  }
  await expect(thread).toHaveCount(0);
  await expect(panel).toContainText('Na ovoj kartici nema komentara.');
  await expect(other.getByRole('button', { name: 'Komentari', exact: true })).toBeVisible();
});
