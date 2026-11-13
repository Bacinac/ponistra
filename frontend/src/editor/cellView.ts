import { history } from 'prosemirror-history';
import type { Node } from 'prosemirror-model';
import { EditorState, Selection, type Transaction } from 'prosemirror-state';
import { DecorationSet, type DecorationSource, EditorView } from 'prosemirror-view';
import { selectOnFocus } from './focus';
import {
  addressOf,
  formulaText,
  type Misread,
  misread,
  readFormula,
  tableNameText,
  takesReference,
} from './formulas';
import type { Look, Shown } from './grids';
import { schema } from './schema';
import { type Designed, dressOf } from './design';
import { type Box, fillOf } from './sheet';
import {
  filled,
  lightCell,
  lookOf,
  type Placed,
  type Rect,
  retyped,
  standsIn,
  unquoted,
} from './tables';
import {
  ARROWS,
  boxes,
  decorated,
  drawable,
  FROM_OUTSIDE,
  owners,
  pointingChanged,
  sameSource,
  serializer,
  table,
  towards,
  whole,
} from './tableBase';
import type { TableView } from './tableView';

/** The cell whose formula is being written, into which a click in any table puts an address. */
export let writing: CellView | null = null;

/** A cell drawn by an element of its own over the sheet: one with a node in the text, or a light
 * cell while it is written in. A light cell's editor is its own until it is left, when what it
 * holds goes to the grid: its text alone, or blocks where it took a look or more than plain text.
 * A node cell's editor writes its changes as steps of the document's, so collaboration and undo
 * know no difference; it has its editor while it is written in, and while its content or the
 * document's decorations in it need one, and is drawn by the schema otherwise. A cell with a
 * formula shows the value the server computed for it, and its formula once it is entered; a
 * number typed in a cell with a number format shows as the format writes it, and as typed once
 * entered. */
export class CellView {
  readonly box = document.createElement('div');
  /** What the cell holds as it is laid out, measured for its row's height. */
  readonly holder = document.createElement('div');
  /** The cell's text, and its own editor's place once it has one. */
  readonly dom = document.createElement('div');
  inner: EditorView | null = null;
  node: Node | null;
  gone = false;
  /** The formula being written, over the cell's text. */
  formula: HTMLInputElement | null = null;
  private decorations: DecorationSource = DecorationSet.empty;
  private decorated = false;
  private plain: boolean;
  private name = '';
  private word = '';
  /** The value, and the formula while it is written. */
  private shown = document.createElement('div');
  private value = document.createElement('div');
  private drawn: { node: Node | null; text: string } | null = null;
  /** Whether the text typed in a cell with a number format is shown in place of its value. */
  private typing = false;
  private problem: HTMLElement | null = null;
  /** The formula as it was when writing it began. */
  private began = '';
  /** A light cell's content as its editor began with it. */
  private start: Node | null = null;
  /** Where the address a click put in last is, which the next click replaces. */
  private pointed: { from: number; to: number } | null = null;
  private dress: Record<string, string> = {};

  constructor(
    readonly table: TableView,
    public placed: Placed,
    /** A light cell, written to the grid once it is left. */
    readonly light: boolean,
  ) {
    this.node = placed.node;
    this.plain = this.node === null || drawable(this.node);
    this.box.className = 'ponistra-cell-box';
    this.box.dataset.cell = placed.key;
    boxes.set(this.box, this);
    this.shown.className = 'ponistra-cell-value';
    this.shown.append(this.value);
    this.holder.append(this.shown, this.dom);
    this.box.append(this.holder);
    if (light) this.box.addEventListener('focusout', () => this.left());
    if (this.needed()) this.open();
    else this.draw();
  }

  private needed(): boolean {
    return this.light || (this.node !== null && (this.decorated || !this.plain));
  }

  get key(): string {
    return this.placed.key;
  }

  private entry(): Shown | undefined {
    const [row, col] = this.key.split(':');
    return this.table.lines?.cell(row, col);
  }

  get computed(): boolean {
    return this.entry()?.formula !== undefined;
  }

  get formatted(): boolean {
    const value = this.table.valueOf(this.key);
    return !this.computed && standsIn(value, false, this.entry()?.format !== undefined);
  }

