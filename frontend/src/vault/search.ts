import { useQuery } from '@tanstack/react-query';
import { hostOf, type Opened } from './secret';
import { OPENED, openedItems, useCollections, useVault, type Collection } from './state';

export interface Held {
  item: Opened;
  collection: Collection;
}

export function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replaceAll('đ', 'd');
}

export function wordsOf(text: string): string[] {
  return fold(text)
    .split(/[^\p{L}\p{N}]+/u)
    .filter(Boolean);
}

/** Whether each word typed starts a word of the item's name, its user name or a site's host.
 * Its notes and its secrets are not searched. */
export function matches(item: Opened, words: string[]): boolean {
  const { name, username, urls } = item.secret;
  const own = wordsOf([name, username, ...urls.map(hostOf)].join(' '));
  return words.every((word) => own.some((each) => each.startsWith(word)));
}

/** The items of every collection the user holds a key to, opened in the browser while the
 * vault is unlocked; locking the vault drops them with the rest of what was opened. */
export function useHeld(enabled: boolean) {
  const { unlocked } = useVault();
  const collections = useCollections(enabled && unlocked !== null);
  const keyed = (collections.data ?? []).filter((collection) => collection.key);
  return useQuery({
    queryKey: [...OPENED, unlocked?.epoch, 'all', keyed.map((collection) => collection.id)],
    queryFn: async (): Promise<Held[]> =>
      (
        await Promise.all(
          keyed.map(async (collection) =>
            (await openedItems(unlocked!, collection))
              .filter((item) => !item.trashed_at)
              .map((item) => ({ item, collection })),
          ),
        )
      ).flat(),
    enabled: enabled && unlocked !== null && keyed.length > 0,
    staleTime: 5 * 60_000,
  });
}
