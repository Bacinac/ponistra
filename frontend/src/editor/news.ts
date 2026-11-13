import type { WebsocketProvider } from 'y-websocket';

/** What the server announces in a document's own room about what it keeps outside the room. */
export type News = 'comments' | 'tabs';

/** Calls back when the server says the news has changed, which it does through its presence in the
 * document's own room, and when that room is back after a drop that may have missed it. The
 * server's presence carries every kind of news, so only a count that moved is news of this kind. */
export function watchNews(provider: WebsocketProvider, news: News, changed: () => void): void {
  const { awareness } = provider;
  const heard = new Map<number, unknown>();
  awareness.on('change', ({ added, updated }: { added: number[]; updated: number[] }) => {
    const states = awareness.getStates();
    let moved = false;
    for (const client of [...added, ...updated]) {
      const told = states.get(client)?.[news];
      if (told === undefined || told === heard.get(client)) continue;
      heard.set(client, told);
      moved = true;
    }
    if (moved) changed();
  });
  let synced = false;
  provider.on('sync', (now: boolean) => {
    if (now && synced) changed();
    synced ||= now;
  });
}
