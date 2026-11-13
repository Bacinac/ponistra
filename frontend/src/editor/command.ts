import type { LucideIcon } from 'lucide-react';
import type { EditorView } from 'prosemirror-view';
import type * as Y from 'yjs';
import type { Desk } from '../comments';
import type { MessageKey } from '../i18n/hr';
import type { ListStore } from './forms';
import type { Undo } from './history';
import type { TabNotes } from './notes';
import type { Parts } from './parts';
import type { Consent, Run } from './runs';
import type { Size, Template } from './slides';
import type { Styling } from './styling';
import { CellRange } from './tableBase';
import type { Target } from './tablesPlugin';

export type Where = 'text' | 'table' | 'image' | 'pdf' | 'chart' | 'note' | 'part';
export type Group =
  | 'history'
  | 'clipboard'
  | 'style'
  | 'format'
  | 'script'
  | 'color'
  | 'highlight'
  | 'list'
  | 'numberForm'
  | 'bulletForm'
  | 'numbering'
  | 'align'
  | 'indent'
  | 'paragraph'
  | 'insert'
  | 'comment'
  | 'review'
  | 'writing'
  | 'rewrite'
  | 'translate'
  | 'table'
  | 'tableDesign'
  | 'tablePart'
  | 'tableData'
  | 'total'
  | 'cellFormat'
  | 'fill'
  | 'image'
  | 'pdf'
  | 'chart'
  | 'note'
  | 'part'
  | 'slide'
  | 'slideLayout'
  | 'slideSize'
  | 'document'
  | 'find'
  | 'help';
export type Dialog =
  | 'shortcuts'
  | 'link'
  | 'image'
  | 'imageAlt'
  | 'imageEdit'
  | 'pdf'
  | 'pdfPages'
  | 'listFormat'
  | 'cellFormat'
  | 'tableName'
  | 'goTo'
  | 'chart'
  | 'tabStops'
  | 'compare'
  | 'compareFile'
  | 'ask'
  | 'task'
  | 'calculate'
  | 'find'
  | 'replace';

/** Where the editor's tab is, for a link to one of its blocks. */
export interface Place {
  document: string;
  tab: string | null;
  address: string;
}

export interface Context {
  view: EditorView;
  doc: Y.Doc;
  history: Undo;
  styling: Styling;
  place: Place;
  /** The tab's note numbering, where the document's own room is at hand. */
  notes: TabNotes | null;
  /** The page's comments, where the editor is a live document's. */
  desk: Desk | null;
  /** The tab's headers and footers, where its pages can be written. */
  parts: Parts | null;
  /** The document's slides, where the editor shows them. */
  slides: Slides | null;
  /** Shows the document's slides on the whole screen, where it is a live document. */
  present: ((from: 'cursor' | 'start') => void) | null;
  lists: ListStore;
  open: (dialog: Dialog) => void;
  fail: (error: unknown) => void;
  /** Tells the editor that a run of an action is done, or under way in the background, to offer
   * taking it back once it ends. */
  ran: (run: Run) => void;
  /** Asks the user to let a model's action send its target out, going on as they answer once the
   * document has been let where they let it always. */
  consent: (go: (consent: Consent) => void) => void;
  label: (key: MessageKey) => string;
  /** Whether what the user writes is proposed, in the Suggesting mode. */
  suggesting: boolean;
  suggest: (on: boolean) => void;
  /** Opens the document's tab at what the query leads to; false where the document has no such
   * tab. */
  visitTab: (tab: string, query: string) => boolean;
}

export interface Slides {
  template: Template;
  setSize: (size: Size) => void;
}

export interface EditorCommand {
  id: string;
  label: MessageKey;
  /** The user's own name for it, as a document's style has, shown in place of the label. */
  name?: string;
  /** Which one of a family, as "Text colour: red" names it. */
  detail?: MessageKey;
  /** How it looks, shown in place of a detail, as "List format: a)". */
  sample?: string;
  icon: LucideIcon;
  /** The colour a menu shows in place of the icon. */
  swatch?: string;
  group: Group;
  where: readonly Where[];
  keys?: readonly string[];
  /** Handled outside the editor, by the browser or the search box: listed, never bound. */
  native?: true;
  typed?: string;
  enabled: (context: Context) => boolean;
  active?: (context: Context) => boolean;
  run: (context: Context) => void;
  /** The same command at a size the user picks, where a view can offer the choice. */
  sized?: (context: Context, rows: number, columns: number) => void;
  /** A menu's submenu of the commands of a group, or of groups between separators, which the
   * command itself only opens. */
  sub?: Group | readonly Group[];
  /** Why it is disabled, shown beside it, where that is not the place or the state. */
  why?: MessageKey;
}

export const TEXT = ['text'] as const;
export const TABLE = ['table'] as const;
export const IMAGE = ['image'] as const;
export const PDF = ['pdf'] as const;
export const CHART = ['chart'] as const;
export const NOTE = ['note'] as const;
export const PROSE = ['text', 'table'] as const;
export const WRITTEN = ['text', 'note', 'table', 'part'] as const;
export const PLACED = ['text', 'image', 'pdf', 'table', 'part'] as const;
export const ANYWHERE = ['text', 'table', 'image', 'pdf', 'chart', 'note', 'part'] as const;
/** Where proposals are kept: not in a header or footer, which the review does not reach. */
export const PROPOSING = ['text', 'table', 'image', 'pdf', 'chart', 'note'] as const;
export const PART = ['part'] as const;
/** Where the ruler shows the paragraph's indents and stops. */
export const PARAGRAPHS: readonly Where[] = ['text', 'note', 'part'];

export function editing(check: (context: Context) => boolean = () => true) {
  return (context: Context) => context.view.editable && check(context);
}

export function later(context: Context, work: Promise<void>): void {
  work.catch(context.fail);
}

/** The column a command on a table applies to: of selected cells the anchor's, else the
 * cursor's. */
export function columnOf(view: EditorView, target: Target): string {
  const { selection } = view.state;
  return selection instanceof CellRange
    ? selection.anchorKey.split(':')[1]
    : target.table.lines!.cols[target.rect.left];
}
