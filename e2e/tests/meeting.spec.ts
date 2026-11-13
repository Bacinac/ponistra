import type { Browser, Locator, Page } from '@playwright/test';
import { randomBytes } from 'node:crypto';
import { expect, sessions, test } from './fixtures';

// Chromium's own camera and microphone: a moving picture and a tone, granted without asking.
const MEDIA = ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'];
// A desk of two screens side by side, the app's on the left.
const SCREENS = '--screen-info={0,0 1600x1000}{1600,0 1280x1024}';

test.use({
  permissions: ['camera', 'microphone'],
  launchOptions: { args: [...MEDIA, SCREENS] },
});

/** A device of its own signed in with the session: the same user's, a colleague's, or nobody's. */
async function device(
  browser: Browser,
  baseURL: string,
  problems: string[],
  session: string | null = sessions().own,
) {
  const context = await browser.newContext({
    baseURL,
    locale: 'hr-HR',
    permissions: ['camera', 'microphone'],
  });
  await context.addCookies([
    ...(session ? [{ name: 'sessionid', value: session, url: baseURL }] : []),
    { name: 'csrftoken', value: randomBytes(16).toString('hex'), url: baseURL },
  ]);
  context.on('page', (page) => {
    page.on('pageerror', (error) => problems.push(`${page.url()} ${error.message}`));
    page.on('console', (message) => {
      if (message.type() === 'error' || message.type() === 'warning') {
        problems.push(`${page.url()} ${message.type()}: ${message.text()}`);
      }
    });
  });
  return context.newPage();
}

/** The meeting's own window, which the click opens beside the app. */
async function beside(page: Page, click: () => Promise<void>): Promise<Page> {
  const [meeting] = await Promise.all([page.waitForEvent('popup'), click()]);
  return meeting;
}

/** Back from a meeting's own window, which closes, the app beside it where it was. */
async function back(meeting: Page) {
  const closed = meeting.waitForEvent('close');
  // The click closes the window, under load before Playwright has finished the click itself.
  await meeting
    .getByRole('button', { name: 'Natrag' })
    .click()
    .catch((error: unknown) => {
      if (!meeting.isClosed()) throw error;
    });
  await closed;
}

const meetingNow = (page: Page) =>
  beside(page, () => page.getByRole('button', { name: 'Sastanak sada' }).click());

const tiles = (page: Page) => page.getByRole('main').getByRole('group');

async function module(page: Page, name: string) {
  await page.goto('/');
  await page.getByRole('navigation', { name: 'Moduli' }).getByRole('link', { name }).click();
}

test('a meeting made now is joined from two devices that see each other, and left', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  await module(page, 'Razgovori');
  const meeting = await meetingNow(page);
  await expect(meeting).toHaveURL(/\/meet\/new$/);
  await expect(meeting.getByRole('heading', { name: 'Sastanak' })).toBeVisible();
  await expect(meeting.getByText('Nitko još nije u sastanku.')).toBeVisible();
  await expect(meeting.getByRole('button', { name: 'Isključi kameru' })).toBeEnabled();
  await meeting.getByRole('button', { name: 'Uređaji' }).click();
  await expect(meeting.getByRole('menuitem', { name: 'Kamera' })).toBeVisible();
  await meeting.keyboard.press('Escape');
  await meeting.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(tiles(meeting)).toHaveCount(1);
  await expect(meeting).toHaveURL(/\/meet\/[0-9a-f-]{36}$/);

  const there = await device(browser, baseURL!, problems);
  await there.goto(new URL(meeting.url()).pathname);
  await expect(there.getByText(/^U sastanku: /)).toBeVisible();
  await there.getByRole('button', { name: 'Pridruži se' }).click();
  for (const each of [meeting, there]) {
    await expect(tiles(each)).toHaveCount(2);
    const other = tiles(each).filter({ hasNotText: '(vi)' }).locator('video');
    await expect
      .poll(() => other.evaluate((video: HTMLVideoElement) => video.videoWidth))
      .toBeGreaterThan(0);
  }

  await there.getByRole('button', { name: 'Isključi mikrofon' }).click();
  await expect(
    tiles(meeting).filter({ hasNotText: '(vi)' }).getByLabel('Mikrofon je isključen'),
  ).toBeVisible();

  await there.getByRole('button', { name: 'Napusti' }).click();
  await expect(there.getByText('Napustili ste sastanak.')).toBeVisible();
  await expect(tiles(meeting)).toHaveCount(1);
  await there.context().close();

  await meeting.getByRole('button', { name: 'Napusti' }).click();
  await back(meeting);
  await expect(page).toHaveURL(/\/chat$/);
});

