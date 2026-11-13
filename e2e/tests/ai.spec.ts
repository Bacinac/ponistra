import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { newDocument, nodeHref } from './helpers/nodes';
import { pdfFile, upload } from './helpers/pdf';

const RUN = '00000000-0000-4000-8000-000000000a4a';
const LATEST = '00000000-0000-4000-8000-000000000a42';
const FIRST = '00000000-0000-4000-8000-000000000a41';

test('a model’s actions are disabled while AI is off, and ask before they send the text out', async ({
  page,
  problems,
}) => {
  let ai = false;
  await page.route('**/api/actions', async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), ai } });
  });
  await page.goto(await newDocument(page, 'Probni sažetak'));
  const editor = page.locator('.ProseMirror').first();
  await editor.click();
  await page.keyboard.type('Najam stana na godinu dana.');
  await editor.getByText('Najam').click({ button: 'right' });
  const summarise = page.getByRole('menuitem', { name: /^Sažmi/ });
  await expect(summarise).toBeDisabled();
  await expect(summarise).toContainText('Umjetna inteligencija nije uključena');
  const rewrite = page.getByRole('menuitem', { name: /^Prepiši/ });
  await expect(rewrite).toBeDisabled();
  await expect(rewrite).toContainText('Umjetna inteligencija nije uključena');
  const translate = page.getByRole('menuitem', { name: /^Prevedi u novu karticu/ });
  await expect(translate).toBeDisabled();
  await expect(translate).toContainText('Umjetna inteligencija nije uključena');
  const compare = page.getByRole('menuitem', { name: /^Usporedi s verzijom…/ });
  await expect(compare).toBeDisabled();
  await expect(compare).toContainText('Umjetna inteligencija nije uključena');
  const ask = page.getByRole('menuitem', { name: /^Drugo…/ });
  await expect(ask).toBeDisabled();
  await expect(ask).toContainText('Umjetna inteligencija nije uključena');
  await page.keyboard.press('Escape');

  ai = true;
  const posted: Record<string, unknown>[] = [];
  const run = {
    id: RUN,
    action: 'text.summarise',
    target: {},
    error: '',
    started_at: new Date().toISOString(),
    finished_at: null,
    reply: '',
    changed: true,
  };
  let asked: { request: string; thread: string } | null = null;
  await page.route(/\/api\/tabs\/[^/]+\/runs(\?|$)/, async (route) => {
    if (route.request().method() !== 'POST') {
      if (!asked) {
        // A new thread's first read answers only after the run it asks about has started.
        if (new URL(route.request().url()).searchParams.has('thread'))
          await new Promise((resolve) => setTimeout(resolve, 2000));
        return route.fallback();
      }
      const turn = { ...run, ...asked, state: 'done', finished_at: run.started_at, offers: [] };
      return route.fulfill({ json: { thread: asked.thread, turns: [turn] } });
    }
    const body = route.request().postDataJSON();
    posted.push(body);
    if (body.action === 'text.ask' && body.consent) asked = body.parameters;
    run.action = body.action;
    run.reply = body.action === 'text.ask' ? 'Dokument nema tablica pa nemam što zbrojiti.' : '';
    run.changed = body.action !== 'text.ask';
    if (!body.consent) return route.fulfill({ status: 428, json: { error: 'consent_needed' } });
    await route.fulfill({ status: 202, json: { run: { ...run, state: 'running' } } });
  });
  await page.route(`**/api/runs/${RUN}`, (route) =>
    route.fulfill({ json: { run: { ...run, state: 'done', finished_at: run.started_at } } }),
  );
  await page.reload();
  await editor.getByText('Najam').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Sažmi' }).click();
  const dialog = page.getByRole('dialog', { name: 'Slanje teksta modelu Claude' });
  await expect(dialog).toContainText('Anthropic u SAD-u');
  await dialog.getByRole('button', { name: 'Samo ovaj put' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('status').filter({ hasText: 'Izvedeno: Sažmi' })).toBeVisible();

  await editor.getByText('Najam').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Prepiši' }).click();
  await page.getByRole('menuitem', { name: 'Kraće' }).click();
  await dialog.getByRole('button', { name: 'Samo ovaj put' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Izvedeno: Prepiši' })).toBeVisible();

  const saved = { restored_from: null, editors: [], created_at: run.started_at };
  await page.route('**/api/nodes/*/versions', (route) =>
    route.fulfill({
      json: {
        versions: [
          { ...saved, id: LATEST, number: 2, title: 'Ponuda' },
          { ...saved, id: FIRST, number: 1, title: '' },
        ],
      },
    }),
  );
  await editor.getByText('Najam').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Usporedi s verzijom…' }).click();
  const comparing = page.getByRole('dialog', { name: 'Usporedi s verzijom' });
  const version = comparing.getByLabel('Verzija');
  await expect(version).toHaveValue(LATEST);
  await version.selectOption(FIRST);
  await comparing.getByRole('button', { name: 'Usporedi' }).click();
  await dialog.getByRole('button', { name: 'Samo ovaj put' }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Izvedeno: Usporedi s verzijom' }),
  ).toBeVisible();

  await editor.getByText('Najam').click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Drugo…' }).click();
  const panel = page.getByRole('complementary', { name: 'Agent' });
  const starts = panel.getByRole('button', { name: 'Pošalji' });
  await expect(starts).toBeDisabled();
  await panel.getByLabel('Uputa agentu').fill('Zbroji.');
  await starts.click();
  await dialog.getByRole('button', { name: 'Samo ovaj put' }).click();
  await expect(panel).toContainText('Dokument nema tablica pa nemam što zbrojiti.');
  await expect(panel.getByRole('button', { name: 'Poništi' })).toHaveCount(0);
  const thread = asked!.thread;
  expect(posted.map((each) => [each.action, each.parameters, each.consent])).toEqual([
    ['text.summarise', {}, undefined],
    ['text.summarise', {}, 'once'],
    ['text.rewrite', { way: 'short' }, undefined],
    ['text.rewrite', { way: 'short' }, 'once'],
    ['document.compare', { version: FIRST }, undefined],
    ['document.compare', { version: FIRST }, 'once'],
    ['text.ask', { request: 'Zbroji.', thread }, undefined],
    ['text.ask', { request: 'Zbroji.', thread }, 'once'],
  ]);
  const refused = problems.filter((problem) => problem.includes('status of 428'));
  expect(refused).toHaveLength(4);
  problems.splice(0, problems.length, ...problems.filter((problem) => !refused.includes(problem)));
});

test('documents chosen in a folder give a row each to a table in a new document beside them', async ({
  page,
  problems,
}) => {
  let ai = false;
  await page.route('**/api/actions', async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), ai } });
  });
  await newDocument(page, 'Najam Ana');
  await newDocument(page, 'Najam Ivo');
  const node = await page.evaluate(async () => {
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const response = await fetch('/api/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ kind: 'document', title: 'Pregled najma', parent: null }),
    });
    return response.json();
  });
  const made = { node, href: nodeHref(node) };
  await page.goto('/documents');
  const choose = async () => {
    await page.getByRole('row', { name: /Najam Ana/ }).click({ modifiers: ['ControlOrMeta'] });
    await page.getByRole('row', { name: /Najam Ivo/ }).click({ modifiers: ['ControlOrMeta'] });
    await page.getByRole('row', { name: /Najam Ivo/ }).click({ button: 'right' });
  };
  await choose();
  const gather = page.getByRole('menuitem', { name: /^Izvuci podatke u tablicu…/ });
  await expect(gather).toBeDisabled();
  await expect(gather).toContainText('Umjetna inteligencija nije uključena');
  await page.keyboard.press('Escape');

  ai = true;
  const posted: Record<string, unknown>[] = [];
  const run = {
    id: RUN,
    action: 'nodes.extract',
    model: 'claude-sonnet-5-5',
    target: {},
    error: '',
    started_at: new Date().toISOString(),
    finished_at: null,
    reply: '',
    changed: true,
  };
  await page.route('**/api/runs', async (route) => {
    posted.push(route.request().postDataJSON());
    const items = { of: 2, through: 0, missed: [] };
    await route.fulfill({
      status: 202,
      json: { run: { ...run, state: 'running', items }, document: made.node },
    });
  });
  const answers = [
    { ...run, state: 'running', items: { of: 2, through: 1, missed: [] } },
    {
      ...run,
      state: 'done',
      finished_at: run.started_at,
      items: { of: 2, through: 2, missed: [{ title: 'Najam Ivo', error: 'empty' }] },
    },
  ];
  await page.route(`**/api/runs/${RUN}`, (route) =>
    route.fulfill({ json: { run: answers.length > 1 ? answers.shift() : answers[0] } }),
  );
  await page.reload();
  await choose();
  await page.getByRole('menuitem', { name: 'Izvuci podatke u tablicu…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Izvuci podatke u tablicu' });
  await expect(dialog.getByLabel('Naziv')).toHaveValue('Podaci');
  await expect(dialog).toContainText('Anthropic u SAD-u');
  await expect(dialog).toContainText('Bez stupaca Claude ih bira prema prvom dokumentu.');
  const columns = dialog.getByLabel('Stupci, jedan po retku');
  await columns.fill('x'.repeat(101));
  await expect(dialog).toContainText('Najviše 30 različitih stupaca, svaki do 100 znakova.');
  await expect(dialog.getByRole('button', { name: 'Izvuci' })).toBeDisabled();
  await columns.fill('Najmoprimac\n  Najamnina (EUR)\n\nNajmoprimac');
  await dialog.getByLabel('Naziv').fill('Pregled najma');
  await dialog.getByRole('button', { name: 'Izvuci' }).click();
  await expect(dialog).toHaveCount(0);
  expect(posted).toHaveLength(1);
  expect(posted[0]).toMatchObject({
    action: 'nodes.extract',
    parameters: { title: 'Pregled najma', columns: ['Najmoprimac', 'Najamnina (EUR)'] },
    consent: 'once',
  });
  expect((posted[0].target as { nodes: string[] }).nodes).toHaveLength(2);

  const status = page.getByRole('status').filter({ hasText: 'Izvuci podatke u tablicu' });
  await expect(status).toContainText('Claude piše…');
  await expect(status).toContainText('Obrađeno: 1 / 2');
  await expect(status.getByRole('button', { name: 'Zaustavi' })).toBeVisible();
  await expect(status).toContainText('Izvedeno: Izvuci podatke u tablicu · Preskočeno: 1');
  await expect(status).toContainText('Najam Ivo: Nema teksta na koji bi se radnja primijenila.');
  await expect(status.getByRole('button', { name: 'Poništi akciju' })).toBeVisible();
  await status.getByRole('button', { name: 'Otvori' }).click();
  await expect(page).toHaveURL(new RegExp(`${made.href}$`));
});

