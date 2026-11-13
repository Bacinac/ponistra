// @vitest-environment jsdom
import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ySyncPlugin } from 'y-prosemirror';
import { applyAwarenessUpdate, Awareness, encodeAwarenessUpdate } from 'y-protocols/awareness';
import * as Y from 'yjs';
import type { MessageKey } from '../i18n/hr';
import { bodyOf } from './tab';
import { NAMED_MS, presence } from './presence';
import { schema } from './schema';

const t = (key: MessageKey) => (key === 'presence.you' ? 'Vi' : key);

const views: EditorView[] = [];
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  views.splice(0).forEach((view) => view.destroy());
  vi.useRealTimers();
});

function connect(left: Y.Doc, right: Y.Doc): void {
  left.on('update', (update: Uint8Array, origin: unknown) => {
    if (origin !== right) Y.applyUpdate(right, update, left);
  });
  right.on('update', (update: Uint8Array, origin: unknown) => {
    if (origin !== left) Y.applyUpdate(left, update, right);
  });
}

function share(from: Awareness, to: Awareness): void {
  from.on('update', ({ added, updated, removed }: Record<string, number[]>, origin: unknown) => {
    if (origin === to) return;
    const clients = [...added, ...updated, ...removed];
    applyAwarenessUpdate(to, encodeAwarenessUpdate(from, clients), from);
  });
}

function window(id: number, name: string): { ydoc: Y.Doc; awareness: Awareness } {
  const ydoc = new Y.Doc();
  const awareness = new Awareness(ydoc);
  awareness.setLocalStateField('user', { id, name, color: '#336699' });
  return { ydoc, awareness };
}

function caretAt(remote: { ydoc: Y.Doc; awareness: Awareness }, index: number): void {
  const [paragraph] = bodyOf(remote.ydoc).toArray() as Y.XmlElement[];
  const position = Y.relativePositionToJSON(
    Y.createRelativePositionFromTypeIndex(paragraph.get(0) as Y.XmlText, index),
  );
  remote.awareness.setLocalStateField('cursor', { anchor: position, head: position });
  vi.advanceTimersByTime(0);
}

describe('presence', () => {
  it("names the others' carets while they move, then only under the pointer", () => {
    const mine = window(1, 'Ana');
    const theirs = window(2, 'Marko');
    const again = window(1, 'Ana');
    connect(mine.ydoc, theirs.ydoc);
    connect(mine.ydoc, again.ydoc);
    for (const other of [theirs, again]) {
      share(other.awareness, mine.awareness);
    }
    const view = new EditorView(document.body.appendChild(document.createElement('div')), {
      state: EditorState.create({
        schema,
        plugins: [ySyncPlugin(bodyOf(mine.ydoc)), ...presence(mine.awareness, () => t)],
      }),
    });
    views.push(view);
    vi.advanceTimersByTime(0);
    view.dispatch(view.state.tr.insertText('Ponuda', 1));

    caretAt(theirs, 3);
    const carets = () => [...view.dom.querySelectorAll<HTMLElement>('.ProseMirror-yjs-cursor')];
    expect(carets().map((caret) => caret.textContent?.replaceAll('⁠', ''))).toEqual(['Marko']);
    expect(carets()[0].classList.contains('ponistra-named')).toBe(true);

    vi.advanceTimersByTime(NAMED_MS);
    expect(carets()[0].classList.contains('ponistra-named')).toBe(false);
    caretAt(theirs, 4);
    expect(carets()[0].classList.contains('ponistra-named')).toBe(true);

    caretAt(again, 1);
    const names = carets().map((caret) => caret.textContent?.replaceAll('⁠', ''));
    expect(names.sort()).toEqual(['Marko', 'Vi']);
  });
});
