import { readFile } from 'node:fs/promises';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';
import { unzipped } from './helpers/zip';

function showView(page: Page, name: string): Promise<void> {
  return page.getByRole('group', { name: 'Prikaz' }).getByRole('button', { name }).click();
}

async function insert(page: Page, query: string, option: string): Promise<void> {
  await page.keyboard.type(`/${query}`);
  await page.getByRole('option', { name: option }).click();
}

test('slide and column breaks and speaker notes show in the text and stay off the pages', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Prezentacija'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('# Cijene');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Najam');
  await page.keyboard.press('Control+Shift+Enter');
  await page.keyboard.type('Prodaja');
  await page.keyboard.press('Enter');
  await insert(page, 'slajd', 'Prijelom slajda');
  await page.keyboard.type('Kontakt');
  await page.keyboard.press('Enter');
  await insert(page, 'bilješke', 'Bilješke govornika');
  await page.keyboard.type('Zahvaliti');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Pitati');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Kraj');

  await expect(editor.locator('[data-column-break]')).toHaveCount(1);
  await expect(editor.locator('[data-slide-break]')).toHaveCount(1);
  await expect(editor.locator('p[data-speaker]')).toHaveText(['Zahvaliti', 'Pitati']);
  await expect(editor.locator('.ponistra-speaker-label')).toHaveText('Bilješke govornika');
  await expect(editor.locator('p:not([data-speaker])').last()).toHaveText('Kraj');

  await showView(page, 'Stranice');
  await expect(page.locator('.ponistra-paper').first()).toBeVisible();
  await expect(editor.locator('p[data-speaker]').first()).toBeHidden();
  await expect(editor.locator('[data-slide-break]')).toBeHidden();
  await expect(editor.locator('[data-column-break]')).toBeHidden();
  await expect(editor.getByText('Kraj')).toBeVisible();
});