test('a meeting made now is made once it is used, and left before that leaves nothing', async ({
  page,
}) => {
  let made = 0;
  page.context().on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/meetings') made++;
  });
  await module(page, 'Razgovori');
  const tried = await meetingNow(page);
  await expect(tried.getByRole('button', { name: 'Isključi kameru' })).toBeEnabled();
  await back(tried);
  await expect(page).toHaveURL(/\/chat$/);
  expect(made).toBe(0);

  const meeting = await meetingNow(page);
  await meeting.getByRole('button', { name: 'Dodaj osobe' }).click();
  await expect(meeting.getByRole('dialog', { name: 'Dodaj osobe' })).toBeVisible();
  await expect(meeting).toHaveURL(/\/meet\/[0-9a-f-]{36}$/);
  await meeting
    .getByRole('dialog', { name: 'Dodaj osobe' })
    .getByRole('button', { name: 'Odustani' })
    .click();
  await meeting.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(tiles(meeting)).toHaveCount(1);
  expect(made).toBe(1);
});

test('a colleague rung into a meeting made now answers on the page they are on and is in', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const colleague = await device(browser, baseURL!, problems, sessions().colleague);
  await colleague.goto('/');
  const address = await colleague.evaluate(async () => {
    const { user } = await (await fetch('/api/auth/session')).json();
    return user.email as string;
  });

  await module(page, 'Razgovori');
  const meeting = await meetingNow(page);
  await meeting.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(tiles(meeting)).toHaveCount(1);
  await meeting.getByRole('button', { name: 'Dodaj osobe' }).click();
  const asking = meeting.getByRole('dialog', { name: 'Dodaj osobe' });
  await asking.getByLabel('Osobe').fill(address);
  await asking.getByLabel('Osobe').press('Enter');
  await asking.getByRole('button', { name: 'Pozovi' }).click();
  await expect(asking.getByRole('status')).toHaveText(`Zvoni: ${sessions().name}.`);
  await asking.getByRole('button', { name: 'Zatvori' }).click();
  const rings = meeting.getByRole('list', { name: 'Pozvane osobe' });
  await expect(rings).toHaveText(new RegExp(`${sessions().name}\\s*zvoni…`));

  const ring = colleague.getByRole('alertdialog');
  await expect(ring).toContainText('vas zove u sastanak');
  const answered = await beside(colleague, () =>
    ring.getByRole('button', { name: 'Pridruži se' }).click(),
  );
  await expect(answered).toHaveURL(new URL(meeting.url()).pathname);
  for (const each of [meeting, answered]) await expect(tiles(each)).toHaveCount(2);
  await expect(ring).toBeHidden();
  await expect(rings).toBeHidden();
  await colleague.context().close();
});

