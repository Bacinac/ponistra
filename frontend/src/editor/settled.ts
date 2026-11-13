import type { RefObject } from 'react';

/** How long a layout must stay as it is before it counts as laid out. */
const SETTLE = 300;

const frames = (count: number) =>
  new Promise<void>((done) => {
    const next = (left: number) => (left ? requestAnimationFrame(() => next(left - 1)) : done());
    next(count);
  });

const held = new Set<Promise<unknown>>();

/** Keeps the page from counting as laid out until `waited` ends, as an image's loading does. */
export function hold(waited: Promise<unknown>): void {
  const kept: Promise<unknown> = waited.catch(() => {}).finally(() => held.delete(kept));
  held.add(kept);
}

/** Whether the page laid itself out, with its fonts and images in, `changes` counting what it
 * laid out again, before it was `gone`. */
export async function settled(changes: RefObject<number>, gone: () => boolean): Promise<boolean> {
  for (;;) {
    const seen = changes.current;
    await document.fonts.ready;
    await Promise.all([...document.images].map((image) => image.decode().catch(() => {})));
    await Promise.all(held);
    await frames(2);
    await new Promise((done) => setTimeout(done, SETTLE));
    if (gone()) return false;
    if (changes.current === seen) return true;
  }
}
