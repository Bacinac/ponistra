import type { Node } from 'prosemirror-model';
import { Plugin, PluginKey, type Command, type EditorState } from 'prosemirror-state';
import type { NodeView } from 'prosemirror-view';
import { schema, type FieldKind } from './schema';

/** What the fields of a tab's headers and footers show, but for the page's own number. */
export interface Fields {
  first: number;
  total: number;
  title: string;
  date: string;
}

export function valueOf(kind: string | undefined, page: number, fields: Fields): string {
  switch (kind as FieldKind) {
    case 'pages':
      return String(fields.total);
    case 'title':
      return fields.title;
    case 'date':
      return fields.date;
    default:
      return String(page);
  }
}

/** The header or footer being written, and the page it is written on. */
export interface Writing {
  side: 'header' | 'footer';
  page: number;
}

/** What the commands may do with the tab's headers and footers. */
export interface Parts {
  /** Whether the first page of the section has its own. */
  firstApart: boolean;
  /** Whether the part being written shows the section before's; null in the tab's first section
   * or while none is written. */
  linked: boolean | null;
  writing: Writing | null;
  /** Opens the header or footer of the page the text's cursor is on. */
  open: (side: Writing['side']) => void;
  setFirstApart: (apart: boolean) => void;
  setLinked: (linked: boolean) => void;
  close: () => void;
}

const partKey = new PluginKey<true>('part');

/** Marks a header's or a footer's own editor. */
export function partPlugin(): Plugin<true> {
  return new Plugin({ key: partKey, state: { init: () => true, apply: () => true } });
}

export function inPart(state: EditorState): boolean {
  return partKey.getState(state) === true;
}

export function insertField(kind: FieldKind): Command {
  return (state, dispatch) => {
    if (!inPart(state)) return false;
    dispatch?.(state.tr.replaceSelectionWith(schema.nodes.field.create({ kind })).scrollIntoView());
    return true;
  };
}

/** A field as the page being written on shows it. */
export function fieldView(value: (kind: string) => string) {
  return (node: Node): NodeView => {
    const dom = document.createElement('span');
    dom.dataset.field = node.attrs.kind;
    dom.contentEditable = 'false';
    dom.textContent = value(node.attrs.kind);
    return { dom };
  };
}
