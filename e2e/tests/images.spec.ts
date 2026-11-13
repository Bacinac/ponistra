import type { Locator, Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';

/** Red on the left half, blue on the right, as a PNG. */
async function halves(page: Page): Promise<Buffer> {
  const data = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 100;
    const paint = canvas.getContext('2d')!;
    paint.fillStyle = 'rgb(200 60 40)';
    paint.fillRect(0, 0, 100, 100);
    paint.fillStyle = 'rgb(40 120 200)';
    paint.fillRect(100, 0, 100, 100);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  return Buffer.from(data, 'base64');
}

/** The colours of the image the address gives at the points, as the browser reads it. */
function colours(page: Page, address: string, points: [number, number][]) {
  return page.evaluate(
    async ({ address, points }) => {
      const response = await fetch(address);
      if (!response.ok) return null;
      const bitmap = await createImageBitmap(await response.blob());
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
      const paint = canvas.getContext('2d')!;
      paint.drawImage(bitmap, 0, 0);
      const whole = paint.getImageData(0, 0, bitmap.width, bitmap.height).data;
      return {
        size: [bitmap.width, bitmap.height],
        pixels: points.map(([x, y]) => {
          const at = (y * bitmap.width + x) * 4;
          return [...whole.slice(at, at + 3)];
        }),
      };
    },
    { address, points },
  );
}

function near(found: number[], expected: number[]) {
  return found.every((value, at) => Math.abs(value - expected[at]) <= 2);
}

test('an image is cropped, turned and toned in the browser, and its copy and picture come out as it shows', async ({
  page,
}) => {
  const buffer = await halves(page);
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: 'Hala.png', mimeType: 'image/png', buffer });
  await page.getByRole('row', { name: /Hala/ }).getByText('Hala', { exact: true }).dblclick();
  const download = page.getByRole('link', { name: 'Preuzmi' });
  const id = (await download.getAttribute('href'))!.split('/')[3];

  const shown = page.getByRole('img', { name: 'Hala' });
  const size = () => shown.evaluate((canvas: HTMLCanvasElement) => [canvas.width, canvas.height]);
  await expect.poll(size).toEqual([200, 100]);
  await page.getByRole('button', { name: 'Uredi' }).click();
  const panel = page.getByRole('complementary', { name: 'Uređivanje slike' });

  await panel.getByRole('button', { name: 'Okreni udesno' }).click();
  await expect.poll(size).toEqual([100, 200]);
  await panel.getByRole('button', { name: 'Obreži' }).click();
  await panel.getByRole('radio', { name: '1:1' }).click();
  await expect(page.getByRole('group', { name: 'Obrezivanje' })).toBeVisible();
  await panel.getByRole('button', { name: 'Obreži' }).click();
  await expect.poll(size).toEqual([100, 100]);

  for (const [label, value] of [
    ['Svjetlina', '1.2'],
    ['Kontrast', '1.5'],
    ['Zasićenost', '0.5'],
  ]) {
    const slider = panel.getByRole('slider', { name: label });
    await slider.fill(value);
    await slider.blur();
  }
  await expect(panel).toContainText('Kopija: 100 × 100 px');

  const points: [number, number][] = [
    [50, 20],
    [50, 80],
  ];
  const drawn = await shown.evaluate((canvas: HTMLCanvasElement, points) => {
    const { data } = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height);
    return points.map(([x, y]) => {
      const at = (y * canvas.width + x) * 4;
      return [...data.slice(at, at + 3)];
    });
  }, points);
  expect(drawn[0][0]).toBeGreaterThan(drawn[0][2]);
  expect(drawn[1][2]).toBeGreaterThan(drawn[1][0]);
  await expect
    .poll(async () => {
      const copy = await colours(page, `/api/nodes/${id}/edited`, points);
      return (
        copy !== null &&
        copy.size.join() === '100,100' &&
        copy.pixels.every((pixel, at) => near(pixel, drawn[at]))
      );
    })
    .toBe(true);
  await expect(download).toHaveAttribute('href', `/api/nodes/${id}/edited?download=1`);

  const saturation = panel.getByRole('slider', { name: 'Zasićenost' });
  await page.keyboard.press('Control+z');
  await expect(saturation).toHaveValue('1');
  await page.keyboard.press('Control+y');
  await expect(saturation).toHaveValue('0.5');

  await expect
    .poll(async () => (await colours(page, `/api/nodes/${id}/picture`, []))?.size.join(), {
      timeout: 20_000,
    })
    .toBe('100,100');
  await page.goto('/documents');
  await page.getByRole('button', { name: 'Pregled' }).click();
  await page.getByRole('row', { name: /Hala/ }).getByText('Hala', { exact: true }).click();
  const picture = page.getByRole('complementary', { name: 'Pregled' }).getByRole('img', {
    name: 'Hala',
  });
  await expect
    .poll(() =>
      picture.evaluate((image: HTMLImageElement) => [image.naturalWidth, image.naturalHeight]),
    )
    .toEqual([100, 100]);
});

