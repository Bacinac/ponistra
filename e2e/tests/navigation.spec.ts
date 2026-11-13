import type { Page, WebSocketRoute } from '@playwright/test';
import { expect, test } from './fixtures';
import { addTabs, idIn, newDocument } from './helpers/nodes';

/** The document's tabs as the server orders them: title, then its parent's title. */
async function tabsOf(page: Page, address: string): Promise<[string, string | null][]> {
  return page.evaluate(
    async (id) => {
      const response = await fetch(`/api/nodes/${id}`);
      const { tabs } = (await response.json()) as {
        tabs: { id: string; parent: string | null; title: string }[];
      };
      const titleOf = (id: string | null) => tabs.find((tab) => tab.id === id)?.title ?? null;
      return tabs.map((tab) => [tab.title, titleOf(tab.parent)] as [string, string | null]);
    },
    idIn(address.split('/')[2]),
  );
}

test('the open tab lists its headings live and each leads to its block', async ({ page }) => {
  await page.goto(await newDocument(page, 'Ponuda s naslovima'));
  const editor = page.locator('.ProseMirror').first();
  const headings = page
    .getByRole('navigation', { name: 'Kartice' })
    .getByRole('list', { name: 'Naslovi' });

  await editor.click();
  await page.keyboard.type('# Uvod');
  await page.keyboard.press('Enter');
  for (let line = 0; line < 40; line++) {
    await page.keyboard.type(`Odlomak ${line}`);
    await page.keyboard.press('Enter');
  }
  await page.keyboard.type('## Cijene');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Kraj');
  await expect(headings.getByRole('link')).toHaveText(['Uvod', 'Cijene']);
  await expect(headings.getByRole('link', { name: 'Cijene' })).toHaveAttribute(
    'aria-current',
    'location',
  );

  await page.keyboard.press('Control+Home');
  await expect(headings.getByRole('link', { name: 'Uvod' })).toHaveAttribute(
    'aria-current',
    'location',
  );
  await expect(editor.locator('h2')).not.toBeInViewport();
  await headings.getByRole('link', { name: 'Cijene' }).click();
  await expect(page).toHaveURL(/\?block=/);
  await expect(editor.locator('h2')).toBeInViewport();

  await editor.locator('h2').click();
  await page.keyboard.press('End');
  await page.keyboard.type(' i rokovi');
  await expect(headings.getByRole('link')).toHaveText(['Uvod', 'Cijene i rokovi']);

  await page.keyboard.press('Control+Home');
  await expect(editor.locator('h2')).not.toBeInViewport();
  await page.setViewportSize({ width: 600, height: 800 });
  await page.getByRole('button', { name: 'Mape' }).click();
  const drawer = page.getByRole('dialog');
  await drawer.getByRole('link', { name: 'Cijene i rokovi' }).click();
  await expect(drawer).toHaveCount(0);
  await expect(editor.locator('h2')).toBeInViewport();
});

