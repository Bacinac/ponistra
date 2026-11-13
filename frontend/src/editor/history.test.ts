import { describe, expect, it, vi } from 'vitest';
import * as Y from 'yjs';
import type { GridClient } from './grids';
import { History } from './history';

function fresh() {
  const doc = new Y.Doc();
  const text = doc.getText('text');
  const manager = new Y.UndoManager(text, { captureTimeout: 0 });
  const undo = vi.fn((token: string) => ({ token: `-${token}`, answer: Promise.resolve() }));
  const client = { undo } as unknown as GridClient;
  const history = new History(
    manager,
    () => ({ client, doc }),
    (error) => {
      throw error;
    },
  );
  return { history, text, undo };
}

describe("an editor's history", () => {
  it('takes back the text and the grids in the order they changed, each change whole', () => {
    const { history, text, undo } = fresh();
    text.insert(0, 'a');
    history.wrote('t1');
    expect([history.canUndo(), history.canRedo()]).toEqual([true, false]);

    history.undo();
    expect([undo.mock.calls, text.toString()]).toEqual([[['t1', expect.any(Y.Doc)]], 'a']);
    history.undo();
    expect([text.toString(), history.canUndo(), history.canRedo()]).toEqual(['', false, true]);

    history.redo();
    expect(text.toString()).toBe('a');
    history.redo();
    expect(undo.mock.calls.at(-1)![0]).toBe('-t1');
    expect([history.canUndo(), history.canRedo()]).toEqual([true, false]);
  });

  it('takes back what ran together as one change, its grid edits last first', () => {
    const { history, text, undo } = fresh();
    history.together(() => {
      text.insert(0, 'x');
      history.wrote('t1');
      history.wrote('t2');
    });
    history.undo();
    expect(text.toString()).toBe('');
    expect(undo.mock.calls.map(([token]) => token)).toEqual(['t2', 't1']);
    expect(history.canUndo()).toBe(false);
  });

  it('joins a change while it is the last, and makes one of its own after another', () => {
    const { history, text } = fresh();
    const entry = history.together(() => history.wrote('t1'));
    history.into(entry, () => text.insert(0, 'a'));
    text.insert(1, 'b');
    history.into(entry, () => text.insert(2, 'c'));
    history.undo();
    expect(text.toString()).toBe('ab');
    history.undo();
    expect(text.toString()).toBe('a');
    history.undo();
    expect([text.toString(), history.canUndo()]).toEqual(['', false]);
  });

  it('forgets what was taken back once something else changes, and tells who listens', () => {
    const { history, text } = fresh();
    const told = vi.fn();
    history.subscribe(told);
    text.insert(0, 'a');
    history.undo();
    expect(history.canRedo()).toBe(true);
    history.wrote('t1');
    expect([history.canRedo(), told.mock.calls.length]).toEqual([false, 3]);
  });
});
