import { redo, redoDepth, undo, undoDepth } from 'prosemirror-history';
import { Plugin, PluginKey, type EditorState } from 'prosemirror-state';
import type { EditorView } from 'prosemirror-view';
import type * as Y from 'yjs';
import type { GridClient } from './grids';

/** What the editor's undo and redo commands take back and do again. */
export interface Undo {
  canUndo(): boolean;
  canRedo(): boolean;
  undo(): void;
  redo(): void;
  /** Calls the listener whenever what can be taken back or done again changes. */
  subscribe(listener: () => void): () => void;
}

/** One change as the user made it: of its text, as many items as Yjs keeps on its stack for it,
 * and its edits of grids by their tokens, in the order they were made. */
export interface Entry {
  items: number;
  tokens: string[];
}

/** An editor's own changes in the order made, each taken back whole: its text's as Yjs records
 * them, its grids' by the tokens of their edits, which the server takes back as edits of their
 * own and, taken back in turn, does again. */
export class History implements Undo {
  private past: Entry[] = [];
  private future: Entry[] = [];
  private listeners = new Set<() => void>();
  /** Yjs moves its items between its stacks as this takes back and does again. */
  private replaying = false;
  private group: Entry | null = null;

  constructor(
    readonly manager: Y.UndoManager,
    private grids: () => { client: GridClient; doc: Y.Doc } | null,
    private fail: (error: unknown) => void,
  ) {
    manager.on('stack-item-added', ({ type }: { type: 'undo' | 'redo' }) => {
      if (!this.replaying && type === 'undo') this.record({ items: 1, tokens: [] });
    });
  }

  private record(entry: Entry): void {
    if (this.group) {
      this.group.items += entry.items;
      this.group.tokens.push(...entry.tokens);
      return;
    }
    this.past.push(entry);
    this.future = [];
    this.told();
  }

  /** An edit of grids done by its token, which a following change of the text does not join. */
  wrote(token: string): void {
    this.manager.stopCapturing();
    if (!this.group) this.manager.clear(false, true);
    this.record({ items: 0, tokens: [token] });
  }

  /** What `run` changes as one change, and what is run later with this change's `into`. */
  together(run: () => void): Entry {
    if (this.group) {
      run();
      return this.group;
    }
    const entry: Entry = { items: 0, tokens: [] };
    this.manager.stopCapturing();
    this.group = entry;
    try {
      run();
    } finally {
      this.group = null;
      this.manager.stopCapturing();
    }
    if (entry.items || entry.tokens.length) this.record(entry);
    return entry;
  }

  /** What `run` changes as part of `entry`, while it is still the last change; else as one of
   * its own. */
  into(entry: Entry, run: () => void): void {
    if (this.past.at(-1) !== entry || this.group) {
      this.together(run);
      return;
    }
    this.past.pop();
    this.group = entry;
    this.manager.stopCapturing();
    try {
      run();
    } finally {
      this.group = null;
      this.manager.stopCapturing();
      this.past.push(entry);
    }
  }

  canUndo(): boolean {
    return this.past.length > 0;
  }

  canRedo(): boolean {
    return this.future.length > 0;
  }

  undo(): void {
    const entry = this.past.pop();
    if (entry) this.future.push(this.replay(entry, 'undo'));
    this.told();
  }

  redo(): void {
    const entry = this.future.pop();
    if (entry) this.past.push(this.replay(entry, 'redo'));
    this.told();
  }

  /** The entry's text taken back or done again, then its grid edits after it, each by an edit of
   * its own, whose token taking back the entry again takes it back. */
  private replay(entry: Entry, way: 'undo' | 'redo'): Entry {
    this.replaying = true;
    try {
      for (let item = 0; item < entry.items; item++) {
        if (way === 'undo') this.manager.undo();
        else this.manager.redo();
      }
    } finally {
      this.replaying = false;
    }
    const grids = this.grids();
    if (!grids || !entry.tokens.length) return { items: entry.items, tokens: [] };
    const tokens = entry.tokens.toReversed().map((token) => {
      const { token: then, answer } = grids.client.undo(token, grids.doc);
      answer.catch(this.fail);
      return then;
    });
    return { items: entry.items, tokens: tokens.toReversed() };
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private told(): void {
    for (const listener of this.listeners) listener();
  }
}

const key = new PluginKey<History>('history');

/** Where the editor's history is found, for its commands and its cells'. */
export function historyPlugin(history: History): Plugin<History> {
  return new Plugin<History>({ key, state: { init: () => history, apply: (_, kept) => kept } });
}

export function historyIn(state: EditorState): History | null {
  return key.getState(state) ?? null;
}

/** The undo of an editor of its own, as a light cell's has while it is written in. */
export function ownUndo(view: EditorView): Undo {
  return {
    canUndo: () => undoDepth(view.state) > 0,
    canRedo: () => redoDepth(view.state) > 0,
    undo: () => undo(view.state, view.dispatch),
    redo: () => redo(view.state, view.dispatch),
    subscribe: () => () => {},
  };
}
