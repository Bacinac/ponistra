import { type Locator, type Page, test } from '@playwright/test';
import { writeFileSync } from 'node:fs';

const LANGUAGES = ['hr', 'en'] as const;
const SCHEMES = ['light', 'dark'] as const;
const started = process.env.PONISTRA_SHOTS;

/** A PNG as WebP, through the browser's own encoder: nothing to install in the image. */
async function webp(page: Page, png: Buffer): Promise<Buffer> {
  const url = await page.evaluate(async (data) => {
    const bytes = Uint8Array.from(atob(data), (each) => each.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([bytes], { type: 'image/png' }));
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0);
    return canvas.toDataURL('image/webp', 0.9);
  }, png.toString('base64'));
  return Buffer.from(url.split(',')[1], 'base64');
}

/** A picture of the help (help/README.md), in each language and scheme, of the account help_seed
    filled in that language. What `make` returns is what is taken; the whole window if nothing. */
export function shot(name: string, make: (page: Page) => Promise<Locator | void>): void {
  for (const language of LANGUAGES) {
    for (const scheme of SCHEMES) {
      test(`${name} ${language} ${scheme}`, async ({ browser, baseURL }) => {
        if (!started) throw new Error('PONISTRA_SHOTS is not set; scripts/check.sh starts them');
        const context = await browser.newContext({
          baseURL,
          colorScheme: scheme,
          locale: language === 'hr' ? 'hr-HR' : 'en-GB',
          viewport: { width: 1280, height: 800 },
        });
        const sessions: Record<string, string> = JSON.parse(started);
        await context.addCookies([{ name: 'sessionid', value: sessions[language], url: baseURL! }]);
        const page = await context.newPage();
        const part = await make(page);
        await page.waitForLoadState('networkidle');
        const png = await (part ?? page).screenshot({ animations: 'disabled', type: 'png' });
        writeFileSync(`/shots/${name}.${language}.${scheme}.webp`, await webp(page, png));
        await context.close();
      });
    }
  }
}