test('tabs move by their menu and by dragging, and the reader stays on their tab', async ({
  page,
}) => {
  const address = await newDocument(page, 'Ponuda s karticama');
  await addTabs(page, address, ['Cijene', 'Uvjeti']);
  await page.goto(address);
  const tabs = page.getByRole('navigation', { name: 'Kartice' });
  const links = tabs.getByRole('link');
  const menu = (index: number) => links.nth(index).click({ button: 'right' });
  await expect(links).toHaveText(['Kartica bez naziva', 'Cijene', 'Uvjeti']);

  await menu(0);
  await expect(page.getByRole('menuitem', { name: 'Premjesti gore' })).toBeDisabled();
  await expect(page.getByRole('menuitem', { name: 'Uvuci' })).toBeDisabled();
  await expect(page.getByRole('menuitem', { name: 'Izvuci' })).toBeDisabled();
  await page.keyboard.press('Escape');

  // A long press opens the tab's menu where it is, and leaves its link unfollowed.
  const before = page.url();
  await links.nth(2).hover();
  await page.mouse.down();
  await expect(page.getByRole('menuitem', { name: 'Premjesti gore' })).toBeVisible();
  await page.mouse.up();
  await expect(page).toHaveURL(before);
  await page.getByRole('menuitem', { name: 'Premjesti gore' }).click();
  await expect(links).toHaveText(['Kartica bez naziva', 'Uvjeti', 'Cijene']);
  await menu(2);
  await page.getByRole('menuitem', { name: 'Uvuci' }).click();
  await expect
    .poll(() => tabsOf(page, address))
    .toEqual([
      ['', null],
      ['Uvjeti', null],
      ['Cijene', 'Uvjeti'],
    ]);

  await tabs
    .getByRole('link', { name: 'Uvjeti' })
    .dragTo(tabs.getByRole('link', { name: 'Kartica bez naziva' }), {
      targetPosition: { x: 20, y: 2 },
    });
  await expect(links).toHaveText(['Uvjeti', 'Cijene', 'Kartica bez naziva']);
  await expect
    .poll(() => tabsOf(page, address))
    .toEqual([
      ['Uvjeti', null],
      ['Cijene', 'Uvjeti'],
      ['', null],
    ]);
  await expect(tabs.getByRole('link', { name: 'Kartica bez naziva' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await expect(page).toHaveURL(new RegExp(`${address}/[0-9A-Za-z]{22}$`));

  await tabs
    .getByRole('link', { name: 'Kartica bez naziva' })
    .dragTo(tabs.getByRole('link', { name: 'Cijene' }));
  await expect
    .poll(() => tabsOf(page, address))
    .toEqual([
      ['Uvjeti', null],
      ['Cijene', 'Uvjeti'],
      ['', 'Cijene'],
    ]);
});

test('tabs another editor adds or renames show at once for everyone with the document open', async ({
  page,
  context,
}) => {
  const address = await newDocument(page, 'Ponuda za dvoje');
  await page.goto(address);
  await expect(page.locator('.ProseMirror').first()).toBeVisible();
  const other = await context.newPage();
  await other.goto(address);
  await expect(other.locator('.ProseMirror').first()).toBeVisible();
  const theirs = other.getByRole('navigation', { name: 'Kartice' }).getByRole('link');
  await expect(theirs).toHaveText(['Kartica bez naziva']);

  await page.bringToFront();
  await addTabs(page, address, ['Cijene']);
  await expect(theirs).toHaveText(['Kartica bez naziva', 'Cijene']);

  const tabs = page.getByRole('navigation', { name: 'Kartice' });
  await expect(tabs.getByRole('link')).toHaveText(['Kartica bez naziva', 'Cijene']);
  await tabs.getByRole('link').last().click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Preimenuj' }).click();
  await page.getByRole('dialog').getByLabel('Naziv').fill('Cjenik');
  await page.getByRole('dialog').getByRole('button', { name: 'Spremi' }).click();
  await expect(theirs).toHaveText(['Kartica bez naziva', 'Cjenik']);
});

test('a version opens its menu where it is, by a right click and by a long press', async ({
  page,
}) => {
  const address = await newDocument(page, 'Ponuda s verzijama');
  await page.goto(`${address}?panel=versions`);
  const versions = page.getByRole('complementary', { name: 'Verzije' });
  await versions.getByRole('button', { name: 'Spremi verziju' }).click();
  await page.getByRole('dialog').getByLabel('Naziv').fill('Prva ponuda');
  await page.getByRole('dialog').getByRole('button', { name: 'Spremi' }).click();
  const version = versions.getByRole('link', { name: /Prva ponuda/ });

  const before = page.url();
  await version.hover();
  await page.mouse.down();
  await expect(page.getByRole('menuitem', { name: 'Vrati ovu verziju' })).toBeVisible();
  await page.mouse.up();
  await expect(page).toHaveURL(before);
  await page.keyboard.press('Escape');

  await version.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Preimenuj' }).click();
  await page.getByRole('dialog').getByLabel('Naziv').fill('Konačna ponuda');
  await page.getByRole('dialog').getByRole('button', { name: 'Spremi' }).click();
  await expect(versions.getByRole('link', { name: /Konačna ponuda/ })).toBeVisible();
  await expect(versions.getByRole('button', { name: 'Radnje' })).toHaveCount(0);
});

test('the day starts at Today, whose recent documents and rail lead into the documents', async ({
  page,
}) => {
  const address = await newDocument(page, 'Zapisnik sastanka');
  await page.goto('/');
  await expect(page).toHaveTitle('Danas – Ponistra');
  const rail = page.getByRole('navigation', { name: 'Moduli' });
  await expect(rail.getByRole('link', { name: 'Danas' })).toHaveAttribute('aria-current', 'page');
  await expect(rail.getByRole('link', { name: 'Kalendar' })).toHaveAttribute('href', '/calendar');
  const order = ['Danas', 'Kalendar', 'Pošta', 'Razgovori', 'Dokumenti'];
  const tops = await Promise.all(
    order.map(async (name) => (await rail.getByRole('link', { name }).boundingBox())!.y),
  );
  expect(tops).toEqual([...tops].sort((a, b) => a - b));
  await expect(rail.getByRole('link', { name: 'Postavke' })).toHaveCount(0);
  await expect(rail.getByRole('link', { name: 'Razgovori' })).toHaveAttribute('href', '/chat');
  await expect(page.getByRole('navigation', { name: 'Mape' })).toBeHidden();
  await expect(page.getByRole('heading', { name: 'Kalendari' })).toHaveCount(0);

  const recent = page.getByRole('region', { name: 'Nedavni dokumenti' });
  await recent.getByRole('link', { name: /Zapisnik sastanka/ }).click();
  await expect(page).toHaveURL(new RegExp(address));
  await expect(rail.getByRole('link', { name: 'Dokumenti' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await rail.getByRole('link', { name: 'Dokumenti' }).click();
  await expect(page).toHaveURL(/\/documents$/);
  await expect(page.getByRole('row', { name: /Zapisnik sastanka/ })).toHaveCount(1);
  await expect(rail.getByRole('link', { name: 'Sef' })).toHaveCount(0);
  await page.getByRole('navigation', { name: 'Mape' }).getByRole('link', { name: 'Sef' }).click();
  await expect(page).toHaveURL(/\/vault/);
  await expect(rail.getByRole('link', { name: 'Dokumenti' })).toHaveAttribute(
    'aria-current',
    'page',
  );

  await page.setViewportSize({ width: 600, height: 800 });
  await page.goto('/');
  await expect.poll(async () => (await rail.boundingBox())?.y).toBeGreaterThan(700);
  await expect(rail.getByRole('link')).toHaveText(order);
  await rail.getByRole('link', { name: 'Kalendar' }).click();
  await expect(page).toHaveURL(/\/calendar$/);
  await expect(rail.getByRole('link', { name: 'Kalendar' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await rail.getByRole('link', { name: 'Razgovori' }).click();
  await page.getByRole('link', { name: 'Kontakti', exact: true }).click();
  await expect(page).toHaveURL(/\/contacts$/);
  await expect(rail.getByRole('link', { name: 'Razgovori' })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await page.goto('/documents');
  const places = page.getByRole('navigation', { name: 'Mjesta' });
  await expect(places.getByRole('link')).toHaveText([
    'Omiljeno',
    'Bilješke',
    'Poveznice',
    'Ploče',
    'Sef',
    'Smeće',
  ]);
  await places.getByRole('link', { name: 'Bilješke' }).click();
  await expect(page).toHaveURL(/\/notes$/);
  await page.goto(address);

  await page.getByRole('button', { name: /^Račun / }).click();
  await page.getByRole('menuitem', { name: 'Postavke' }).click();
  await expect(page).toHaveURL(/\/settings$/);
  const settings = page.getByRole('navigation', { name: 'Postavke' });
  await settings.getByRole('link', { name: 'Lozinke aplikacija' }).click();
  await expect(page).toHaveURL(/\/settings\/app-passwords$/);
  await expect(settings).toBeHidden();
  await page.getByRole('link', { name: 'Zatvori' }).click();
  await expect(settings.getByRole('link', { name: 'Obavijesti' })).toBeVisible();
});

test('the page never scrolls, however long a pane in it grows', async ({ page }) => {
  await page.goto('/documents');
  const main = page.getByRole('main');
  await expect(main).toBeVisible();
  await main.evaluate((element) => {
    const long = document.createElement('div');
    long.style.height = '5000px';
    const hidden = document.createElement('span');
    hidden.className = 'sr-only';
    hidden.textContent = 'Nepročitano';
    long.append(hidden);
    element.append(long);
    long.prepend(Object.assign(document.createElement('div'), { style: 'height: 4990px' }));
  });
  await main.hover();
  await page.mouse.wheel(0, 20_000);
  await expect.poll(() => main.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBe(
    await page.evaluate(() => window.innerHeight),
  );
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test('the search box and the microphone stand in one place on every page, the page’s own actions before them', async ({
  page,
}) => {
  const address = await newDocument(page, 'Raspored stolova');
  const microphone = page.getByRole('button', { name: 'Izgovorite naredbu ili bilješku' });
  const search = page.getByRole('combobox', { name: 'Pretraži' });
  const places: { mic: number; box: number }[] = [];
  for (const to of ['/', address, '/chat', '/documents']) {
    await page.goto(to);
    await expect(microphone).toBeVisible();
    places.push({
      mic: (await microphone.boundingBox())!.x,
      box: (await search.boundingBox())!.x,
    });
  }
  expect(new Set(places.map((each) => each.mic)).size).toBe(1);
  expect(new Set(places.map((each) => each.box)).size).toBe(1);
  await page.goto('/search');
  await expect.poll(async () => (await microphone.boundingBox())!.x).toBe(places[0].mic);
});

test('the signature stands on one line at the foot of the side column and opens About, which writes to the author', async ({
  page,
}) => {
  const version = (await (await page.request.get('/api/version')).json()).version;
  const rail = page.getByRole('navigation', { name: 'Moduli' });
  const author = page.getByRole('button', { name: 'Ivo Bošković' });
  for (const to of ['/calendar', '/mail', '/chat', '/contacts', '/tasks', '/settings', '/']) {
    await page.goto(to);
    await expect(author).toBeVisible();
    await expect(rail.getByRole('button', { name: 'Ivo Bošković' })).toHaveCount(0);
  }
  const signature = author.locator('..');
  await expect(signature).toContainText(`v${version}`);
  await expect(signature).toContainText(`© ${new Date().getFullYear()}`);
  const box = (await signature.boundingBox())!;
  const within = (await rail.boundingBox())!;
  expect(box.height).toBeLessThan(30);
  expect(box.x).toBeGreaterThanOrEqual(within.x + within.width);
  expect(await signature.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(
    true,
  );
  await author.click();
  const about = page.getByRole('dialog', { name: 'O aplikaciji' });
  await expect(about).toContainText(version);
  const contact = about.getByRole('link', { name: 'ivo.boskovic.zg@gmail.com' });
  await expect(contact).toHaveAttribute('href', /^\/mail\?to=ivo.boskovic.zg%40gmail.com&/);
  await contact.click();
  await expect(about).toBeHidden();
  await expect(page).toHaveURL(/\/mail/);
});

test('a page that outlives its release takes the new one at the next page it goes to', async ({
  page,
}) => {
  let release = '1.0.0';
  let socket: WebSocketRoute | undefined;
  await page.routeWebSocket('**/api/live', (route) => {
    socket = route;
    const server = route.connectToServer();
    server.onMessage((text) => {
      const message = JSON.parse(String(text));
      route.send(JSON.stringify(message.type === 'state' ? { ...message, release } : message));
    });
  });
  await page.goto('/notes');
  await expect.poll(() => socket).toBeTruthy();
  const main = page.getByRole('navigation', { name: 'Moduli' });
  await main.getByRole('link', { name: 'Dokumenti' }).click();
  await expect(page).toHaveURL(/\/documents$/);

  let reloaded = false;
  page.once('load', () => {
    reloaded = true;
  });
  await page.waitForTimeout(500);
  expect(reloaded).toBe(false);

  release = '1.0.1';
  await socket!.close();
  await page.waitForTimeout(1500);
  expect(reloaded).toBe(false);
  await main.getByRole('link', { name: 'Pošta' }).click();
  await expect.poll(() => reloaded).toBe(true);
  await expect(page).toHaveURL(/\/mail/);
});