  /** The cell as its editor holds it: its node, or one with its text in its look. */
  private content(): Node {
    if (this.node) return this.node;
    const [row, col] = this.key.split(':');
    const shown = this.entry();
    return lightCell(schema, row, col, shown?.text ?? '', shown?.look);
  }

  /** A light cell's editor takes what its grid entry holds now, where nothing was typed in it
   * since it opened or last took it. */
  private renew(): void {
    const { inner, start } = this;
    if (!inner || !start || !inner.state.doc.eq(start)) return;
    const tr = towards(inner.state, this.content());
    if (!tr) return;
    inner.dispatch(tr);
    this.start = inner.state.doc;
  }

  /** The cell's own editor, made where its text was. */
  open(): EditorView {
    if (this.inner) return this.inner;
    const { table } = this;
    const { spec } = table;
    this.dom.replaceChildren();
    const content = this.content();
    if (this.light) this.start = content;
    const inner = new EditorView(
      { mount: this.dom },
      {
        state: EditorState.create({
          doc: content,
          plugins: this.light ? [...spec.inner, history()] : spec.inner,
        }),
        editable: () => table.outer.editable,
        nodeViews: spec.nodeViews,
        decorations: () => this.decorations,
        attributes: () => ({ class: 'ponistra-cell', role: 'textbox', 'aria-label': this.name }),
        dispatchTransaction: (tr) => this.dispatchInner(tr),
        handlePaste: (_view, _event, slice) => table.pasted(this, slice),
        handleTextInput: (view, _from, _to, text) => {
          if (text !== '=' || filled(view.state.doc)) return false;
          this.edit('=');
          return true;
        },
        handleDOMEvents: {
          focus: (view) => {
            selectOnFocus(view);
            this.reveal();
            table.entered(this.key);
            spec.onCell(inner);
            return false;
          },
        },
      },
    );
    owners.set(inner, this);
    this.inner = inner;
    return inner;
  }

  /** The editor put away once the cell is left, where nothing in it needs one. */
  private shut(): void {
    const { inner } = this;
    if (!inner || this.formula || inner.hasFocus() || this.needed()) return;
    this.inner = null;
    inner.destroy();
    for (const name of ['contenteditable', 'translate']) this.dom.removeAttribute(name);
    this.draw();
  }

  /** The cell's text as it reads, while it has no editor. */
  private draw(): void {
    this.dom.className = 'ponistra-cell';
    this.dom.setAttribute('role', 'textbox');
    this.dom.setAttribute('aria-label', this.name);
    const drawn = serializer.serializeFragment(unquoted(this.content()).content);
    // An empty paragraph keeps a line's height, as the editor's own trailing break gives it.
    drawn
      .querySelectorAll('p:empty')
      .forEach((block) => block.append(document.createElement('br')));
    this.dom.replaceChildren(drawn);
  }

  /** Opened where it was clicked, as the browser would put the cursor in an editor. */
  openAt(left: number, top: number): void {
    const inner = this.open();
    inner.focus();
    const { doc } = inner.state;
    const at = inner.posAtCoords({ left, top })?.pos ?? doc.content.size;
    inner.dispatch(inner.state.tr.setSelection(Selection.near(doc.resolve(at))));
  }

  /** What the cell shows: its value, or its text. */
  get face(): HTMLElement {
    return this.dom.hidden ? this.shown : this.dom;
  }

  /** The value in place of the text, or the formula while it is written. */
  show(): void {
    const value = this.table.valueOf(this.key);
    const writing = this.formula !== null;
    const shown = this.computed || writing || (this.formatted && !this.typing);
    if (this.dom.hidden !== shown) this.dom.hidden = shown;
    if (this.shown.hidden === shown) this.shown.hidden = !shown;
    if (this.value.hidden !== writing) this.value.hidden = writing;
    const text = shown && !writing ? (value?.text ?? '') : null;
    if (text === null) {
      if (this.drawn) this.value.replaceChildren();
      this.drawn = null;
    } else if (this.drawn?.node !== this.node || this.drawn.text !== text) {
      this.drawn = { node: this.node, text };
      const cell = retyped(this.content(), text);
      this.value.replaceChildren(serializer.serializeFragment(cell.content));
    }
    const kind = writing ? '' : (value?.kind ?? '');
    if (this.shown.dataset.kind !== kind) this.shown.dataset.kind = kind;
    if (this.dom.dataset.kind !== kind) this.dom.dataset.kind = kind;
    const designed = this.table.design.at(this.placed.row, this.placed.col);
    const fill = fillOf(this.table.lines ?? undefined, this.placed, designed);
    if (this.box.style.getPropertyValue('--fill') !== fill)
      this.box.style.setProperty('--fill', fill);
    this.dressIn(designed);
  }