test('someone outside the installation comes by the link, is let in at the door and talks beside the call', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  await module(page, 'Razgovori');
  const meeting = await meetingNow(page);
  await meeting.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(tiles(meeting)).toHaveCount(1);
  await expect(meeting).toHaveURL(/\/meet\/[0-9a-f-]{36}$/);

  const guest = await device(browser, baseURL!, problems, null);
  await guest.goto(new URL(meeting.url()).pathname);
  await expect(guest.getByRole('heading', { name: 'Sastanak' })).toBeVisible();
  await expect(guest.getByRole('button', { name: 'Imate račun? Prijavite se' })).toBeVisible();
  const join = guest.getByRole('button', { name: 'Pridruži se' });
  await expect(join).toBeDisabled();
  await guest.getByLabel('Vaše ime').fill('Eva Kovač');
  await join.click();
  await expect(guest.getByRole('status')).toHaveText(
    'Čekate da vas netko iz sastanka pusti unutra.',
  );

  const door = meeting.getByRole('list', { name: 'Čekaju ulaz' });
  await expect(door).toContainText('Eva Kovač čeka ulaz');
  await door.getByRole('button', { name: 'Pusti' }).click();
  await expect(door).toBeHidden();
  for (const each of [meeting, guest]) await expect(tiles(each)).toHaveCount(2);
  await expect(tiles(meeting).filter({ hasText: 'Eva Kovač (gost)' })).toHaveCount(1);

  const said = `Dobar dan ${randomBytes(3).toString('hex')}`;
  const answer = `Hvala ${randomBytes(3).toString('hex')}`;
  await meeting.getByRole('button', { name: 'Poruke' }).click();
  const mine = meeting.getByRole('complementary', { name: 'Poruke' });
  await mine.getByLabel('Napišite poruku').fill(said);
  await mine.getByLabel('Napišite poruku').press('Enter');
  const messages = guest.getByRole('button', { name: /^Poruke/ });
  await expect(messages.getByLabel('Nepročitano')).toHaveText('1');
  await messages.click();
  const theirs = guest.getByRole('complementary', { name: 'Poruke' });
  await expect(theirs.getByRole('list', { name: 'Poruke' })).toContainText(said);
  await expect(messages.getByLabel('Nepročitano')).toBeHidden();
  await theirs.getByLabel('Napišite poruku').fill(answer);
  await theirs.getByRole('button', { name: 'Pošalji' }).click();
  const written = mine.getByRole('listitem').filter({ hasText: answer });
  await expect(written).toContainText('Eva Kovač (gost)');
  await guest.context().close();
});

test('the people in a meeting write to each other beside the call and keep the conversation', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  const said = `Dobar dan ${randomBytes(3).toString('hex')}`;
  const answer = `Stižem ${randomBytes(3).toString('hex')}`;
  await module(page, 'Razgovori');
  const meeting = await meetingNow(page);
  await meeting.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(tiles(meeting)).toHaveCount(1);

  const colleague = await device(browser, baseURL!, problems, sessions().colleague);
  await colleague.goto(new URL(meeting.url()).pathname);
  await colleague.getByRole('button', { name: 'Pridruži se' }).click();
  for (const each of [meeting, colleague]) await expect(tiles(each)).toHaveCount(2);

  await meeting.getByRole('button', { name: 'Poruke' }).click();
  const mine = meeting.getByRole('complementary', { name: 'Poruke' });
  await mine.getByLabel('Napišite poruku').fill(said);
  await mine.getByLabel('Napišite poruku').press('Enter');
  await expect(mine.getByRole('list', { name: 'Poruke' })).toContainText(said);
  await expect(mine.getByLabel('Napišite poruku')).toHaveValue('');

  const messages = colleague.getByRole('button', { name: /^Poruke/ });
  await expect(messages.getByLabel('Nepročitano')).toHaveText('1');
  await messages.click();
  const theirs = colleague.getByRole('complementary', { name: 'Poruke' });
  await expect(theirs.getByRole('list', { name: 'Poruke' })).toContainText(said);
  await theirs.getByLabel('Napišite poruku').fill(answer);
  await theirs.getByRole('button', { name: 'Pošalji' }).click();
  await expect(mine.getByRole('list', { name: 'Poruke' })).toContainText(answer);
  await expect(messages.getByLabel('Nepročitano')).toBeHidden();
  await colleague.context().close();

  await meeting.getByRole('button', { name: 'Napusti' }).click();
  await back(meeting);
  await expect(page).toHaveURL(/\/chat$/);
  const kept = page
    .getByRole('list', { name: 'Vaši razgovori' })
    .getByRole('link')
    .filter({ hasText: answer });
  await expect(kept).toContainText(sessions().name);
  await kept.click();
  await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}$/);
  const conversation = page.getByRole('list', { name: 'Poruke' });
  await expect(conversation).toContainText(said);
  await expect(conversation).toContainText(answer);
});

