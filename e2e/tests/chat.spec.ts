import type { Browser, Page } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { expect, sessions, test } from './fixtures';

/** The colleague's own device, signed in with their session. */
async function colleagueDevice(browser: Browser, baseURL: string, problems: string[]) {
  const context = await browser.newContext({ baseURL, locale: 'hr-HR' });
  await context.addCookies([
    { name: 'sessionid', value: sessions().colleague, url: baseURL },
    { name: 'csrftoken', value: randomBytes(16).toString('hex'), url: baseURL },
  ]);
  const page = await context.newPage();
  page.on('pageerror', (error) => problems.push(`${page.url()} ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      problems.push(`${page.url()} ${message.type()}: ${message.text()}`);
    }
  });
  return page;
}

async function openChat(page: Page) {
  await page.goto('/');
  await page
    .getByRole('navigation', { name: 'Moduli' })
    .getByRole('link', { name: 'Razgovori' })
    .click();
}

/** Starts a conversation with the colleague, under a group name where one is given. */
async function started(page: Page, title = '') {
  await page.getByRole('button', { name: 'Novi razgovor' }).click();
  const dialog = page.getByRole('dialog', { name: 'Novi razgovor' });
  const { name } = sessions();
  await dialog.getByRole('combobox', { name: 'Kolege' }).fill(name.split(' ')[0]);
  await dialog.getByRole('option', { name: new RegExp(name) }).click();
  if (title) await dialog.getByLabel('Naziv skupine (neobvezno)').fill(title);
  await dialog.getByRole('button', { name: 'Započni' }).click();
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
  return new URL(page.url()).pathname;
}

const messages = (page: Page) => page.getByRole('list', { name: 'Poruke' });
const conversations = (page: Page) => page.getByRole('list', { name: 'Vaši razgovori' });

test('a conversation with a colleague is started once, its message edited and taken back', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const said = `Dolazim u 8 ${randomBytes(3).toString('hex')}`;
  const edited = `Dolazim u 9 ${randomBytes(3).toString('hex')}`;
  await openChat(page);
  const path = await started(page);
  await expect(page.getByRole('heading', { name: sessions().name, level: 1 })).toBeVisible();
  await page.getByLabel('Napišite poruku').fill(said);
  await page.getByLabel('Napišite poruku').press('Enter');
  await expect(messages(page)).toContainText(said);

  const colleague = await colleagueDevice(browser, baseURL!, problems);
  await openChat(colleague);
  const theirs = conversations(colleague).getByRole('link').filter({ hasText: said });
  await expect(theirs.getByLabel('Nepročitano')).toHaveText('1');
  await theirs.click();
  await expect(colleague).toHaveURL(path);
  await expect(messages(colleague)).toContainText(said);

  await messages(page).getByRole('button', { name: 'Radnje poruke' }).click();
  await page.getByRole('menuitem', { name: 'Uredi' }).click();
  await expect(page.getByLabel('Napišite poruku')).toHaveValue(said);
  await page.getByLabel('Napišite poruku').fill(edited);
  await page.getByLabel('Napišite poruku').press('Enter');
  await expect(messages(page)).toContainText(edited);
  await expect(messages(page)).toContainText('uređeno');
  await expect(messages(page)).not.toContainText(said);
  await expect(messages(colleague)).toContainText(edited);

  const reactions = (on: Page) => messages(on).getByRole('list', { name: 'Reakcije' });
  await messages(colleague).getByText(edited).hover();
  await messages(colleague).getByRole('button', { name: 'Reagiraj' }).click();
  await colleague.getByRole('menuitem', { name: '👍' }).click();
  for (const each of [page, colleague])
    await expect(reactions(each).getByRole('button', { name: /👍/ })).toBeVisible();
  await expect(reactions(colleague).getByRole('button', { name: /👍/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await messages(colleague).getByText(edited).click({ button: 'right' });
  await colleague.getByRole('menuitem', { name: 'Više…' }).click();
  const choosing = colleague.getByRole('dialog', { name: 'Odaberite emoji' });
  await choosing.getByLabel('Pretraži emojije').fill('crveno srce');
  await choosing.getByRole('gridcell', { name: 'crveno srce' }).click();
  await expect(choosing).toBeHidden();
  await expect(reactions(page).getByRole('button', { name: /❤️/ })).toBeVisible();
  await reactions(colleague).getByRole('button', { name: /👍/ }).click();
  for (const each of [page, colleague])
    await expect(reactions(each).getByRole('button', { name: /👍/ })).toBeHidden();

  await messages(page).getByRole('button', { name: 'Radnje poruke' }).click();
  await page.getByRole('menuitem', { name: 'Povuci' }).click();
  await page
    .getByRole('alertdialog', { name: 'Povuci' })
    .getByRole('button', { name: 'Povuci' })
    .click();
  for (const each of [page, colleague])
    await expect(each.getByRole('main').getByText('Još nema poruka.')).toBeVisible();
  await colleague.context().close();

  await page.goto('/chat');
  await expect(page).toHaveURL(path);
  await started(page);
  await expect(page).toHaveURL(path);
});

test('a group under a name takes people, is renamed and left', async ({ page }) => {
  const name = `Projekt ${randomBytes(3).toString('hex')}`;
  const renamed = `${name} B`;
  await openChat(page);
  await started(page, name);
  const main = page.getByRole('main');
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(main.getByRole('paragraph').filter({ hasText: sessions().name })).toBeVisible();

  await main.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Preimenuj' }).click();
  const dialog = page.getByRole('dialog', { name: 'Preimenuj skupinu' });
  await dialog.getByLabel('Naziv').fill(renamed);
  await dialog.getByRole('button', { name: 'Spremi' }).click();
  await expect(page.getByRole('heading', { name: renamed, level: 1 })).toBeVisible();
  await expect(conversations(page).getByRole('link', { name: new RegExp(renamed) })).toBeVisible();

  await main.getByRole('button', { name: 'Radnje' }).click();
  await page.getByRole('menuitem', { name: 'Napusti razgovor' }).click();
  await page
    .getByRole('alertdialog', { name: 'Napusti razgovor' })
    .getByRole('button', { name: 'Napusti razgovor' })
    .click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(conversations(page).getByRole('link', { name: new RegExp(renamed) })).toHaveCount(0);
});

async function intoChannels(page: Page) {
  await page.getByRole('button', { name: 'Kanali', exact: true }).click();
  return page.getByRole('dialog', { name: 'Kanali' });
}

test('an open channel is found, read before joining, joined and deleted', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const tag = randomBytes(3).toString('hex');
  const name = `Nabava ${tag}`;
  await openChat(page);
  const list = await intoChannels(page);
  await list.getByRole('button', { name: 'Novi kanal' }).click();
  const dialog = page.getByRole('dialog', { name: 'Novi kanal' });
  await dialog.getByLabel('Naziv kanala').fill(name);
  await dialog.getByRole('button', { name: 'Stvori' }).click();
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await page.getByLabel('Napišite poruku').fill(`Dobro jutro ${tag}`);
  await page.getByLabel('Napišite poruku').press('Enter');
  await expect(messages(page)).toContainText(`Dobro jutro ${tag}`);

  const colleague = await colleagueDevice(browser, baseURL!, problems);
  await openChat(colleague);
  const found = await intoChannels(colleague);
  await found.getByRole('searchbox', { name: 'Traži kanale' }).fill(tag);
  await found.getByRole('link', { name: new RegExp(name) }).click();
  await expect(colleague.getByRole('heading', { name, level: 1 })).toBeVisible();
  await expect(messages(colleague)).toContainText(`Dobro jutro ${tag}`);
  await expect(colleague.getByLabel('Napišite poruku')).toBeHidden();

  await page.getByLabel('Napišite poruku').fill(`Još nešto ${tag}`);
  await page.getByLabel('Napišite poruku').press('Enter');
  await expect(messages(colleague)).toContainText(`Još nešto ${tag}`);

  await colleague.getByRole('button', { name: 'Pridruži se' }).click();
  await colleague.getByLabel('Napišite poruku').fill(`Evo me ${tag}`);
  await colleague.getByLabel('Napišite poruku').press('Enter');
  await expect(messages(page)).toContainText(`Evo me ${tag}`);
  await expect(colleague.getByRole('list', { name: 'Kanali' })).toContainText(name);
  await colleague.context().close();

  await page.getByRole('main').getByRole('button', { name: 'Radnje', exact: true }).click();
  await page.getByRole('menuitem', { name: 'Obriši kanal' }).click();
  await page
    .getByRole('alertdialog', { name: 'Obriši kanal' })
    .getByRole('button', { name: 'Obriši kanal' })
    .click();
  await expect(page).toHaveURL(/\/chat$/);
});

test('a private channel is not offered to a colleague', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const name = `Uprava ${randomBytes(3).toString('hex')}`;
  await openChat(page);
  const list = await intoChannels(page);
  await list.getByRole('button', { name: 'Novi kanal' }).click();
  const dialog = page.getByRole('dialog', { name: 'Novi kanal' });
  await dialog.getByLabel('Naziv kanala').fill(name);
  await dialog.getByRole('checkbox', { name: 'Privatni kanal' }).check();
  await dialog.getByRole('button', { name: 'Stvori' }).click();
  await expect(page.getByRole('list', { name: 'Kanali' })).toContainText(name);

  const colleague = await colleagueDevice(browser, baseURL!, problems);
  await openChat(colleague);
  const found = await intoChannels(colleague);
  await expect(found.getByRole('searchbox', { name: 'Traži kanale' })).toBeVisible();
  await expect(found).not.toContainText(name);
  await colleague.context().close();
});

test('a mention is offered, marked, and only it counts in a channel', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const tag = randomBytes(3).toString('hex');
  const name = `Skladište ${tag}`;
  const person = sessions().name;
  await openChat(page);
  const list = await intoChannels(page);
  await list.getByRole('button', { name: 'Novi kanal' }).click();
  const dialog = page.getByRole('dialog', { name: 'Novi kanal' });
  await dialog.getByLabel('Naziv kanala').fill(name);
  await dialog.getByRole('button', { name: 'Stvori' }).click();
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  const channel = page.url();

  const joining = await colleagueDevice(browser, baseURL!, problems);
  await joining.goto(channel);
  await joining.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(joining.getByLabel('Napišite poruku')).toBeVisible();
  await joining.context().close();
  // A wide screen opens the conversation it was last in, which reads every mention at once.
  const colleague = await colleagueDevice(browser, baseURL!, problems);
  await colleague.goto('/chat/');
  const row = colleague
    .getByRole('list', { name: 'Kanali' })
    .getByRole('link', { name: new RegExp(name) });
  await expect(row).toBeVisible();

  const box = page.getByLabel('Napišite poruku');
  await box.fill(`Obična poruka ${tag}`);
  await box.press('Enter');
  await expect(messages(page)).toContainText(`Obična poruka ${tag}`);
  await expect(row).toContainText(`Obična poruka ${tag}`);
  await expect(row.getByLabel('Nepročitano')).toBeHidden();

  await box.pressSequentially(`@${person.split(' ')[0]}`);
  const offered = page.getByRole('listbox', { name: 'Spomeni' });
  await expect(offered.getByRole('option', { name: person })).toBeVisible();
  await box.press('Enter');
  await expect(box).toHaveValue(`@${person} `);
  await box.pressSequentially('pogledaj');
  await box.press('Enter');
  await expect(messages(page).locator('mark')).toHaveText(`@${person}`);

  await expect(row.getByLabel('Nepročitano')).toHaveText('1');
  await row.click();
  await expect(messages(colleague).locator('mark')).toHaveText(`@${person}`);
  await expect(row.getByLabel('Nepročitano')).toBeHidden();
  await colleague.context().close();
});

test('a reply goes to the thread, which tells the one who wrote the message', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const tag = randomBytes(3).toString('hex');
  const name = `Kontrola ${tag}`;
  await openChat(page);
  const list = await intoChannels(page);
  await list.getByRole('button', { name: 'Novi kanal' }).click();
  const dialog = page.getByRole('dialog', { name: 'Novi kanal' });
  await dialog.getByLabel('Naziv kanala').fill(name);
  await dialog.getByRole('button', { name: 'Stvori' }).click();
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible();
  await page.getByLabel('Napišite poruku').fill(`Pitanje ${tag}`);
  await page.getByLabel('Napišite poruku').press('Enter');
  await expect(messages(page)).toContainText(`Pitanje ${tag}`);

  const colleague = await colleagueDevice(browser, baseURL!, problems);
  await colleague.goto(page.url());
  await colleague.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(colleague.getByLabel('Napišite poruku')).toBeVisible();
  await messages(colleague).getByText(`Pitanje ${tag}`).click({ button: 'right' });
  await colleague.getByRole('menuitem', { name: 'Odgovori u niti' }).click();
  const thread = colleague.getByRole('complementary', { name: 'Nit' });
  await thread.getByLabel('Napišite poruku').fill(`Odgovor ${tag}`);
  await thread.getByLabel('Napišite poruku').press('Enter');
  await expect(thread.getByRole('list', { name: 'Odgovori' })).toContainText(`Odgovor ${tag}`);

  const row = page
    .getByRole('list', { name: 'Kanali' })
    .getByRole('link', { name: new RegExp(name) });
  await expect(row.getByLabel('Nepročitano')).toHaveText('1');
  await expect(messages(page)).not.toContainText(`Odgovor ${tag}`);
  await messages(page)
    .getByRole('button', { name: /Odgovori: 1/ })
    .click();
  const mine = page.getByRole('complementary', { name: 'Nit' });
  await expect(mine.getByRole('list', { name: 'Odgovori' })).toContainText(`Odgovor ${tag}`);
  await expect(row.getByLabel('Nepročitano')).toBeHidden();
  await colleague.context().close();
});

const PIXEL = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
);

test('a picture goes without words, opens over the conversation and can be saved', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  await openChat(page);
  const path = await started(page);
  await page
    .locator('form input[type=file]')
    .setInputFiles({ name: 'skica.png', mimeType: 'image/png', buffer: PIXEL });
  await expect(page.getByRole('list', { name: 'Priložene datoteke' })).toContainText('skica.png');
  await page.getByRole('button', { name: 'Pošalji' }).click();
  await expect(page.getByRole('list', { name: 'Priložene datoteke' })).toBeHidden();

  const colleague = await colleagueDevice(browser, baseURL!, problems);
  await colleague.goto(path);
  await colleague.getByRole('button', { name: 'skica.png' }).click();
  const view = colleague.getByRole('dialog', { name: 'skica.png' });
  await expect(view.getByRole('img', { name: 'skica.png' })).toBeVisible();
  await view.getByRole('button', { name: 'Spremi u mapu' }).click();
  const place = colleague.getByRole('dialog', { name: 'Spremi u mapu' });
  await place.getByRole('button', { name: 'Spremi ovdje' }).click();
  await expect(view.getByRole('link', { name: 'Spremljeno, otvori' })).toBeVisible();
  await view.getByRole('button', { name: 'Zatvori' }).last().click();
  await expect(messages(colleague)).toBeVisible();
  await expect(page.getByText('Pročitano:')).toContainText(sessions().name);
  await expect(conversations(page)).toContainText('Datoteke: 1');
  await colleague.context().close();
});

test('an address in a message is a link without the sentence around it', async ({ page }) => {
  await openChat(page);
  await started(page);
  await page.getByRole('textbox', { name: 'Napišite poruku' }).fill('Vidi https://example.com/a.');
  await page.getByRole('button', { name: 'Pošalji' }).click();
  await expect(messages(page).getByRole('link')).toHaveAttribute('href', 'https://example.com/a');
});

test('a meeting opened in a channel is a message anyone there can join from', async ({ page }) => {
  await openChat(page);
  const list = await intoChannels(page);
  await list.getByRole('button', { name: 'Novi kanal' }).click();
  const made = page.getByRole('dialog', { name: 'Novi kanal' });
  await made.getByLabel('Naziv kanala').fill(`Montaža ${randomBytes(3).toString('hex')}`);
  await made.getByRole('button', { name: 'Stvori' }).click();
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
  const conversation = new URL(page.url()).pathname.split('/').at(-1);
  const opened = await page.evaluate(async (id) => {
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const answer = await fetch('/api/meetings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ conversation: id }),
    });
    return answer.status;
  }, conversation);
  expect(opened).toBe(201);
  await expect(messages(page).getByText('Otvoren je sastanak')).toBeVisible();
  await expect(messages(page).getByRole('link', { name: 'Pridruži se' })).toBeVisible();
});

test('a document of the tree goes as a card its reader opens over the conversation', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const title = `Ponuda ${randomBytes(3).toString('hex')}`;
  await openChat(page);
  const path = await started(page);
  const made = await page.evaluate(async (name) => {
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const answer = await fetch('/api/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ kind: 'document', parent: null, title: name }),
    });
    return answer.status;
  }, title);
  expect(made).toBe(201);
  await page.getByRole('button', { name: 'Priloži' }).click();
  await page.getByRole('menuitem', { name: 'Iz Dokumenata…' }).click();
  await page.getByRole('dialog', { name: 'Iz Dokumenata…' }).getByText(title).click();
  await expect(page.getByRole('list', { name: 'Priložene datoteke' })).toContainText(title);
  await page.getByRole('button', { name: 'Pošalji' }).click();
  await expect(messages(page).getByRole('button', { name: title })).toBeVisible();

  const colleague = await colleagueDevice(browser, baseURL!, problems);
  await colleague.goto(path);
  await messages(colleague).getByRole('button', { name: title }).click();
  const view = colleague.getByRole('dialog', { name: title });
  await expect(view.getByRole('link', { name: 'Otvori' })).toBeVisible();
  await colleague.context().close();
});