test('the Slides view lays each slide in its layout’s boxes, shrinks text to fit them, and the slides go to PowerPoint and come back', async ({
  page,
}) => {
  const offer = await newDocument(page, 'Ponuda');
  await page.goto(offer);
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('# Cijene');
  await page.keyboard.press('Enter');
  for (let item = 1; item <= 12; item++) {
    await page.keyboard.type(`Stavka ${item}`);
    await page.keyboard.press('Enter');
  }
  await page.keyboard.type('# Usporedba');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Lijevo');
  await page.keyboard.press('Control+Shift+Enter');
  await page.keyboard.type('Desno');
  await page.keyboard.press('Enter');
  await insert(page, 'bilješke', 'Bilješke govornika');
  await page.keyboard.type('Zahvaliti');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await page.keyboard.type('# Hvala');

  await showView(page, 'Slajdovi');
  const slides = page.locator('.ponistra-slide');
  await expect(slides).toHaveCount(3);
  const last = editor.getByText('Stavka 12');
  await expect(last).toHaveAttribute('style', /--fit: 0\.\d+/);
  const first = (await slides.nth(0).boundingBox())!;
  await expect
    .poll(async () => {
      const box = (await last.boundingBox())!;
      return box.y + box.height <= first.y + first.height;
    })
    .toBe(true);
  await expect(page.locator('.ponistra-slide-over')).toHaveCount(0);

  const left = (await editor.getByText('Lijevo').boundingBox())!;
  const right = (await editor.getByText('Desno').boundingBox())!;
  expect(Math.abs(left.y - right.y)).toBeLessThan(1);
  expect(right.x).toBeGreaterThan(left.x + left.width);
  await expect(page.locator('.ponistra-slide-notes')).toHaveText('Bilješke govornika');
  await expect(editor.getByText('Zahvaliti')).toBeVisible();

  const prompt = page.locator('.ponistra-slide-prompt');
  await expect(prompt).toHaveText('Kliknite za dodavanje teksta');
  await prompt.scrollIntoViewIfNeeded();
  const empty = (await prompt.boundingBox())!;
  await page.mouse.click(empty.x + empty.width / 2, empty.y + empty.height / 2);
  await page.keyboard.type('Pitanja?');
  await expect(prompt).toHaveCount(0);
  const layout = page.getByRole('combobox', { name: 'Raspored slajda' });
  await expect(layout).toHaveValue('slide.layout.section');

  await editor.getByText('Desno').click();
  const hide = page.getByRole('button', { name: 'Sakrij slajd' });
  await hide.click();
  await expect(hide).toHaveAttribute('aria-pressed', 'true');
  await expect(slides.nth(1)).toHaveAttribute('data-hidden', 'true');
  await expect(page.locator('.ponistra-slide-head').nth(1)).toContainText('Skriven');

  await editor.getByText('Cijene').click();
  await expect(hide).toHaveAttribute('aria-pressed', 'false');
  await expect(layout).toHaveValue('slide.layout');
  await layout.selectOption({ label: 'Naslovni slajd' });
  await expect(editor.getByText('Cijene')).toHaveCSS('font-size', '72px');

  await page.getByRole('button', { name: 'Veličina slajda' }).click();
  await page.getByRole('menuitemcheckbox', { name: 'Standardni (4 : 3)' }).click();
  await expect
    .poll(async () => {
      const box = (await slides.nth(0).boundingBox())!;
      return Math.round((box.width / box.height) * 100) / 100;
    })
    .toBe(1.33);

  await showView(page, 'Tekst');
  await expect(editor.locator('.ponistra-placed')).toHaveCount(0);
  await expect(editor.getByText('Cijene')).toHaveAttribute('data-layout', 'title');

  const download = page.waitForEvent('download');
  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Spremi kao' }).click();
  await page.getByRole('menuitem', { name: 'PowerPoint (.pptx)' }).click();
  const saved = await download;
  expect(saved.suggestedFilename()).toBe('Ponuda.pptx');
  const file = unzipped(await readFile((await saved.path())!));
  expect(file['ppt/presentation.xml']).toContain('<p:sldSz cx="9144000" cy="6858000"/>');
  expect(file['ppt/presentation.xml']).toMatch(/<p14:section name="[^"]+"/);
  const [title, hidden, closing] = [1, 2, 3].map((at) => file[`ppt/slides/slide${at}.xml`]);
  expect(title).toMatch(/<p:ph type="ctrTitle"\/>.*Cijene/s);
  expect(title).toMatch(/<a:normAutofit fontScale="\d+"\/>.*Stavka 12/s);
  expect(hidden).toMatch(/<p:sld [^>]*show="0"/);
  expect(hidden).toMatch(/Lijevo.*Desno/s);
  expect(file['ppt/notesSlides/notesSlide1.xml']).toContain('Zahvaliti');
  expect(closing).toMatch(/Hvala.*Pitanja\?/s);

  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (
    await chooser
  ).setFiles({
    name: 'Ponuda natrag.pptx',
    mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    buffer: await readFile((await saved.path())!),
  });
  await page
    .getByRole('row', { name: /Ponuda natrag/ })
    .getByText('Ponuda natrag', { exact: true })
    .dblclick();
  const views = page.getByRole('group', { name: 'Prikaz' });
  await expect(views.getByRole('button', { name: 'Slajdovi' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expect(slides).toHaveCount(3);
  await expect(slides.nth(1)).toHaveAttribute('data-hidden', 'true');
  const back = (await slides.nth(0).boundingBox())!;
  expect(Math.round((back.width / back.height) * 100) / 100).toBe(1.33);
  await editor.getByText('Cijene').click();
  await expect(layout.locator('option:checked')).toHaveText('Naslovni slajd');
  await expect(editor.getByText('Stavka 12')).toBeVisible();
  await expect(editor.getByText('Zahvaliti')).toBeVisible();
  await expect(editor.getByText('Pitanja?')).toBeVisible();

  await page.goto(offer);
  await expect(views.getByRole('button', { name: 'Tekst' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('a show runs every tab’s slides on the whole screen, its presenter’s window following it', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Izlaganje'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('# Uvod');
  await page.keyboard.press('Enter');
  await insert(page, 'bilješke', 'Bilješke govornika');
  await page.keyboard.type('Pozdraviti publiku');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await page.keyboard.type('# Skriveni');
  await page.keyboard.press('Enter');
  await page.keyboard.type('# Cijene');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Najam');

  await showView(page, 'Slajdovi');
  await editor.getByText('Skriveni').click();
  const hide = page.getByRole('button', { name: 'Sakrij slajd' });
  await hide.click();
  await expect(hide).toHaveAttribute('aria-pressed', 'true');

  await showView(page, 'Tekst');
  await page.getByRole('button', { name: 'Nova kartica' }).click();
  await expect(editor).not.toContainText('Uvod');
  await editor.click();
  await page.keyboard.type('# Pitanja');
  await showView(page, 'Slajdovi');
  await expect(page.locator('.ponistra-slide-head')).toHaveText('4');

  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Izlaži od početka' }).click();
  const show = page.getByRole('dialog', { name: 'Izlaganje' });
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true);
  await expect(show.getByText('Uvod')).toBeInViewport();
  await expect(show.getByText('Cijene')).not.toBeInViewport();
  await page.keyboard.press('ArrowRight');
  await expect(show.getByText('Cijene')).toBeInViewport();
  await expect(show.getByText('Skriveni')).not.toBeInViewport();
  await page.keyboard.press('Space');
  await expect(show.getByText('Pitanja')).toBeInViewport();
  await show.click();
  await expect(show.getByText('Kraj izlaganja. Kliknite za izlaz.')).toBeVisible();
  await page.keyboard.type('2');
  await page.keyboard.press('Enter');
  await expect(show.getByText('Skriveni')).toBeInViewport();
  await page.keyboard.press('Home');
  await expect(show.getByText('Uvod')).toBeInViewport();

  const opened = page.waitForEvent('popup');
  await show.getByRole('button', { name: 'Izlagački prikaz' }).click();
  const presenter = await opened;
  const current = presenter.getByRole('region', { name: 'Trenutni slajd' });
  await expect(current.getByText('Uvod')).toBeInViewport();
  await expect(
    presenter.getByRole('region', { name: 'Sljedeći slajd' }).getByText('Cijene'),
  ).toBeInViewport();
  await expect(presenter.getByRole('region', { name: 'Bilješke govornika' })).toContainText(
    'Pozdraviti publiku',
  );
  await expect(presenter.getByText('Slajd 1 / 4')).toBeVisible();
  await expect(presenter.getByLabel('Proteklo vrijeme')).toHaveText(/^0:0\d:\d\d$/);
  await expect(show).toBeVisible();

  await presenter.keyboard.press('ArrowRight');
  await expect(show.getByText('Cijene')).toBeInViewport();
  await expect(current.getByText('Cijene')).toBeInViewport();
  await expect(presenter.getByText('Slajd 3 / 4')).toBeVisible();
  await page.keyboard.press('ArrowLeft');
  await expect(current.getByText('Uvod')).toBeInViewport();

  const closed = presenter.waitForEvent('close');
  await presenter.getByRole('button', { name: 'Završi izlaganje' }).click();
  await closed;
  await expect(show).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(false);

  await page.getByRole('navigation', { name: 'Kartice' }).getByRole('link').first().click();
  await expect(editor.getByText('Uvod')).toBeVisible();
  await editor.getByText('Cijene').click();
  await page.getByRole('button', { name: 'Izlaži od ovog slajda' }).click();
  await expect(show.getByText('Cijene')).toBeInViewport();
  await expect(editor).not.toBeFocused();
  await page.keyboard.press('Escape');
  await expect(show).toHaveCount(0);
  await expect(editor).toBeFocused();
});

test('a show runs what was written in this browser before the server has received it', async ({
  page,
}) => {
  await page.routeWebSocket('**/api/collab/**', (socket) => {
    const server = socket.connectToServer();
    socket.onMessage((message) => {
      const edit = typeof message !== 'string' && message[0] === 0 && message[1] === 2;
      if (!edit) server.send(message);
    });
  });
  await page.goto(await newDocument(page, 'Netom napisano'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('# Uvod');
  await page.keyboard.press('Enter');
  await page.keyboard.type('# Cijene');

  await page.locator('header button[aria-current="page"]').click();
  await page.getByRole('menuitem', { name: 'Izlaži od početka' }).click();
  const show = page.getByRole('dialog', { name: 'Izlaganje' });
  await expect(show.getByText('Uvod')).toBeInViewport();
  await page.keyboard.press('ArrowRight');
  await expect(show.getByText('Cijene')).toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(show).toHaveCount(0);
});