test('an event given a meeting of PONISTRA is joined from the calendar under its name', async ({
  page,
}) => {
  await module(page, 'Kalendar');
  await page.getByRole('button', { name: 'Postavke kalendara' }).click();
  await page.getByRole('button', { name: 'Novi kalendar' }).click();
  const made = page.getByRole('dialog', { name: 'Novi kalendar' });
  await made.getByLabel('Naziv', { exact: true }).fill('Sastanci');
  await made.getByRole('button', { name: 'Spremi' }).click();
  await expect(made).toBeHidden();
  await expect(page.getByRole('checkbox', { name: 'Sastanci' })).toBeChecked();

  await page.getByRole('button', { name: 'Novi događaj' }).first().click();
  const event = page.getByRole('dialog', { name: 'Novi događaj' });
  await event.getByLabel('Naziv', { exact: true }).fill('Kolegij');
  await event.getByLabel('Cijeli dan').check();
  await event.getByRole('button', { name: 'Dodaj sastanak u Ponistri' }).click();
  await expect(event.getByText('Sastanak u Ponistri', { exact: true })).toBeVisible();
  await event.getByRole('button', { name: 'Spremi' }).click();
  await expect(event).toBeHidden();

  await page.getByRole('button', { name: /Kolegij/ }).click();
  const edited = page.getByRole('dialog', { name: 'Uredi događaj' });
  const meeting = await beside(page, () =>
    edited.getByRole('link', { name: 'Pridruži se' }).click(),
  );
  await expect(meeting).toHaveURL(/\/meet\/[0-9a-f-]{36}$/);
  await expect(meeting.getByRole('heading', { name: 'Kolegij' })).toBeVisible();
  await expect(meeting).toHaveTitle('Kolegij – Ponistra');
  await back(meeting);
  await expect(edited).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(edited).toBeHidden();

  await page.getByRole('button', { name: /Kolegij/ }).click();
  await edited.getByRole('button', { name: 'Ukloni sastanak' }).click();
  await expect(edited.getByRole('button', { name: 'Dodaj sastanak u Ponistri' })).toBeVisible();
  await edited.getByRole('button', { name: 'Spremi' }).click();
  await expect(edited).toBeHidden();
  await page.getByRole('button', { name: /Kolegij/ }).click();
  await expect(edited.getByRole('link', { name: 'Pridruži se' })).toHaveCount(0);
});

test('a meeting the browser keeps from opening a window of its own opens here and says so', async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.open = () => null;
  });
  await module(page, 'Razgovori');
  await page.getByRole('button', { name: 'Sastanak sada' }).click();
  await expect(page).toHaveURL(/\/meet\/new$/);
  const told = page
    .getByRole('alert')
    .filter({ hasText: 'Preglednik nije dopustio zaseban prozor' });
  await expect(told).toBeVisible();
  await told.getByRole('button', { name: 'Zatvori' }).click();
  await expect(told).toBeHidden();
  await page.getByRole('button', { name: 'Natrag' }).click();
  await expect(page).toHaveURL(/\/chat$/);
});

test('a meeting opens filling the other screen than the app, and moves between them', async ({
  page,
  baseURL,
}) => {
  // What the browser asks the user once: to let the app place windows on its screens.
  const cdp = await page.context().newCDPSession(page);
  const { targetInfo } = await cdp.send('Target.getTargetInfo');
  await cdp.send('Browser.setPermission', {
    permission: { name: 'window-management' },
    setting: 'granted',
    origin: new URL(baseURL!).origin,
    browserContextId: targetInfo.browserContextId,
  });
  await module(page, 'Razgovori');
  const meeting = await meetingNow(page);
  await expect(meeting.getByRole('button', { name: 'Pridruži se' })).toBeVisible();
  const where = () => meeting.evaluate(() => [screenX, screenY, outerWidth, outerHeight]);
  await expect.poll(where).toEqual([1600, 0, 1280, 1024]);
  await meeting.getByRole('button', { name: 'Pridruži se' }).click();
  await expect(tiles(meeting)).toHaveCount(1);
  await meeting.getByRole('button', { name: 'Na drugi zaslon' }).click();
  await expect.poll(where).toEqual([0, 0, 1600, 1000]);
});

