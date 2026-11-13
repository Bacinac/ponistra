import { expect, sessions, test } from './fixtures';
import { newDocument } from './helpers/nodes';

test('system theme updates the whole interface with readable colours', async ({
  page,
  context,
}) => {
  await context.clearCookies();
  await page.goto('/');
  await expect(page).toHaveTitle('Ponistra');
  for (const colorScheme of ['light', 'dark', 'light'] as const) {
    await page.emulateMedia({ colorScheme });
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.content ===
            getComputedStyle(document.documentElement).backgroundColor,
        ),
      )
      .toBe(true);
    const logo = page.getByRole('img', { name: 'Ponistra', exact: true });
    await expect
      .poll(() =>
        logo.evaluate((image) => (image as HTMLImageElement).currentSrc.includes('logo-inverse')),
      )
      .toBe(colorScheme === 'dark');
    const contrast = await page.evaluate(() => {
      const probe = document.createElement('span');
      document.body.append(probe);
      const luminance = (value: string) => {
        probe.style.color = value;
        const rgb = getComputedStyle(probe)
          .color.match(/[\d.]+/g)!
          .slice(0, 3)
          .map(Number);
        return rgb
          .map((value) => {
            const c = value / 255;
            return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
          })
          .reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
      };
      const ratio = (a: string, b: string) => {
        const values = [luminance(a), luminance(b)];
        return (Math.max(...values) + 0.05) / (Math.min(...values) + 0.05);
      };
      const pairs: [string, string, number][] = [];
      for (const background of ['surface', 'panel', 'raised', 'hover', 'selected']) {
        for (const foreground of [
          'ink',
          'muted',
          'accent',
          'danger',
          'inserted',
          'deleted',
          'ai',
        ]) {
          pairs.push([foreground, background, 4.5]);
        }
        pairs.push(['focus', background, 3]);
      }
      for (const background of ['surface', 'panel', 'raised'])
        pairs.push(['control', background, 3]);
      for (const background of ['surface', 'panel', 'raised', 'hover', 'selected']) {
        for (let account = 1; account <= 7; account++)
          pairs.push([`account-${account}`, background, 3]);
      }
      pairs.push(
        ['on-accent', 'accent', 4.5],
        ['on-accent', 'accent-hover', 4.5],
        ['on-danger', 'danger', 4.5],
        ['ai', 'ai-soft', 4.5],
      );
      const failures = pairs.flatMap(([a, b, minimum]) => {
        const actual = ratio(`var(--${a})`, `var(--${b})`);
        return actual < minimum ? [{ a, b, actual, minimum }] : [];
      });
      for (const color of getComputedStyle(document.documentElement)
        .getPropertyValue('--presence-colors')
        .split(',')) {
        const actual = ratio('var(--on-presence)', color);
        if (actual < 4.5) failures.push({ a: 'presence label', b: color, actual, minimum: 4.5 });
      }
      probe.remove();
      return failures;
    });
    expect(contrast, colorScheme).toEqual([]);
    const email = page.getByRole('textbox', { name: 'E-pošta' });
    await email.focus();
    await expect(email).toHaveCSS('outline-style', 'solid');
    await expect(email).toHaveCSS('outline-width', '2px');
  }
});

test('a chosen theme holds against the system and is remembered', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto('/');
  const background = () =>
    page.evaluate(() => getComputedStyle(document.documentElement).backgroundColor);
  const themeColor = () =>
    page.evaluate(
      () => document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.content,
    );
  // The pointer jumps straight from the trigger onto the item, which Radix reads as leaving the
  // submenu and closes it under the click; a key does what a steady hand would.
  const choose = async (name: string) => {
    await page.getByRole('button', { name: /^Račun / }).click();
    await page.getByRole('menuitem', { name: 'Tema', exact: true }).click();
    const kept = page.waitForResponse('**/api/auth/preferences');
    await page.getByRole('menuitemradio', { name }).press('Enter');
    await kept;
  };
  await expect.poll(themeColor).toBe(await background());
  const dark = await background();

  await choose('Svijetla');
  await expect.poll(background).not.toBe(dark);
  const light = await background();
  await expect.poll(themeColor).toBe(light);
  await page.reload();
  await expect(page.getByRole('navigation', { name: 'Moduli' })).toBeVisible();
  expect(await background()).toBe(light);
  await page.emulateMedia({ colorScheme: 'light' });
  await page.emulateMedia({ colorScheme: 'dark' });
  expect(await background()).toBe(light);

  await choose('Kao sustav');
  await expect.poll(background).toBe(dark);
  await expect.poll(themeColor).toBe(dark);
});

