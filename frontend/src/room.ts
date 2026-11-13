import { useQueryClient } from '@tanstack/react-query';
import { useCallback } from 'react';
import { WebsocketProvider } from 'y-websocket';
import * as Y from 'yjs';
import { SESSION_KEY } from './auth';
import { keptRoom } from './kept';
import { nodeKey, useNode } from './tree';

declare global {
  interface Window {
    ponistraHeld?: (room: string) => Uint8Array | null;
  }
}

const joined = new Map<string, Y.Doc>();

window.ponistraHeld = (room) => {
  const doc = joined.get(room);
  return doc ? Y.encodeStateAsUpdate(doc) : null;
};

/** The room's state as this page holds it, or the page that opened this window: what was written
 * there reaches the server a moment later, and a show must not start without it. */
export function heldState(room: string): Uint8Array | null {
  const here = window.ponistraHeld!(room);
  if (here) return here;
  try {
    const there = window.opener?.ponistraHeld?.(room);
    return there ? new Uint8Array(there) : null;
  } catch {
    // An opener of another origin holds none of our rooms.
    return null;
  }
}

function collabUrl(): string {
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${location.host}/api/collab`;
}

/** Fast navigation can leave a room while its socket is still connecting, and closing it then is a
 * console warning, so such a socket closes once it is open. */
class LeavingSocket extends WebSocket {
  override close(code?: number, reason?: string): void {
    if (this.readyState !== WebSocket.CONNECTING) return super.close(code, reason);
    this.addEventListener('open', () => super.close(code, reason), { once: true });
  }
}

/** Connects the doc to its room; one that may be `kept` stays in the browser too on a device
 * marked to work without the network (D45). `onReady` hears whether the doc can be shown: once
 * the room has synced, or at once from what the browser kept of it. */
export function joinRoom(
  room: string,
  doc: Y.Doc,
  onClose: () => void,
  keep = false,
): {
  provider: WebsocketProvider;
  leave: () => void;
  onReady: (listener: (ready: boolean) => void) => void;
} {
  const provider = new WebsocketProvider(collabUrl(), room, doc, {
    connect: false,
    WebSocketPolyfill: LeavingSocket,
  });
  const local = keep ? keptRoom(room, doc) : null;
  let held = false;
  const listeners = new Set<(ready: boolean) => void>();
  const told = () => {
    for (const each of listeners) each(provider.synced || held);
  };
  provider.on('sync', told);
  void local?.whenSynced.then(() => {
    // An empty store has kept nothing yet, and the room alone shows the doc whole.
    held = doc.store.clients.size > 0;
    if (held) told();
  });
  // StrictMode undoes a mount at once, so only a mount that outlives this task opens a socket.
  const connecting = setTimeout(() => provider.connect());
  provider.on('connection-close', onClose);
  joined.set(room, doc);
  return {
    provider,
    leave: () => {
      clearTimeout(connecting);
      provider.destroy();
      void local?.destroy();
      if (joined.get(room) === doc) joined.delete(room);
    },
    onReady: (listener) => listeners.add(listener),
  };
}

/** A room the server refuses closes for good (apps/collab/server.py, `refuse`). Refetching shows
 * the login form for an expired session, the document's absence once it is trashed or the tab
 * deleted, and its new rooms once it is imported again. */
export function useRecheck(documentId: string): () => void {
  const queryClient = useQueryClient();
  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: SESSION_KEY });
    queryClient.invalidateQueries({ queryKey: nodeKey(documentId) });
  }, [queryClient, documentId]);
}

/** Whether the document's rooms may stay in the browser of a device that works without the
 * network: not while a folder on its way keeps it in the browser (D20, D45). */
export function useKept(documentId: string): boolean {
  return useNode(documentId).data?.confined === false;
}