test('a meeting has a theme of its own in its window, the rest of Ponistra keeping its own', async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/chat');
  const kept = page.waitForResponse('**/api/auth/preferences');
  await page.getByRole('button', { name: /^Račun / }).click();
  await page.getByRole('menuitem', { name: 'Tema sastanaka' }).click();
  await page.getByRole('menuitemradio', { name: 'Tamna' }).press('Enter');
  await kept;
  await page.keyboard.press('Escape');
  await expect(page.locator('html')).not.toHaveAttribute('data-theme');
  const [meeting] = await Promise.all([
    page.waitForEvent('popup'),
    page.getByRole('button', { name: 'Sastanak sada' }).click(),
  ]);
  await expect(meeting.getByRole('button', { name: 'Isključi kameru' })).toBeEnabled();
  await expect(meeting.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('html')).not.toHaveAttribute('data-theme');
  await meeting.close();
});

/** The picture's mean colour, red, green and blue from 0 to 255. */
const meanColour = (video: Locator) =>
  video.evaluate((shown: HTMLVideoElement) => {
    const canvas = document.createElement('canvas');
    canvas.width = 32;
    canvas.height = 18;
    const context = canvas.getContext('2d', { willReadFrequently: true })!;
    context.drawImage(shown, 0, 0, 32, 18);
    const { data } = context.getImageData(0, 0, 32, 18);
    const sum = [0, 0, 0];
    for (let at = 0; at < data.length; at += 4) for (const c of [0, 1, 2]) sum[c] += data[at + c];
    return sum.map((each) => Math.round(each / (data.length / 4)));
  });

const lightWall = ([red, green, blue]: number[]) => red > 190 && green > 185 && blue > 170;

/** A red picture. */
const RED = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAF0lEQVR4nGP4z8BAEiJN9aiGUQ1DSgMAkPn/Afnh+ngAAAAASUVORK5CYII=',
  'base64',
);

