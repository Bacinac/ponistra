import { afterEach, describe, expect, it, vi } from 'vitest';
import { applyAwarenessUpdate, Awareness, encodeAwarenessUpdate } from 'y-protocols/awareness';
import type { WebsocketProvider } from 'y-websocket';
import * as Y from 'yjs';
import { watchNews } from './news';

const awarenesses: Awareness[] = [];
afterEach(() => awarenesses.splice(0).forEach((awareness) => awareness.destroy()));

describe('the news of a document', () => {
  it('is fetched again when the server tells of its kind in the room, or the room is back', () => {
    const awareness = new Awareness(new Y.Doc());
    const server = new Awareness(new Y.Doc());
    const someone = new Awareness(new Y.Doc());
    awarenesses.push(awareness, server, someone);
    const synced: ((now: boolean) => void)[] = [];
    const provider = {
      awareness,
      on: (event: string, handler: (now: boolean) => void) =>
        event === 'sync' && synced.push(handler),
    } as unknown as WebsocketProvider;
    const sync = (now: boolean) => synced.forEach((handler) => handler(now));
    const comments = vi.fn();
    const tabs = vi.fn();
    watchNews(provider, 'comments', comments);
    watchNews(provider, 'tabs', tabs);
    const hear = (from: Awareness) =>
      applyAwarenessUpdate(awareness, encodeAwarenessUpdate(from, [from.clientID]), 'room');

    server.setLocalState({ comments: 1 });
    hear(server);
    someone.setLocalState({ user: { id: 2, name: 'Ana', color: '#176b72' } });
    hear(someone);
    server.setLocalState({ comments: 1 });
    hear(server);
    expect([comments.mock.calls.length, tabs.mock.calls.length]).toEqual([1, 0]);
    server.setLocalState({ comments: 1, tabs: 1 });
    hear(server);
    expect([comments.mock.calls.length, tabs.mock.calls.length]).toEqual([1, 1]);
    server.setLocalState({ comments: 2, tabs: 1 });
    hear(server);
    sync(true);
    sync(false);
    sync(true);
    expect([comments.mock.calls.length, tabs.mock.calls.length]).toEqual([3, 2]);
  });
});