  /** The cell's design on its element, beneath what its own text carries. */
  private dressIn(designed: Designed): void {
    const dress = dressOf(designed);
    if (designed.valign === 'center' || designed.valign === 'bottom') {
      dress['align-content'] = designed.valign === 'center' ? 'center' : 'end';
    }
    const { style } = this.box;
    for (const name of Object.keys(this.dress)) if (!(name in dress)) style.removeProperty(name);
    for (const [name, value] of Object.entries(dress)) {
      if (style.getPropertyValue(name) !== value) style.setProperty(name, value);
    }
    this.dress = dress;
  }

  /** The typed text in place of the value, for writing in it. */
  reveal(): void {
    if (this.typing) return;
    this.typing = true;
    this.show();
  }

  /** The value again in place of the typed text, once the cell is left. */
  leave(): void {
    if (this.light) return;
    if (this.typing) {
      this.typing = false;
      this.show();
    }
    this.shut();
  }

  /** A light cell left for anywhere outside it, while the page has the focus, is written. Left
   * for the editor's toolbar, a menu or a dialog, it stays open until the focus goes on elsewhere:
   * the command chosen there acts on it, and gives the focus back to it. */
  private left(): void {
    setTimeout(() => {
      if (this.gone || !document.hasFocus()) return;
      if (this.box.contains(document.activeElement)) return;
      this.close();
      if (aside(document.activeElement)) document.addEventListener('focusin', this.away, true);
      else this.table.closed(this);
    });
  }

  private away = (event: FocusEvent) => {
    if (aside(event.target)) return;
    document.removeEventListener('focusin', this.away, true);
    if (!(event.target instanceof globalThis.Node && this.box.contains(event.target))) {
      this.table.closed(this);
    }
  };

  /** What a light cell's editor holds, to the grid where it changed: its text alone where it kept
   * its look, else its blocks, which the server keeps as a light cell's where they are one. */
  private written(): void {
    const { inner, start } = this;
    if (!this.light || !inner || !start || inner.state.doc.eq(start)) return;
    const doc = inner.state.doc;
    const [row, col] = this.key.split(':');
    const before = this.entry();
    const was = lookOf(start);
    const now = lookOf(doc);
    if (
      now &&
      was &&
      JSON.stringify(now.look) === JSON.stringify(was.look) &&
      !now.text.startsWith('=')
    ) {
      this.table.writeCells([{ row, col, value: now.text || null }], {
        [this.key]: { ...before, formula: undefined, text: now.text },
      });
    } else {
      this.table.writeCells([{ row, col, blocks: blocksJSON(doc) }], {
        [this.key]: now ? { ...before, text: now.text, look: now.look } : { text: doc.textContent },
      });
    }
    this.start = doc;
  }

  /** The look a light cell's editor gave it, as blocks without text, which a formula written
   * after them keeps; none where its look is as it was. */
  takeLook(): { blocks: object[]; look: Look | undefined } | null {
    const { inner, start } = this;
    if (!this.light || !inner || !start) return null;
    const doc = inner.state.doc;
    this.start = doc;
    const now = lookOf(doc);
    if (!now || JSON.stringify(now.look) === JSON.stringify(lookOf(start)?.look)) return null;
    return { blocks: blocksJSON(retyped(doc, '')), look: now.look };
  }