// MediaPipe's own notes on stderr (its warnings and TensorFlow Lite's info) and Chromium's notes
// on its software GL driver; MediaPipe's errors still fail the test.
const VISION_NOTES =
  / (warning|error): (W\d{4} [\d:.]+ +\d+ \S+\] |INFO: Created TensorFlow Lite )|GL Driver Message \(OpenGL, Performance/;

// Before the problems are checked, and when a test failed too, so that its failure is its own.
test.afterEach(({ problems }) => {
  problems.splice(0, problems.length, ...problems.filter((each) => !VISION_NOTES.test(each)));
});

async function chosen(meeting: Page, sub: string, item: string) {
  await meeting.getByRole('button', { name: 'Uređaji' }).click();
  await meeting.getByRole('menuitem', { name: sub }).press('Enter');
  const kept = meeting.waitForResponse('**/api/auth/preferences');
  await meeting.getByRole('menuitemradio', { name: item }).press('Enter');
  await kept;
}

test('the camera’s background, framing and light and the sound’s processing are chosen beside the devices and kept by the account', async ({
  page,
  browser,
  baseURL,
  problems,
}) => {
  test.slow();
  await module(page, 'Razgovori');
  const meeting = await meetingNow(page);
  await expect(meeting.getByRole('button', { name: 'Isključi kameru' })).toBeEnabled();
  const preview = meeting.locator('video');
  await expect
    .poll(() => preview.evaluate((v: HTMLVideoElement) => v.videoWidth))
    .toBeGreaterThan(0);
  expect(lightWall(await meanColour(preview))).toBe(false);

  // Chromium's own camera shows no person, so the whole picture is background.
  await chosen(meeting, 'Pozadina', 'Svijetli zid');
  await expect
    .poll(async () => lightWall(await meanColour(preview)), { timeout: 30_000 })
    .toBe(true);

  await meeting.getByRole('button', { name: 'Uređaji' }).click();
  let kept = meeting.waitForResponse('**/api/auth/preferences');
  await meeting.getByRole('menuitemcheckbox', { name: 'Prati lice' }).press('Enter');
  await kept;
  await meeting.getByRole('button', { name: 'Uređaji' }).click();
  kept = meeting.waitForResponse('**/api/auth/preferences');
  await meeting
    .getByRole('menuitemcheckbox', { name: 'Popravi slabo osvjetljenje' })
    .press('Enter');
  await kept;
  await meeting.getByRole('button', { name: 'Uređaji' }).click();
  await meeting.getByRole('menuitem', { name: 'Zvuk' }).press('Enter');
  kept = meeting.waitForResponse('**/api/auth/preferences');
  await meeting.getByRole('menuitemcheckbox', { name: 'Prigušivanje šuma' }).press('Enter');
  await kept;
  await expect(meeting.getByRole('alert')).toHaveCount(0);

  await meeting.getByRole('button', { name: 'Pridruži se' }).click();
  // Every processing on at once keeps the page's thread busy without a graphics card.
  await expect(tiles(meeting)).toHaveCount(1, { timeout: 30_000 });
  const there = await device(browser, baseURL!, problems, sessions().colleague);
  await there.goto(new URL(meeting.url()).pathname);
  await there.getByRole('button', { name: 'Pridruži se' }).click();
  const seen = tiles(there).filter({ hasNotText: '(vi)' }).locator('video');
  await expect.poll(async () => lightWall(await meanColour(seen)), { timeout: 30_000 }).toBe(true);
  await there.context().close();
  await meeting.getByRole('button', { name: 'Napusti' }).click();
  await expect(meeting.getByText('Napustili ste sastanak.')).toBeVisible();
  await meeting.close();

  // Another device of the same account finds the same choices.
  const app = await device(browser, baseURL!, problems);
  await module(app, 'Razgovori');
  const other = await meetingNow(app);
  await expect(other.getByRole('button', { name: 'Isključi kameru' })).toBeEnabled();
  await other.getByRole('button', { name: 'Uređaji' }).click();
  await expect(other.getByRole('menuitemcheckbox', { name: 'Prati lice' })).toHaveAttribute(
    'aria-checked',
    'true',
  );
  await other.getByRole('menuitem', { name: 'Pozadina' }).press('Enter');
  await expect(other.getByRole('menuitemradio', { name: 'Svijetli zid' })).toHaveAttribute(
    'aria-checked',
    'true',
  );

  // The test's Chromium draws without a graphics card, too slowly for every processing at once.
  kept = other.waitForResponse('**/api/auth/preferences');
  await other.getByRole('menuitemcheckbox', { name: 'Prati lice' }).press('Enter');
  await kept;
  await other.getByRole('button', { name: 'Uređaji' }).click();
  kept = other.waitForResponse('**/api/auth/preferences');
  await other.getByRole('menuitemcheckbox', { name: 'Popravi slabo osvjetljenje' }).press('Enter');
  await kept;
  await other.getByRole('button', { name: 'Uređaji' }).click();
  await other.getByRole('menuitem', { name: 'Pozadina' }).press('Enter');

  // A picture of one's own takes the background's place, and leaves with it.
  const picked = other.waitForEvent('filechooser');
  await other.getByRole('menuitem', { name: 'Učitaj vlastitu sliku…' }).press('Enter');
  await (await picked).setFiles({ name: 'crveno.png', mimeType: 'image/png', buffer: RED });
  const own = other.locator('video');
  await expect
    .poll(
      async () => {
        const [red, green, blue] = await meanColour(own);
        return red > 180 && green < 80 && blue < 80;
      },
      { timeout: 30_000 },
    )
    .toBe(true);
  await other.getByRole('button', { name: 'Uređaji' }).click();
  await other.getByRole('menuitem', { name: 'Pozadina' }).press('Enter');
  await expect(other.getByRole('menuitemradio', { name: 'Vlastita slika' })).toHaveAttribute(
    'aria-checked',
    'true',
  );
  const removed = other.waitForResponse('**/api/auth/backdrop');
  await other.getByRole('menuitem', { name: 'Ukloni vlastitu sliku' }).press('Enter');
  await removed;
  await expect.poll(async () => lightWall(await meanColour(own))).toBe(false);
  await app.context().close();
});
