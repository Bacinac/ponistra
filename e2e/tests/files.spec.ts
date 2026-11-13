import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { newDocument } from './helpers/nodes';

const CP1250: Record<string, number> = { Š: 0x8a, š: 0x9a, Ž: 0x8e, ž: 0x9e, Č: 0xc8, č: 0xe8 };

function cp1250(text: string): Buffer {
  return Buffer.from([...text].map((char) => CP1250[char] ?? char.charCodeAt(0)));
}

/** Half a second of a tone, as a WAV of 16-bit samples. */
function tone(): Buffer {
  const rate = 8000;
  const samples = Buffer.alloc(rate);
  for (let at = 0; at < rate / 2; at++) {
    samples.writeInt16LE(Math.round(8000 * Math.sin((2 * Math.PI * 440 * at) / rate)), at * 2);
  }
  const head = Buffer.alloc(44);
  head.write('RIFF', 0);
  head.writeUInt32LE(36 + samples.length, 4);
  head.write('WAVEfmt ', 8);
  head.writeUInt32LE(16, 16);
  head.writeUInt16LE(1, 20);
  head.writeUInt16LE(1, 22);
  head.writeUInt32LE(rate, 24);
  head.writeUInt32LE(rate * 2, 28);
  head.writeUInt16LE(2, 32);
  head.writeUInt16LE(16, 34);
  head.write('data', 36);
  head.writeUInt32LE(samples.length, 40);
  return Buffer.concat([head, samples]);
}

/** A short WebM the browser records from a canvas. */
async function recording(page: Page): Promise<Buffer> {
  const data = await page.evaluate(async () => {
    const canvas = document.createElement('canvas');
    canvas.width = 160;
    canvas.height = 120;
    const paint = canvas.getContext('2d')!;
    const recorder = new MediaRecorder(canvas.captureStream(25), { mimeType: 'video/webm' });
    const parts: Blob[] = [];
    recorder.ondataavailable = (event) => parts.push(event.data);
    const stopped = new Promise((done) => (recorder.onstop = done));
    recorder.start();
    for (let frame = 0; frame < 12; frame++) {
      paint.fillStyle = frame % 2 ? '#176b72' : '#7ca995';
      paint.fillRect(0, 0, 160, 120);
      await new Promise((done) => setTimeout(done, 40));
    }
    recorder.stop();
    await stopped;
    const bytes = new Uint8Array(await new Blob(parts).arrayBuffer());
    return btoa(String.fromCharCode(...bytes));
  });
  return Buffer.from(data, 'base64');
}

async function uploaded(page: Page, files: { name: string; mimeType: string; buffer: Buffer }[]) {
  await page.goto('/documents');
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Novo' }).click();
  await page.getByRole('menuitem', { name: 'Učitaj datoteke…' }).click();
  await (await chooser).setFiles(files);
}

async function opened(page: Page, title: string) {
  await page
    .getByRole('row', { name: new RegExp(title) })
    .getByText(title, { exact: true })
    .dblclick();
}

test('a text file shows as its text in the code page it is in, highlighted by its extension and searched in place', async ({
  page,
}) => {
  const settings = '{\n  "kalibracija": 0.02,\n  "naziv": "Žičana mreža"\n}\n';
  const list =
    'Šifra artikla;Naziv;Količina\r\nŽ-104;Žičana mreža, pocinčana;12\r\nČ-17;Čelična šipka;4\r\n';
  await uploaded(page, [
    { name: 'Postavke.json', mimeType: 'application/json', buffer: Buffer.from(settings) },
    { name: 'Agent.lss', mimeType: 'application/octet-stream', buffer: cp1250(list) },
  ]);
  await expect(page.getByRole('row', { name: /Postavke/ })).toContainText('JSON datoteka');
  await expect(page.getByRole('row', { name: /Agent/ })).toContainText('LSS datoteka');

  await opened(page, 'Postavke');
  const content = page.locator('.cm-content');
  await expect(content).toContainText('"naziv": "Žičana mreža"');
  await expect(page.getByText('UTF-8', { exact: true })).toBeVisible();
  // JSON's highlighting marks the property names apart from the strings.
  await expect(content.locator('span', { hasText: '"kalibracija"' })).toHaveCSS(
    'color',
    await page.evaluate(() => {
      const probe = document.createElement('span');
      probe.style.color = 'var(--code-name)';
      document.body.append(probe);
      const color = getComputedStyle(probe).color;
      probe.remove();
      return color;
    }),
  );
  await content.click();
  await page.keyboard.type('x');
  await expect(content).not.toContainText('x');
  await page.keyboard.press('Control+f');
  await page.getByRole('textbox', { name: 'Traži' }).pressSequentially('naziv');
  await expect(page.locator('.cm-searchMatch')).toHaveCount(1);

  await page.goBack();
  await opened(page, 'Agent');
  await expect(page.locator('.cm-content')).toContainText('Ž-104;Žičana mreža, pocinčana;12');
  await expect(page.getByText('Windows-1250', { exact: true })).toBeVisible();
});