/** The file page's reading of the PDF, once code tells the language of its text. */
function languageKnown(page: Page, language: string) {
  return page.waitForResponse(
    async (response) =>
      /^\/api\/nodes\/[^/]+$/.test(new URL(response.url()).pathname) &&
      (await response.json().catch(() => null))?.pdf?.language === language,
  );
}

test('a PDF file in a language the user does not read is translated page by page into theirs', async ({
  page,
}) => {
  test.slow();
  let ai = false;
  await page.route('**/api/actions', async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), ai } });
  });
  const croatian = languageKnown(page, 'hr');
  await upload(
    page,
    'Ponuda odrzavanja',
    pdfFile({ pages: [[{ text: 'Postovani, nudimo vam odrzavanje opreme.', top: 100 }]] }),
  );
  await croatian;
  await page.getByRole('button', { name: 'Ponuda odrzavanja', exact: true }).click();
  await expect(page.getByRole('menuitem', { name: 'Otvori zasebno' })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: /^Prevedi na hrvatski/ })).toHaveCount(0);
  await page.keyboard.press('Escape');

  const german = languageKnown(page, 'de');
  await upload(
    page,
    'Angebot Wartung',
    pdfFile({
      pages: [
        [{ text: 'Sehr geehrte Damen und Herren, wir bieten', top: 100 }],
        [{ text: 'die Wartung an.', top: 100 }],
      ],
    }),
  );
  await german;
  const menu = page.getByRole('button', { name: 'Angebot Wartung', exact: true });
  await menu.click();
  const translate = page.getByRole('menuitem', { name: /^Prevedi na hrvatski…/ });
  await expect(translate).toBeDisabled();
  await expect(translate).toContainText('Umjetna inteligencija nije uključena');
  await page.keyboard.press('Escape');

  ai = true;
  const node = await page.evaluate(async () => {
    const token = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? '';
    const response = await fetch('/api/nodes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': token },
      body: JSON.stringify({ kind: 'document', title: 'Angebot Wartung – Hrvatski', parent: null }),
    });
    return response.json();
  });
  const made = { node, href: nodeHref(node) };
  const posted: Record<string, unknown>[] = [];
  const run = {
    id: RUN,
    action: 'file.translate',
    model: 'claude-sonnet-5-5',
    target: {},
    error: '',
    started_at: new Date().toISOString(),
    finished_at: null,
    reply: '',
    changed: true,
  };
  await page.route('**/api/runs', async (route) => {
    posted.push(route.request().postDataJSON());
    await route.fulfill({
      status: 202,
      json: {
        run: { ...run, state: 'running', items: { of: 2, through: 0, missed: [] } },
        document: made.node,
      },
    });
  });
  const answers = [
    { ...run, state: 'running', items: { of: 2, through: 1, missed: [] } },
    {
      ...run,
      state: 'done',
      finished_at: run.started_at,
      items: { of: 2, through: 2, missed: [{ title: '2', error: 'empty' }] },
    },
  ];
  await page.route(`**/api/runs/${RUN}`, (route) =>
    route.fulfill({ json: { run: answers.length > 1 ? answers.shift() : answers[0] } }),
  );
  await page.reload();
  await menu.click();
  await page.getByRole('menuitem', { name: 'Prevedi na hrvatski…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Prevedi na hrvatski' });
  await expect(dialog).toContainText('Anthropic u SAD-u');
  await dialog.getByRole('button', { name: 'Prevedi' }).click();
  await expect(dialog).toHaveCount(0);
  expect(posted).toHaveLength(1);
  expect(posted[0]).toMatchObject({
    action: 'file.translate',
    parameters: { language: 'hr' },
    consent: 'once',
  });
  expect((posted[0].target as { nodes: string[] }).nodes).toHaveLength(1);

  const status = page.getByRole('status').filter({ hasText: 'Prijevod PDF-a' });
  await expect(status).toContainText('Claude piše…');
  await expect(status).toContainText('Obrađeno: 1 / 2');
  await expect(status).toContainText('Izvedeno: Prijevod PDF-a · Preskočeno: 1');
  await expect(status).toContainText('Stranica 2: Nema teksta na koji bi se radnja primijenila.');
  await status.getByRole('button', { name: 'Otvori' }).click();
  await expect(page).toHaveURL(new RegExp(`${made.href}$`));
});