test('the theme and language chosen go with the account to a browser that never saw them', async ({
  page,
  browser,
  baseURL,
}) => {
  await page.goto('/');
  const choose = async (menu: string, name: string) => {
    const kept = page.waitForResponse('**/api/auth/preferences');
    await page.getByRole('button', { name: /^(Račun|Account) / }).click();
    await page.getByRole('menuitem', { name: menu, exact: true }).click();
    await page.getByRole('menuitemradio', { name }).press('Enter');
    await kept;
  };
  await choose('Tema', 'Tamna');
  await choose('Jezik', 'English');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  const elsewhere = await browser.newContext();
  await elsewhere.addCookies([{ name: 'sessionid', value: sessions().own, url: baseURL! }]);
  const other = await elsewhere.newPage();
  await other.goto('/');
  await expect(other.locator('html')).toHaveAttribute('lang', 'en');
  await expect(other.locator('html')).toHaveAttribute('data-theme', 'dark');

  await other.reload();
  await expect(other.getByRole('navigation', { name: 'Modules' })).toBeVisible();
  await choose('Theme', 'Light');
  await expect(other.locator('html')).toHaveAttribute('data-theme', 'light');
  await elsewhere.close();
});

test('menus, dialogs and editor keep the active theme', async ({ page }) => {
  await page.goto(await newDocument(page, 'Provjera teme'));
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.keyboard.type('Petrolej i kadulja');
  for (const colorScheme of ['light', 'dark'] as const) {
    await page.emulateMedia({ colorScheme });
    await editor.click();
    await page.keyboard.press('Control+b');
    await expect(page.getByRole('button', { name: 'Podebljano', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await page.keyboard.press('Control+b');
    await page.locator('header button[aria-current="page"]').click();
    await page.getByRole('menuitem', { name: 'Tema i stilovi…' }).click();
    const dialog = page.getByRole('dialog', { name: 'Tema i stilovi' });
    await expect(dialog).toBeVisible();
    expect(
      await dialog.evaluate((element) => {
        const actual = getComputedStyle(element).backgroundColor;
        const probe = document.createElement('div');
        probe.style.backgroundColor = 'var(--raised)';
        document.body.append(probe);
        const expected = getComputedStyle(probe).backgroundColor;
        probe.remove();
        return actual === expected;
      }),
    ).toBe(true);
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
  }
});

test('browser icons are transparent and fill their available width', async ({ page }) => {
  await page.goto('/');
  const icons = await page.evaluate(async () => {
    const inspect = async (blob: Blob, size: number) => {
      const url = URL.createObjectURL(blob);
      const image = new Image();
      image.src = url;
      await image.decode();
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = size;
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(image, 0, 0, size, size);
      URL.revokeObjectURL(url);
      const pixels = ctx.getImageData(0, 0, size, size).data;
      const corners = [0, size - 1, size * (size - 1), size * size - 1].map(
        (index) => pixels[index * 4 + 3],
      );
      let left = size;
      let right = -1;
      for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
          if (pixels[(y * size + x) * 4 + 3] > 32) {
            left = Math.min(left, x);
            right = Math.max(right, x);
          }
        }
      }
      return { size, corners, coverage: (right - left + 1) / size };
    };
    const svg = document.querySelector<HTMLLinkElement>('link[rel="icon"][type="image/svg+xml"]')!;
    const results = [await inspect(await (await fetch(svg.href)).blob(), 32)];
    const ico = document.querySelector<HTMLLinkElement>('link[rel="icon"]:not([type])')!;
    const buffer = await (await fetch(ico.href)).arrayBuffer();
    const header = new DataView(buffer);
    for (let index = 0; index < header.getUint16(4, true); index++) {
      const entry = 6 + index * 16;
      const size = header.getUint8(entry) || 256;
      const length = header.getUint32(entry + 8, true);
      const offset = header.getUint32(entry + 12, true);
      results.push(
        await inspect(
          new Blob([buffer.slice(offset, offset + length)], { type: 'image/png' }),
          size,
        ),
      );
    }
    return results;
  });
  expect(icons).toHaveLength(5);
  for (const icon of icons) {
    expect(icon.corners).toEqual([0, 0, 0, 0]);
    expect(icon.coverage, `${icon.size}px`).toBeGreaterThanOrEqual(0.9);
  }
});