/** A pixel of the canvas, read from a copy of it: reading the canvas itself more than once makes
 * Chrome warn. */
function pixelOf(canvas: Locator, x: number, y: number) {
  return canvas.evaluate(
    (shown: HTMLCanvasElement, [x, y]) => {
      const copy = new OffscreenCanvas(shown.width, shown.height).getContext('2d')!;
      copy.drawImage(shown, 0, 0);
      return [...copy.getImageData(x, y, 1, 1).data.slice(0, 3)];
    },
    [x, y],
  );
}

/** How far the canvas and the image the address gives part, pixel by pixel. */
function apart(canvas: Locator, address: string) {
  return canvas.evaluate(async (shown: HTMLCanvasElement, address) => {
    const response = await fetch(address);
    if (!response.ok) return null;
    const bitmap = await createImageBitmap(await response.blob());
    if (bitmap.width !== shown.width || bitmap.height !== shown.height) return null;
    const copy = new OffscreenCanvas(bitmap.width, bitmap.height).getContext('2d')!;
    copy.drawImage(bitmap, 0, 0);
    const theirs = copy.getImageData(0, 0, bitmap.width, bitmap.height).data;
    const own = new OffscreenCanvas(shown.width, shown.height).getContext('2d')!;
    own.drawImage(shown, 0, 0);
    const ours = own.getImageData(0, 0, shown.width, shown.height).data;
    let far = 0;
    let total = 0;
    for (let at = 0; at < ours.length; at += 4) {
      const most = Math.max(
        ...[0, 1, 2].map((channel) => Math.abs(ours[at + channel] - theirs[at + channel])),
      );
      total += most;
      if (most > 16) far += 1;
    }
    const pixels = ours.length / 4;
    return { mean: total / pixels, far: far / pixels };
  }, address);
}

