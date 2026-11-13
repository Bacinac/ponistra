import type { Page } from '@playwright/test';

/** Chromium tells the page of a selection made by keys in a later task than the next key, so a
 * shortcut pressed at once would act on the selection before it; no person is that quick. */
export async function selectBack(page: Page, text: string): Promise<void> {
  const heard = await page.evaluateHandle(
    (wanted) => ({
      done: new Promise<void>((resolve) => {
        document.addEventListener('selectionchange', function check() {
          if (getSelection()?.toString() !== wanted) return;
          document.removeEventListener('selectionchange', check);
          setTimeout(resolve);
        });
      }),
    }),
    text,
  );
  for (const _ of text) await page.keyboard.press('Shift+ArrowLeft');
  await heard.evaluate((found) => found.done);
}

/** ProseMirror, given the focus back, puts its own selection back 20 ms later over one the
 * browser made meanwhile that it has not heard of yet, so a key pressed before then, as a loaded
 * check machine presses it, is undone. A timer set now runs after ProseMirror's. */
export async function settled(page: Page): Promise<void> {
  await page.evaluate(() => new Promise((resolve) => setTimeout(resolve, 20)));
}