test('audio and video play in the browser, and a recording it cannot play says so', async ({
  page,
}) => {
  await page.goto('/documents');
  const webm = await recording(page);
  await uploaded(page, [
    { name: 'Ton.wav', mimeType: 'audio/wav', buffer: tone() },
    { name: 'Snimka.webm', mimeType: 'video/webm', buffer: webm },
    {
      name: 'Pokvarena.webm',
      mimeType: 'video/webm',
      buffer: Buffer.concat([webm.subarray(0, 40), Buffer.alloc(400, 7)]),
    },
  ]);
  await expect(page.getByRole('row', { name: /Ton/ })).toContainText('WAV datoteka');

  await opened(page, 'Ton');
  const audio = page.locator('audio');
  await expect
    .poll(() => audio.evaluate((found: HTMLAudioElement) => found.duration))
    .toBeCloseTo(0.5, 1);

  await page.goBack();
  await opened(page, 'Snimka');
  await expect
    .poll(() => page.locator('video').evaluate((found: HTMLVideoElement) => found.videoWidth))
    .toBe(160);

  await page.goBack();
  await opened(page, 'Pokvarena');
  await expect(
    page.getByText('Preglednik ovaj zapis ne može reproducirati.', { exact: false }),
  ).toBeVisible();
  await expect(page.locator('video')).toHaveCount(0);
});

test('the preview beside the folder shows the chosen item: an image drawn small, the start of a text or a document, several counted', async ({
  page,
}) => {
  await page.goto(await newDocument(page, 'Ugovor o održavanju'));
  await page.locator('.ProseMirror').click();
  await page.keyboard.type('# Uvjeti isporuke');
  await page.keyboard.press('Enter');
  await page.keyboard.type('Rok je trideset dana.');
  await expect
    .poll(
      async () => {
        const response = await page.request.get('/api/search?q=trideset');
        return (await response.json()).documents.length;
      },
      { timeout: 20_000 },
    )
    .toBe(1);

  const drawn = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 120;
    canvas.height = 80;
    canvas.getContext('2d')!.fillRect(0, 0, 120, 80);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await uploaded(page, [
    { name: 'Strojarnica.png', mimeType: 'image/png', buffer: Buffer.from(drawn, 'base64') },
    {
      name: 'Kalibracija.json',
      mimeType: 'application/json',
      buffer: Buffer.from('{\n  "naziv": "Žičana mreža"\n}\n'),
    },
  ]);
  const row = (title: string) =>
    page.getByRole('row', { name: new RegExp(title) }).getByText(title, { exact: true });
  await expect(row('Kalibracija')).toBeVisible();

  const toggle = page.getByRole('button', { name: 'Pregled' });
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  const pane = page.getByRole('complementary', { name: 'Pregled' });
  await expect(pane).toContainText('Odaberite stavku za pregled.');

  await row('Strojarnica').click();
  const picture = pane.getByRole('img', { name: 'Strojarnica' });
  await expect
    .poll(() => picture.evaluate((image: HTMLImageElement) => image.naturalWidth))
    .toBe(120);
  await expect(pane).toContainText('PNG datoteka');

  await row('Kalibracija').click();
  await expect(pane.locator('.cm-content')).toContainText('"naziv": "Žičana mreža"');

  await row('Ugovor o održavanju').click();
  await expect(pane).toContainText('Uvjeti isporuke');
  await expect(pane).toContainText('Rok je trideset dana.');

  await row('Ugovor o održavanju').click({ modifiers: ['Control'] });
  await row('Strojarnica').click({ modifiers: ['Control'] });
  await expect(pane.getByRole('definition').first()).toHaveText('2');

  await page.reload();
  await expect(pane).toContainText('Odaberite stavku za pregled.');
  await toggle.click();
  await expect(pane).toHaveCount(0);
});