test('marks drawn on an image show in its copy, are taken back and saved as a new image', async ({
  page,
}) => {
  const buffer = await halves(page);
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles({ name: 'Oznake.png', mimeType: 'image/png', buffer });
  await page
    .getByRole('row', { name: /Oznake/ })
    .getByText('Oznake', { exact: true })
    .dblclick();
  const id = (await page.getByRole('link', { name: 'Preuzmi' }).getAttribute('href'))!.split(
    '/',
  )[3];
  const shown = page.getByRole('img', { name: 'Oznake' });
  await expect
    .poll(() => shown.evaluate((canvas: HTMLCanvasElement) => [canvas.width, canvas.height]))
    .toEqual([200, 100]);
  await page.getByRole('button', { name: 'Uredi' }).click();
  const panel = page.getByRole('complementary', { name: 'Uređivanje slike' });
  const drag = async (from: [number, number], to: [number, number]) => {
    const box = (await shown.boundingBox())!;
    await page.mouse.move(box.x + from[0], box.y + from[1]);
    await page.mouse.down();
    await page.mouse.move(box.x + to[0], box.y + to[1], { steps: 5 });
    await page.mouse.up();
  };
  const pixel = (x: number, y: number) => pixelOf(shown, x, y);

  await panel.getByRole('button', { name: 'Pravokutnik' }).click();
  await drag([20, 20], [80, 60]);
  await expect.poll(() => pixel(20, 40)).toEqual([0xc4, 0x32, 0x1c]);
  await panel.getByRole('button', { name: 'Zamućenje' }).click();
  await drag([90, 70], [130, 95]);
  await panel.getByRole('button', { name: 'Tekst' }).click();
  const box = (await shown.boundingBox())!;
  await page.mouse.click(box.x + 110, box.y + 40);
  const text = page.getByRole('textbox', { name: 'Tekst' });
  await text.fill('Hala');
  await text.press('Enter');
  await expect(text).toBeHidden();
  await expect
    .poll(async () => {
      const [red, , blue] = await pixel(100, 85);
      return red < 200 && red > 40 && blue < 200 && blue > 40;
    })
    .toBe(true);

  await expect
    .poll(async () => {
      const found = await apart(shown, `/api/nodes/${id}/edited`);
      return found && found.mean < 1.5 && found.far < 0.01 ? 'near' : JSON.stringify(found);
    })
    .toBe('near');
  const [mixed] = (await colours(page, `/api/nodes/${id}/edited`, [[100, 85]]))!.pixels;
  expect(mixed[0]).toBeGreaterThan(40);
  expect(mixed[0]).toBeLessThan(200);
  expect(mixed[2]).toBeGreaterThan(40);
  expect(mixed[2]).toBeLessThan(200);

  await page.keyboard.press('Escape');
  await expect(panel.getByRole('button', { name: 'Tekst' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await page.getByRole('button', { name: 'Pravokutnik' }).and(page.locator('[data-mark]')).click();
  await page
    .getByRole('toolbar', { name: 'Odabrana oznaka' })
    .getByRole('button', { name: 'Ukloni' })
    .click();
  await expect.poll(() => pixel(20, 40)).toEqual([200, 60, 40]);
  await page.keyboard.press('Control+z');
  await expect.poll(() => pixel(20, 40)).toEqual([0xc4, 0x32, 0x1c]);

  await panel.getByRole('button', { name: 'Spremi kao novu sliku…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Spremi kao novu sliku' });
  await expect(dialog.getByRole('textbox')).toHaveValue('Oznake (uređeno)');
  await dialog.getByRole('button', { name: 'Izradi' }).click();
  await expect(page).not.toHaveURL(new RegExp(id));
  const saved = page.getByRole('img', { name: 'Oznake (uređeno)' });
  await expect.poll(() => pixelOf(saved, 20, 40)).toEqual([0xc4, 0x32, 0x1c]);
});

test('an image in a document is edited into one of its own, which the document then shows', async ({
  page,
}) => {
  const buffer = await halves(page);
  await page.goto(await newDocument(page, 'Izvještaj sa slikom'));
  const editor = page.locator('.ProseMirror');
  await editor.click();
  await page.getByRole('button', { name: 'Umetni' }).click();
  await page.getByRole('menuitem', { name: 'Slika' }).click();
  const chooser = page.waitForEvent('filechooser');
  await page
    .getByRole('dialog', { name: 'Umetni sliku' })
    .getByRole('button', { name: 'S računala…' })
    .click();
  await (await chooser).setFiles({ name: 'Hala.png', mimeType: 'image/png', buffer });
  const img = editor.locator('figure[data-image] img');
  await expect.poll(() => img.evaluate((found: HTMLImageElement) => found.naturalWidth)).toBe(200);
  const before = (await img.getAttribute('src'))!;

  await img.click({ button: 'right' });
  await page.getByRole('menuitem', { name: 'Uredi sliku…' }).click();
  const dialog = page.getByRole('dialog', { name: 'Uređivanje slike' });
  const panel = dialog.getByRole('complementary', { name: 'Uređivanje slike' });
  const shown = dialog.getByRole('img', { name: 'Slika' });
  await expect
    .poll(() => shown.evaluate((canvas: HTMLCanvasElement) => [canvas.width, canvas.height]))
    .toEqual([200, 100]);
  await panel.getByRole('button', { name: 'Okreni udesno' }).click();
  await expect
    .poll(() => shown.evaluate((canvas: HTMLCanvasElement) => [canvas.width, canvas.height]))
    .toEqual([100, 200]);
  await panel.getByRole('button', { name: 'Pravokutnik' }).click();
  const box = (await shown.boundingBox())!;
  await page.mouse.move(box.x + 10, box.y + 110);
  await page.mouse.down();
  await page.mouse.move(box.x + 90, box.y + 190, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => pixelOf(shown, 10, 150)).toEqual([0xc4, 0x32, 0x1c]);

  await page.keyboard.press('Escape');
  await page.keyboard.press('Escape');
  await expect(dialog).toBeVisible();
  await panel.getByRole('button', { name: 'Primijeni' }).click();
  await expect(dialog).toBeHidden();

  await expect(img).not.toHaveAttribute('src', before);
  const after = (await img.getAttribute('src'))!;
  const drawn = await colours(page, after, [
    [50, 20],
    [50, 180],
    [10, 150],
  ]);
  expect(drawn!.size).toEqual([100, 200]);
  const [top, bottom, mark] = drawn!.pixels;
  expect(near(top, [200, 60, 40]), `top ${top}`).toBe(true);
  expect(near(bottom, [40, 120, 200]), `bottom ${bottom}`).toBe(true);
  expect(near(mark, [0xc4, 0x32, 0x1c]), `mark ${mark}`).toBe(true);
  expect((await colours(page, before, [[0, 0]]))!.size).toEqual([200, 100]);

  await editor.press('Control+z');
  await expect(img).toHaveAttribute('src', before);
});