  /** Opens the formula for writing, or starts one with `start`. */
  edit(start?: string, select: 'all' | 'end' = 'end'): void {
    if (this.gone) return;
    if (!this.formula) {
      const inner = this.open();
      const formula = this.entry()?.formula;
      this.began = formula ? formulaText(formula, this.table.syntax(), this.table.book()) : '';
      const input = document.createElement('input');
      input.className = 'ponistra-formula';
      input.spellcheck = false;
      input.autocomplete = 'off';
      input.readOnly = !this.table.outer.editable;
      const address = this.table.addressAt(this.placed.row, this.placed.col);
      input.setAttribute('aria-label', `${this.table.spec.label()('table.formula')} ${address}`);
      input.value = start ?? this.began;
      input.addEventListener('keydown', (event) => this.keyed(event));
      input.addEventListener('input', () => {
        this.pointed = null;
        this.misread(null);
      });
      input.addEventListener('focus', () => {
        this.table.entered(this.key);
        this.table.spec.onCell(inner);
      });
      input.addEventListener('blur', () => {
        if (this.formula === input) this.commit(false);
      });
      this.formula = input;
      writing = this;
      this.table.outer.dom.classList.add('ponistra-pointing');
      pointingChanged(this.table.outer);
      this.shown.append(input);
      this.show();
    } else if (start !== undefined) {
      this.formula.value = start;
    }
    const { formula } = this;
    formula.focus();
    if (select === 'all') formula.select();
    else formula.setSelectionRange(formula.value.length, formula.value.length);
  }

  /** Whether a click on another cell now puts its address in the formula. */
  takes(): boolean {
    const input = this.formula;
    if (!input || input.readOnly || input !== input.ownerDocument.activeElement) return false;
    const caret = input.selectionStart ?? input.value.length;
    if (this.pointed && caret === this.pointed.to && input.selectionEnd === caret) return true;
    return takesReference(input.value.slice(0, caret), this.table.syntax());
  }

  /** The address of the cells pointed at, after the name of their table where it is another, in
   * place of the one pointed at before. */
  point(rect: Rect, table: string | null = null): void {
    const input = this.formula;
    if (!input) return;
    const text = (table === null ? '' : `${tableNameText(table)}!`) + addressOf(rect);
    const from = this.pointed?.from ?? input.selectionStart ?? input.value.length;
    const to = this.pointed?.to ?? input.selectionEnd ?? from;
    input.setRangeText(text, from, to, 'end');
    this.pointed = { from, to: from + text.length };
    this.misread(null);
  }

  /** Keeps what was written: a formula, or text where it no longer starts with "=". A formula that
   * cannot be read stays open, showing why. */
  commit(focus = true): boolean {
    const input = this.formula;
    if (!input) return true;
    const text = input.value;
    if (!input.readOnly && text !== this.began) {
      if (text.startsWith('=') && text.trim() !== '=') {
        const found = readFormula(text, this.table.size(), this.table.syntax(), this.table.book());
        if (misread(found)) {
          this.misread(found, focus);
          return false;
        }
        this.table.setFormula(this, found);
      } else {
        this.table.setFormula(this, null, text.trim() === '=' ? '' : text);
      }
    }
    this.close();
    return true;
  }

  /** Back to what the cell held before. */
  cancel(): void {
    const computed = this.computed;
    this.close(false);
    if (computed || this.light) this.table.select(this.key, this.key);
    else this.focus(Selection.atEnd);
  }

  /** The formula put away, and a light cell's editor with it once what it holds is written. */
  close(write = true): void {
    const input = this.formula;
    if (input) {
      this.formula = null;
      if (writing === this) writing = null;
      if (!writing) {
        this.table.outer.dom.classList.remove('ponistra-pointing');
        pointingChanged(this.table.outer);
      }
      this.pointed = null;
      this.problem?.remove();
      this.problem = null;
      input.remove();
      this.show();
    }
    if (this.light && write && !this.box.contains(document.activeElement)) this.written();
  }

  private misread(found: Misread | null, focus = true): void {
    const input = this.formula;
    if (!input) return;
    input.setAttribute('aria-invalid', String(found !== null));
    if (!found) {
      this.problem?.remove();
      this.problem = null;
      return;
    }
    const t = this.table.spec.label();
    this.problem ??= this.box.appendChild(document.createElement('div'));
    this.problem.className = 'ponistra-formula-problem';
    this.problem.setAttribute('role', 'alert');
    this.problem.textContent = t(
      found.problem === 'outside'
        ? 'formula.outside'
        : found.problem === 'table'
          ? 'formula.table'
          : this.table.syntax().list === ';'
            ? 'formula.semicolons'
            : 'formula.commas',
    );
    if (!focus) return;
    input.focus();
    input.setSelectionRange(found.from, found.to);
  }

