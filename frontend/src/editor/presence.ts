import { Plugin } from 'prosemirror-state';
import { yCursorPlugin } from 'y-prosemirror';
import type { Awareness } from 'y-protocols/awareness';
import type { MessageKey } from '../i18n/hr';

export const NAMED_MS = 3000;

interface Person {
  id?: number;
  name: string;
  color: string;
}

interface Changes {
  added: number[];
  updated: number[];
  removed: number[];
}

/** The others in the text, each a caret and a selection in their colour. A caret names its
    person while they write or move and for a moment after, then only under the pointer; the
    same account in another window is named as the reader. */
export function presence(awareness: Awareness, label: () => (key: MessageKey) => string): Plugin[] {
  const carets = new Map<number, HTMLElement>();
  const moved = new Map<number, number>();
  const timers = new Map<number, ReturnType<typeof setTimeout>>();

  const name = (client: number) => {
    const caret = carets.get(client);
    if (!caret) return;
    clearTimeout(timers.get(client));
    const left = NAMED_MS - (Date.now() - (moved.get(client) ?? -Infinity));
    caret.classList.toggle('ponistra-named', left > 0);
    if (left <= 0) return;
    timers.set(client, setTimeout(name, left, client));
  };

  const cursorBuilder = (person: Person, client: number) => {
    const caret = document.createElement('span');
    caret.className = 'ProseMirror-yjs-cursor';
    caret.style.borderColor = person.color;
    const tag = document.createElement('div');
    tag.style.backgroundColor = person.color;
    const you = person.id !== undefined && person.id === awareness.getLocalState()?.user?.id;
    tag.textContent = you ? label()('presence.you') : person.name;
    caret.append('⁠', tag, '⁠');
    carets.set(client, caret);
    name(client);
    return caret;
  };

  const changed = ({ added, updated, removed }: Changes) => {
    for (const client of [...added, ...updated]) {
      if (client === awareness.clientID) continue;
      moved.set(client, Date.now());
      name(client);
    }
    for (const client of removed) {
      clearTimeout(timers.get(client));
      for (const map of [carets, moved, timers]) map.delete(client);
    }
  };

  return [
    yCursorPlugin(awareness, { cursorBuilder }),
    new Plugin({
      view: () => {
        awareness.on('change', changed);
        return {
          destroy: () => {
            awareness.off('change', changed);
            timers.forEach(clearTimeout);
          },
        };
      },
    }),
  ];
}