  private keyed(event: KeyboardEvent): void {
    const input = this.formula;
    if (!input || event.isComposing) return;
    const leave = (then: () => void) => {
      event.preventDefault();
      if (this.commit()) then();
    };
    const dir = ARROWS[event.key];
    const caret = input.selectionStart === input.selectionEnd ? input.selectionStart : null;
    if (event.key === 'Enter') leave(() => this.table.move(this, event.shiftKey ? 'up' : 'down'));
    else if (event.key === 'Tab') leave(() => this.table.tab(this.key, event.shiftKey ? -1 : 1));
    else if (event.key === 'Escape') {
      event.preventDefault();
      this.cancel();
    } else if (
      dir &&
      !event.shiftKey &&
      (dir === 'up' || dir === 'down' || caret === (dir === 'left' ? 0 : input.value.length))
    ) {
      leave(() => this.table.move(this, dir));
    }
  }

  /** The cell as placed now, at `box` on the sheet, named by `word` and its address, its value
   * shown again where its grid entries changed. */
  sync(
    placed: Placed,
    box: Box,
    decorations: DecorationSource,
    word: string,
    entries: boolean,
  ): void {
    const relabelled =
      word !== this.word || placed.row !== this.placed.row || placed.col !== this.placed.col;
    this.placed = placed;
    if (relabelled) {
      this.word = word;
      this.name = `${word} ${this.table.addressAt(placed.row, placed.col)}`;
    }
    const changed = !this.light && placed.node !== this.node;
    if (changed) {
      this.node = placed.node;
      this.plain = this.node === null || drawable(this.node);
    }
    const redecorated = !sameSource(decorations, this.decorations);
    if (redecorated) {
      this.decorations = decorations;
      this.decorated = decorated(decorations);
    }
    if (this.inner) {
      if (changed) {
        const tr = towards(this.inner.state, this.content());
        if (tr) this.inner.dispatch(tr);
      } else if (this.light && entries) this.renew();
      if (redecorated || relabelled) this.inner.setProps({});
    } else if (this.needed()) this.open();
    else if (changed) this.draw();
    else if (relabelled) this.dom.setAttribute('aria-label', this.name);
    const { style } = this.box;
    const size = this.light ? 'minHeight' : 'height';
    for (const [name, value] of [
      ['left', box.x],
      ['top', box.y],
      ['width', box.width],
      [size, box.height],
    ] as const) {
      if (style[name] !== `${value}px`) style[name] = `${value}px`;
    }
    if (changed || entries || relabelled) this.show();
  }

  private dispatchInner(tr: Transaction): void {
    const inner = this.inner!;
    const { state, transactions } = inner.state.applyTransaction(tr);
    inner.updateState(state);
    if (!tr.getMeta(FROM_OUTSIDE) && !this.light) {
      const steps = transactions.flatMap((transaction) => transaction.steps);
      if (steps.length) this.table.write(this, steps);
    }
    if (inner.hasFocus()) this.table.spec.onCell(inner);
  }

  focus(selection: (doc: Node) => Selection): void {
    if (this.gone) return;
    if (this.computed) {
      this.edit(undefined, selection === whole ? 'all' : 'end');
      return;
    }
    this.reveal();
    const inner = this.open();
    inner.focus();
    const { state } = inner;
    inner.dispatch(state.tr.setSelection(selection(state.doc)).scrollIntoView());
  }

  /** A light cell's editor holding `text` in place of what it held, its look kept. */
  replaceText(text: string): void {
    const inner = this.open();
    const { state } = inner;
    const { content } = retyped(state.doc, text);
    inner.dispatch(state.tr.replaceWith(0, state.doc.content.size, content));
  }

  destroy(): void {
    this.gone = true;
    document.removeEventListener('focusin', this.away, true);
    if (writing === this) writing = null;
    this.formula = null;
    this.inner?.destroy();
    this.box.remove();
  }
}

/** Where the focus goes to choose what to do with the cell it came from. */
function aside(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    target.closest('[role="toolbar"], [role="menu"], [role="dialog"], [role="alertdialog"]') !==
      null
  );
}

export function blocksJSON(cell: Node): object[] {
  const blocks: object[] = [];
  cell.forEach((block) => blocks.push(block.toJSON()));
  return blocks;
}

/** Rows a table holds at once around those in view, in blocks of as many. */
