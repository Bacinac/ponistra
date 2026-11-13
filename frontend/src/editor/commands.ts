import {
  ArrowDownAZ,
  ArrowDownZA,
  ChevronsDown,
  ChevronsRight,
  Banknote,
  Baseline,
  BetweenHorizontalEnd,
  BetweenHorizontalStart,
  BetweenVerticalEnd,
  BetweenVerticalStart,
  Binary,
  Bold,
  Calendar,
  CalendarClock,
  Captions,
  CaseSensitive,
  ChartColumn,
  ClipboardPaste,
  ClipboardType,
  Clock,
  Copy,
  CopyPlus,
  CornerUpLeft,
  DecimalsArrowRight,
  Eye,
  EyeOff,
  ExternalLink,
  Funnel,
  FunnelPlus,
  FunnelX,
  Files,
  FilePenLine,
  FileStack,
  FileText,
  Grid2x2,
  Hash,
  Heading1,
  Heading2,
  Heading3,
  Heading4,
  Highlighter,
  PaintBucket,
  ImagePlus,
  Italic,
  Keyboard,
  LayoutTemplate,
  Columns2,
  Columns3,
  Link,
  Link2,
  List,
  ListTodo,
  LocateFixed,
  ListChecks,
  ListEnd,
  ListIndentDecrease,
  ListIndentIncrease,
  ListMinus,
  ListOrdered,
  ListRestart,
  ListTree,
  MessageSquarePlus,
  MonitorPlay,
  NotebookPen,
  PanelBottom,
  PanelLeft,
  PanelRight,
  PanelTop,
  PencilLine,
  Pin,
  PinOff,
  RectangleHorizontal,
  Percent,
  Pilcrow,
  Play,
  Redo2,
  Replace,
  RemoveFormatting,
  Rows3,
  Rows4,
  Ruler,
  Scissors,
  Search,
  Section,
  SeparatorHorizontal,
  Minus,
  SlidersHorizontal,
  Square,
  SquareSplitVertical,
  ArrowRightToLine,
  Sigma,
  SquareMinus,
  Strikethrough,
  Subscript,
  Superscript,
  Table2,
  TableCellsMerge,
  TableCellsSplit,
  TableOfContents,
  Tag,
  TextAlignCenter,
  TextAlignEnd,
  TextAlignJustify,
  TextAlignStart,
  TextSearch,
  Trash2,
  Type,
  type LucideIcon,
  Underline,
  Undo2,
  X,
} from 'lucide-react';
import { toggleMark } from 'prosemirror-commands';
import { Fragment, Mark, Slice, type MarkType, type Node } from 'prosemirror-model';
import { EditorState, NodeSelection, type Command } from 'prosemirror-state';
import type { EditorView } from 'prosemirror-view';
import type {} from '../comments';
import type { MessageKey } from '../i18n/hr';
import type {} from './grids';
import type { Choice } from '../palette';
import {} from '../api';
import { focusSearch } from '../search';
import { focusNameBox, selectedQuery } from './NameBox';
import { endsIn, indent, insertBreak, reshape, retype, shortId, textblocks } from './blocks';
import { clipboardReady, copySelection, cutSelection, pasteInto } from './clipboard';
import { insertContents } from './contents';
import { inPart, insertField } from './parts';
import { HIGHLIGHTS, onScreen, TEXT_COLORS, type Palette, type Swatch } from './colors';
import { endMarksOf, marksAt, restyleEnds } from './ends';
import { selectedChart } from './charts';
import { selectedImage, type ImageHost } from './images';
import { selectedPdf } from './pdfs';
import { canLink } from './links';
import { FORMS, sameLevel, sample, type ListLevel, type Marked } from './forms';
import { continuable, continuedFormat, formAt, inList, listAt, reform, toggleList } from './lists';
import { commentable, draftOf } from './comments';
import { insertNote, noteOf, openSelected } from './notes';
import { numberedBy } from './numbering';
import { formats } from './proposals';
import {
  ALIGNMENTS,
  LEVELS,
  listOf,
  pdfUrl,
  schema,
  type Alignment,
  type FieldKind,
  type ListKind,
} from './schema';
import { SIZES, slideAt, speakerNotes, type Size } from './slides';
import { offeredCommands } from './actions';
import {
  ANYWHERE,
  CHART,
  columnOf,
  editing,
  IMAGE,
  later,
  NOTE,
  PARAGRAPHS,
  PART,
  PDF,
  PLACED,
  PROPOSING,
  PROSE,
  TABLE,
  TEXT,
  WRITTEN,
  type Context,
  type EditorCommand,
  type Group,
  type Slides,
  type Where,
} from './command';
import {
  blockOf,
  KIND_LABELS,
  kindOf,
  ownStyles,
  styleOf,
  type Kind,
  type Styling,
} from './styling';
import { PRESETS, presetCode, type Preset } from './formats';
import { CATALOGUE, designsIn, NEW, ours, SWITCHES, type Switch } from './design';
import type { Axis, Part } from './tables';
import { CellRange, cellOf, focusedCell, type RangeEdit } from './tableBase';
import { pastedTables, rangeEdit, refocusCell, targetOf, type Target } from './tablesPlugin';

const { paragraph, title, subtitle, heading, table } = schema.nodes;
const { strong, em, underline, strike, sub, sup } = schema.marks;

/** A tab, which runs to the paragraph's next stop, as Word's Tab key writes one. */
const insertTab: Command = (state, dispatch) => {
  if (!state.selection.$from.parent.inlineContent) return false;
  dispatch?.(state.tr.insertText('\t').scrollIntoView());
  return true;
};

function hasTable(state: EditorState): boolean {
  let found = false;
  state.doc.forEach((node) => (found ||= node.type === schema.nodes.table));
  return found;
}

function canInsertChart(state: EditorState): boolean {
  const index = state.selection.$from.index(0);
  return state.doc.canReplaceWith(index, index, schema.nodes.chart);
}

/** Puts a table of empty cells in place of the selection, and the cursor in its first cell once
 * the server has made its grid. */
export function insertTable(rows = 3, columns = 3): Command {
  return (state, dispatch, view) => {
    const { $from } = state.selection;
    const index = $from.index(0);
    if (!state.doc.canReplaceWith(index, index, table)) return false;
    if (dispatch && view) {
      const lines: Part = {
        rows: Array.from({ length: rows }, shortId),
        cols: Array.from({ length: columns }, shortId),
      };
      const made = table.create({ grid: lines, designs: [ours(NEW)] });
      pastedTables(view, new Slice(Fragment.from(made), 0, 0), true);
    }
    return true;
  };
}

function prose(command: Command): Pick<EditorCommand, 'enabled' | 'run'> {
  return {
    enabled: editing((context) => command(context.view.state)),
    run: ({ view }) => command(view.state, view.dispatch, view),
  };
}

const formattedEdits = new WeakMap<EditorState, RangeEdit | null>();

function edited(view: EditorView): RangeEdit | null {
  const kept = formattedEdits.get(view.state);
  if (kept !== undefined) return kept;
  const found = rangeEdit(view);
  formattedEdits.set(view.state, found);
  return found;
}

/** The state the formatting commands read: the text's, or a range of cells' as their own editor
 * holds them, none while any of their rows is not held. */
function formatted(view: EditorView): EditorState | null {
  const { state } = view;
  return state.selection instanceof CellRange ? (edited(view)?.state ?? null) : state;
}

/** A command on the text, or on a range of cells as their own editor holds them, whose result
 * goes back to the grid; on whole rows or columns, only one they can take. */
function formatting(command: Command): Pick<EditorCommand, 'enabled' | 'run'> {
  return {
    enabled: editing(({ view }) => {
      if (!(view.state.selection instanceof CellRange)) return command(view.state);
      const edit = edited(view);
      if (!edit?.fits) return edit !== null && command(edit.state);
      let fits = false;
      command(edit.state, (made) => {
        fits = made.docChanged && edit.fits!(made.doc);
      });
      return fits;
    }),
    run: (context) => {
      const { view } = context;
      if (!(view.state.selection instanceof CellRange)) {
        return command(view.state, view.dispatch, view);
      }
      const edit = rangeEdit(view);
      return (
        edit !== null &&
        command(edit.state, (made) => {
          if (!made.docChanged) return;
          const done = edit.apply(made.doc);
          if (done) later(context, done);
        })
      );
    },
  };
}

function textHas(state: EditorState, type: MarkType): boolean {
  return state.selection.ranges.some(({ $from, $to }) =>
    state.doc.rangeHasMark($from.pos, $to.pos, type),
  );
}

function markActive(state: EditorState, type: MarkType): boolean {
  if (state.selection.empty) return Boolean(type.isInSet(marksAt(state)));
  return textHas(state, type) || endsIn(state).some(({ node }) => type.isInSet(endMarksOf(node)));
}

/** A mark given to text, or taken from it, the empty paragraphs among it keep at their end. */
function toggled(type: MarkType): Command {
  const plain = toggleMark(type);
  return (state, dispatch, view) => {
    const ends = endsIn(state);
    if (!ends.length) return plain(state, dispatch, view);
    if (dispatch) {
      const add = !markActive(state, type);
      const change = (marks: readonly Mark[]) =>
        add ? type.create().addToSet(marks) : type.removeFromSet(marks);
      let tr = state.tr;
      if (state.selection.empty) tr.setStoredMarks(change(marksAt(state)));
      // Over text with none of the mark, where only an end has it, there is nothing to take.
      else if (add || textHas(state, type)) plain(state, (made) => (tr = made), view);
      restyleEnds(tr, ends, change);
      dispatch(tr.scrollIntoView());
    }
    return true;
  };
}

function marked(type: MarkType): Pick<EditorCommand, 'active' | 'enabled' | 'run'> {
  return {
    active: ({ view }) => {
      const state = formatted(view);
      return state !== null && markActive(state, type);
    },
    ...formatting(toggled(type)),
  };
}

function colorsOf(state: EditorState, type: MarkType): Set<string | null> {
  const colorOf = (marks: readonly Mark[]) => type.isInSet(marks)?.attrs.color ?? null;
  if (state.selection.empty) return new Set([colorOf(marksAt(state))]);
  const found = new Set<string | null>();
  for (const { $from, $to } of state.selection.ranges) {
    state.doc.nodesBetween($from.pos, $to.pos, (node) => {
      if (node.isText) found.add(colorOf(node.marks));
    });
  }
  for (const { node } of endsIn(state)) found.add(colorOf(endMarksOf(node)));
  return found;
}

function paint(type: MarkType, name: string | null): Command {
  return (state, dispatch) => {
    if (dispatch) {
      const tr = state.tr;
      const mark = name ? type.create({ color: name }) : null;
      const change = (marks: readonly Mark[]) =>
        mark ? mark.addToSet(marks) : type.removeFromSet(marks);
      if (state.selection.empty) {
        tr.setStoredMarks(change(marksAt(state)));
      } else {
        for (const { $from, $to } of state.selection.ranges) {
          tr.removeMark($from.pos, $to.pos, type);
          if (mark) tr.addMark($from.pos, $to.pos, mark);
        }
      }
      restyleEnds(tr, endsIn(state), change);
      dispatch(tr.scrollIntoView());
    }
    return true;
  };
}

function palette(
  family: 'color' | 'highlight',
  swatches: Palette,
  none: MessageKey,
  icon: LucideIcon,
): EditorCommand[] {
  const type = schema.marks[family];
  const entries: [string | null, Swatch | null][] = [[null, null], ...Object.entries(swatches)];
  return entries.map(([name, swatch]) => ({
    id: `${family}.${name ?? 'none'}`,
    label: `command.${family}`,
    detail: name ? (`color.${name}` as MessageKey) : none,
    icon,
    swatch: swatch ? onScreen(swatch) : undefined,
    group: family,
    where: WRITTEN,
    active: ({ view }) => {
      const state = formatted(view);
      const found = state ? colorsOf(state, type) : new Set();
      return found.size === 1 && found.has(name);
    },
    ...formatting(paint(type, name)),
  }));
}

function fills(): EditorCommand[] {
  const entries: [string | null, Swatch | null][] = [[null, null], ...Object.entries(HIGHLIGHTS)];
  return entries.map(([name, swatch]) => ({
    id: `fill.${name ?? 'none'}`,
    label: 'command.fill',
    detail: name ? (`color.${name}` as MessageKey) : 'color.none',
    icon: PaintBucket,
    swatch: swatch ? onScreen(swatch) : undefined,
    group: 'fill',
    where: TABLE,
    active: ({ view }) => {
      const target = targetOf(view);
      return target !== null && target.table.fillAt(target.rect) === name;
    },
    ...onTable(
      () => true,
      ({ table, rect }) => table.setFill(rect, name),
    ),
  }));
}

function selectedFigure(state: EditorState): { node: Node; pos: number } | null {
  return selectedImage(state) ?? selectedPdf(state);
}

function aligned(align: Alignment): Pick<EditorCommand, 'active' | 'enabled' | 'run'> {
  const value = align === 'left' ? null : align;
  const { run } = formatting(reshape((attrs) => (attrs.align === value ? null : { align: value })));
  return {
    active: ({ view }) => {
      const picked = selectedFigure(view.state);
      if (picked) return picked.node.attrs.align === value;
      const state = formatted(view);
      const blocks = state ? textblocks(state) : [];
      return blocks.length > 0 && blocks.every(({ node }) => node.attrs.align === value);
    },
    enabled: editing(({ view }) => {
      if (selectedFigure(view.state)) return align !== 'justify';
      const state = formatted(view);
      return state !== null && textblocks(state).length > 0;
    }),
    run: (context) => {
      const picked = selectedFigure(context.view.state);
      if (!picked) run(context);
      else
        context.view.dispatch(context.view.state.tr.setNodeAttribute(picked.pos, 'align', value));
    },
  };
}

function listed(kind: ListKind): Pick<EditorCommand, 'active' | 'enabled' | 'run'> {
  return {
    active: ({ view }) => inList(view.state, kind),
    ...formatting(toggleList(kind)),
  };
}

function formed(kind: Marked, form: ListLevel): Pick<EditorCommand, 'active' | 'enabled' | 'run'> {
  return {
    active: ({ view, lists }) => {
      const shown = formAt(view.state, lists.get(), kind);
      return shown !== null && sameLevel(shown, form);
    },
    enabled: editing(({ view, lists }) => reform(lists, form)(view.state)),
    run: ({ view, lists }) => reform(lists, form)(view.state, view.dispatch),
  };
}

function forms(kind: Marked): EditorCommand[] {
  return Object.entries(FORMS[kind]).map(([name, form]) => ({
    id: `${kind}Form.${name}`,
    label: kind === 'number' ? 'command.numberForm' : 'command.bulletForm',
    sample: sample(form),
    icon: kind === 'number' ? ListOrdered : List,
    group: kind === 'number' ? 'numberForm' : 'bulletForm',
    where: PROSE,
    ...formed(kind, form),
  }));
}

/** The block at the cursor, where its list or its style numbers it. */
function numberedAt({ view, styling }: Context): { pos: number; node: Node } | null {
  const { $from } = view.state.selection;
  if ($from.depth < 1) return null;
  const node = $from.node(1);
  const numbered = listOf(node) === 'number' || numberedBy(node, styling) !== null;
  return numbered ? { pos: $from.before(1), node } : null;
}

const restarting: Pick<EditorCommand, 'enabled' | 'run'> = {
  enabled: editing((context) => numberedAt(context)?.node.attrs.restart === false),
  run: (context) => {
    const at = numberedAt(context);
    if (!at) return;
    const { view } = context;
    const tr = view.state.tr.setNodeAttribute(at.pos, 'restart', true);
    if (at.node.attrs.continued === true) tr.setNodeAttribute(at.pos, 'continued', false);
    view.dispatch(tr);
  },
};

/** The number counts on: past its own restart, and past the blocks since its list's last item. */
const continuing: Pick<EditorCommand, 'enabled' | 'run'> = {
  enabled: editing((context) => {
    const at = numberedAt(context);
    if (!at) return false;
    return at.node.attrs.restart === true || continuable(context.view.state.doc.content, at.pos);
  }),
  run: (context) => {
    const at = numberedAt(context);
    if (!at) return;
    const { view } = context;
    const tr = view.state.tr.setNodeAttribute(at.pos, 'restart', false);
    if (continuable(tr.doc.content, at.pos)) {
      tr.setNodeAttribute(at.pos, 'continued', true).setNodeAttribute(
        at.pos,
        'format',
        continuedFormat(tr.doc, at.pos),
      );
    }
    view.dispatch(tr);
  },
};

/** The top-level block the selection or cell is in, or the note being written. */
function blockId({ view }: Context): string | null {
  const note = noteOf(view);
  if (note) return note.id;
  const { selection } = view.state;
  const node = selection instanceof NodeSelection ? selection.node : selection.$from.node(1);
  return node?.attrs.id ?? null;
}

export function imageHost({ place, fail, label }: Context): ImageHost {
  return { document: place.document, fail, label };
}

function blockLink(context: Context): string {
  const query = selectedQuery(context) ?? new URLSearchParams({ block: blockId(context)! });
  return `${location.origin}${context.place.address}?${query}`;
}

function indented(step: 1 | -1): Pick<EditorCommand, 'enabled' | 'run'> {
  return formatting(indent(step));
}

/** Formatting, not meaning: a link stays a link, a proposal a proposal and an item keeps its
 * level. */
const clearFormatting: Command = (state, dispatch) => {
  const { empty, ranges } = state.selection;
  const anyFormat = (marks: readonly Mark[]) => marks.some((mark) => formats(mark.type.name));
  const ends = endsIn(state).filter(({ node }) => endMarksOf(node).length);
  let marks = (empty && anyFormat(marksAt(state))) || ends.length > 0;
  for (const { $from, $to } of empty ? [] : ranges) {
    state.doc.nodesBetween($from.pos, $to.pos, (node) => {
      marks ||= node.isText && anyFormat(node.marks);
    });
  }
  const laidOut = textblocks(state).filter(
    ({ node }) =>
      node.attrs.align ||
      node.attrs.firstLine ||
      node.attrs.right ||
      node.attrs.tabs ||
      (node.attrs.indent && !listOf(node)),
  );
  if (!marks && !laidOut.length) return false;
  if (dispatch) {
    const tr = state.tr;
    if (empty) tr.setStoredMarks([]);
    for (const range of ranges) {
      for (const type of Object.values(schema.marks)) {
        if (formats(type.name)) tr.removeMark(range.$from.pos, range.$to.pos, type);
      }
    }
    restyleEnds(tr, ends, () => Mark.none);
    for (const { pos, node } of laidOut) {
      tr.setNodeAttribute(pos, 'align', null)
        .setNodeAttribute(pos, 'firstLine', null)
        .setNodeAttribute(pos, 'right', null)
        .setNodeAttribute(pos, 'tabs', null);
      if (!listOf(node)) tr.setNodeAttribute(pos, 'indent', null);
    }
    dispatch(tr);
  }
  return true;
};

const ALIGN_ICONS = [TextAlignStart, TextAlignCenter, TextAlignEnd, TextAlignJustify];
const ALIGN_KEYS = ['Shift-Mod-l', 'Shift-Mod-e', 'Shift-Mod-r', 'Shift-Mod-j'];

const DESIGN_ICONS: Record<string, LucideIcon> = {
  grid: Grid2x2,
  lines: Rows3,
  bands: Rows4,
  header: PanelTop,
  plain: Square,
};

const PART_ICONS: Record<Switch, LucideIcon> = {
  header: PanelTop,
  totals: PanelBottom,
  firstColumn: PanelLeft,
  lastColumn: PanelRight,
  rowBands: Rows3,
  columnBands: Columns3,
};

function onTable(
  check: (target: Target) => boolean,
  act: (target: Target) => void | Promise<void>,
): Pick<EditorCommand, 'enabled' | 'run'> {
  return {
    enabled: editing(({ view }) => {
      const target = targetOf(view);
      return target !== null && check(target);
    }),
    run: (context) => {
      const target = targetOf(context.view);
      const done = target && act(target);
      if (done) later(context, done);
    },
  };
}

function addLine(axis: Axis, after: boolean): Pick<EditorCommand, 'enabled' | 'run'> {
  return onTable(
    () => true,
    ({ table, rect }) => {
      const [first, last] = axis === 'rows' ? [rect.top, rect.bottom] : [rect.left, rect.right];
      return table.addLine(axis, after ? last + 1 : first);
    },
  );
}

function removeLines(axis: Axis): Pick<EditorCommand, 'enabled' | 'run'> {
  const span = ({ rect }: Target) =>
    axis === 'rows' ? [rect.top, rect.bottom] : [rect.left, rect.right];
  return onTable(
    (target) => {
      const [first, last] = span(target);
      const lines = target.table.lines;
      const count = !lines ? 0 : axis === 'rows' ? lines.rowCount : lines.cols.length;
      return last - first + 1 < count;
    },
    (target) => {
      const [first, last] = span(target);
      return target.table.deleteLines(axis, first, last);
    },
  );
}

/** Sorts the selected rows, or the table's under its header, by the column the cursor is in;
 * the server compares the values as Excel sorts them in the document's language. */
function sortBy(descending: boolean): Pick<EditorCommand, 'enabled' | 'run'> {
  return {
    enabled: editing(({ view, place }) => {
      const target = targetOf(view);
      return place.tab !== null && (target?.table.lines?.rowCount ?? 0) > 1;
    }),
    run: (context) => {
      const target = targetOf(context.view);
      if (!target || !context.place.tab) return;
      const { table, rect, range } = target;
      const col = columnOf(context.view, target);
      const rows: [number, number] | null =
        range && rect.bottom > rect.top ? [rect.top, rect.bottom] : null;
      later(context, table.sort(col, descending, rows));
    },
  };
}

const PRESET_ICONS: Record<Preset, LucideIcon> = {
  number: DecimalsArrowRight,
  integer: Binary,
  currency: Banknote,
  percent: Percent,
  scientific: Sigma,
  date: Calendar,
  time: Clock,
  dateTime: CalendarClock,
};

function several(cells: Iterator<unknown>): boolean {
  return !cells.next().done && !cells.next().done;
}

function spanned(target: Target): boolean {
  return [...target.table.layout.cellsIn(target.rect)].some(
    (cell) => cell.rows > 1 || cell.cols > 1,
  );
}

const HEADINGS = [Heading1, Heading2, Heading3, Heading4];
const STYLE_ICONS: Record<Kind, LucideIcon> = {
  text: Pilcrow,
  title: Type,
  subtitle: Type,
  h1: Heading1,
  h2: Heading2,
  h3: Heading3,
  h4: Heading4,
};

function styled(kind: Kind, id: string | null = null): (context: Context) => boolean {
  return ({ view, styling }) => {
    const parent = view.state.selection.$from.parent;
    return kindOf(parent) === kind && styleOf(parent, styling) === id;
  };
}

const FIELD_COMMANDS: readonly (readonly [FieldKind, MessageKey, LucideIcon])[] = [
  ['page', 'field.page', Hash],
  ['pages', 'field.pages', Files],
  ['title', 'field.title', Type],
  ['date', 'field.date', Calendar],
];

export const COMMANDS: readonly EditorCommand[] = [
  {
    id: 'history.undo',
    label: 'command.undo',
    icon: Undo2,
    group: 'history',
    where: ANYWHERE,
    keys: ['Mod-z'],
    enabled: editing((context) => context.history.canUndo()),
    run: (context) => context.history.undo(),
  },
  {
    id: 'history.redo',
    label: 'command.redo',
    icon: Redo2,
    group: 'history',
    where: ANYWHERE,
    keys: ['Mod-y', 'Shift-Mod-z'],
    enabled: editing((context) => context.history.canRedo()),
    run: (context) => context.history.redo(),
  },
  {
    id: 'style.paragraph',
    label: 'command.paragraph',
    icon: Pilcrow,
    group: 'style',
    where: PROSE,
    active: styled('text'),
    ...formatting(retype(paragraph)),
  },
  {
    id: 'style.title',
    label: 'command.title',
    icon: Type,
    group: 'style',
    where: PROSE,
    active: styled('title'),
    ...formatting(retype(title)),
  },
  {
    id: 'style.subtitle',
    label: 'command.subtitle',
    icon: Type,
    group: 'style',
    where: PROSE,
    active: styled('subtitle'),
    ...formatting(retype(subtitle)),
  },
  ...LEVELS.map((level): EditorCommand => ({
    id: `style.heading${level}`,
    label: `command.heading${level}`,
    icon: HEADINGS[level - 1],
    group: 'style',
    where: PROSE,
    typed: `${'#'.repeat(level)} `,
    active: styled(`h${level}`),
    ...formatting(retype(heading, { level })),
  })),
  {
    id: 'format.bold',
    label: 'command.bold',
    icon: Bold,
    group: 'format',
    where: WRITTEN,
    keys: ['Mod-b'],
    ...marked(strong),
  },
  {
    id: 'format.italic',
    label: 'command.italic',
    icon: Italic,
    group: 'format',
    where: WRITTEN,
    keys: ['Mod-i'],
    ...marked(em),
  },
  {
    id: 'format.underline',
    label: 'command.underline',
    icon: Underline,
    group: 'format',
    where: WRITTEN,
    keys: ['Mod-u'],
    ...marked(underline),
  },
  {
    id: 'format.strike',
    label: 'command.strike',
    icon: Strikethrough,
    group: 'format',
    where: WRITTEN,
    keys: ['Shift-Mod-x'],
    ...marked(strike),
  },
  {
    id: 'format.clear',
    label: 'command.clearFormatting',
    icon: RemoveFormatting,
    group: 'format',
    where: WRITTEN,
    keys: ['Mod-Space', 'Mod-\\'],
    ...formatting(clearFormatting),
  },
  {
    id: 'script.sub',
    label: 'command.subscript',
    icon: Subscript,
    group: 'script',
    where: WRITTEN,
    keys: ['Mod-,'],
    ...marked(sub),
  },
  {
    id: 'script.sup',
    label: 'command.superscript',
    icon: Superscript,
    group: 'script',
    where: WRITTEN,
    keys: ['Mod-.'],
    ...marked(sup),
  },
  ...palette('color', TEXT_COLORS, 'color.auto', Baseline),
  ...palette('highlight', HIGHLIGHTS, 'color.none', Highlighter),
  ...fills(),
  ...ALIGNMENTS.map((align, index): EditorCommand => ({
    id: `align.${align}`,
    label: `command.align${align[0].toUpperCase()}${align.slice(1)}` as MessageKey,
    icon: ALIGN_ICONS[index],
    group: 'align',
    where: PLACED,
    keys: [ALIGN_KEYS[index]],
    ...aligned(align),
  })),
  {
    id: 'list.bullet',
    label: 'command.bulletList',
    icon: List,
    group: 'list',
    where: PROSE,
    keys: ['Shift-Mod-8'],
    typed: '- ',
    ...listed('bullet'),
  },
  {
    id: 'list.number',
    label: 'command.numberList',
    icon: ListOrdered,
    group: 'list',
    where: PROSE,
    keys: ['Shift-Mod-7'],
    typed: '1. ',
    ...listed('number'),
  },
  {
    id: 'list.check',
    label: 'command.checkList',
    icon: ListChecks,
    group: 'list',
    where: PROSE,
    keys: ['Shift-Mod-9'],
    typed: '[] ',
    ...listed('check'),
  },
  ...forms('number'),
  ...forms('bullet'),
  {
    id: 'list.format',
    label: 'command.listFormat',
    icon: ListTree,
    group: 'numbering',
    where: PROSE,
    enabled: editing(({ view }) => listAt(view.state) !== null),
    run: (context) => context.open('listFormat'),
  },
  {
    id: 'numbering.restart',
    label: 'command.numberRestart',
    icon: ListRestart,
    group: 'numbering',
    where: TEXT,
    ...restarting,
  },
  {
    id: 'numbering.continue',
    label: 'command.numberContinue',
    icon: ListOrdered,
    group: 'numbering',
    where: TEXT,
    ...continuing,
  },
  {
    id: 'indent.less',
    label: 'command.indentLess',
    icon: ListIndentDecrease,
    group: 'indent',
    where: PROSE,
    keys: ['Shift-Mod-m'],
    ...indented(-1),
  },
  {
    id: 'indent.more',
    label: 'command.indentMore',
    icon: ListIndentIncrease,
    group: 'indent',
    where: PROSE,
    keys: ['Mod-m'],
    ...indented(1),
  },
  {
    id: 'paragraph.tabs',
    label: 'command.tabStops',
    icon: Ruler,
    group: 'paragraph',
    where: PARAGRAPHS,
    enabled: editing(({ view }) => textblocks(view.state).length > 0),
    run: (context) => context.open('tabStops'),
  },
  {
    id: 'insert.image',
    label: 'command.image',
    icon: ImagePlus,
    group: 'insert',
    where: PROSE,
    enabled: editing(),
    run: (context) => context.open('image'),
  },
  {
    id: 'insert.pdf',
    label: 'command.pdf',
    icon: FileText,
    group: 'insert',
    where: TEXT,
    enabled: editing(),
    run: (context) => context.open('pdf'),
  },
  {
    id: 'insert.link',
    label: 'command.link',
    icon: Link,
    group: 'insert',
    where: WRITTEN,
    keys: ['Mod-k'],
    enabled: editing(({ view }) => canLink(view.state)),
    run: (context) => context.open('link'),
  },
  {
    id: 'insert.table',
    label: 'command.table',
    icon: Table2,
    group: 'insert',
    where: TEXT,
    enabled: editing(({ view }) => insertTable()(view.state)),
    run: ({ view }) => insertTable()(view.state, view.dispatch, view),
    sized: ({ view }, rows, columns) => insertTable(rows, columns)(view.state, view.dispatch, view),
  },
  {
    id: 'insert.chart',
    label: 'command.chart',
    icon: ChartColumn,
    group: 'insert',
    where: TEXT,
    enabled: editing(({ view }) => hasTable(view.state) && canInsertChart(view.state)),
    run: (context) => context.open('chart'),
  },
  {
    id: 'insert.contents',
    label: 'command.contents',
    icon: TableOfContents,
    group: 'insert',
    where: PROSE,
    ...prose(insertContents),
  },
  {
    id: 'insert.horizontalRule',
    label: 'command.horizontalRule',
    icon: Minus,
    group: 'insert',
    where: TEXT,
    ...prose(insertBreak(schema.nodes.horizontalRule)),
  },
  {
    id: 'insert.pageBreak',
    label: 'command.pageBreak',
    icon: SeparatorHorizontal,
    group: 'insert',
    where: TEXT,
    keys: ['Mod-Enter'],
    ...prose(insertBreak(schema.nodes.pageBreak)),
  },
  {
    id: 'insert.sectionBreak',
    label: 'command.sectionBreak',
    icon: Section,
    group: 'insert',
    where: TEXT,
    ...prose(insertBreak(schema.nodes.sectionBreak)),
  },
  {
    id: 'insert.slideBreak',
    label: 'command.slideBreak',
    icon: SquareSplitVertical,
    group: 'insert',
    where: TEXT,
    ...prose(insertBreak(schema.nodes.slideBreak)),
  },
  {
    id: 'insert.columnBreak',
    label: 'command.columnBreak',
    icon: Columns2,
    group: 'insert',
    where: TEXT,
    keys: ['Shift-Mod-Enter'],
    ...prose(insertBreak(schema.nodes.columnBreak)),
  },
  {
    id: 'insert.speakerNotes',
    label: 'command.speakerNotes',
    icon: NotebookPen,
    group: 'insert',
    where: TEXT,
    ...prose(speakerNotes),
  },
  {
    id: 'insert.tab',
    label: 'command.tab',
    icon: ArrowRightToLine,
    group: 'insert',
    where: ['text', 'part'],
    keys: ['Tab'],
    ...prose(insertTab),
  },
  ...(['header', 'footer'] as const).map((side): EditorCommand => ({
    id: `insert.${side}`,
    label: `command.${side}`,
    icon: side === 'header' ? PanelTop : PanelBottom,
    group: 'insert',
    where: TEXT,
    enabled: editing(({ parts }) => parts !== null),
    run: ({ parts }) => parts?.open(side),
  })),
  ...FIELD_COMMANDS.map(([kind, label, icon]): EditorCommand => ({
    id: `insert.field.${kind}`,
    label,
    icon,
    group: 'insert',
    where: PART,
    ...prose(insertField(kind)),
  })),
  ...(['foot', 'end'] as const).map((kind): EditorCommand => ({
    id: `insert.${kind}note`,
    label: `command.${kind}note`,
    icon: kind === 'foot' ? PanelBottom : ListEnd,
    group: 'insert',
    where: TEXT,
    ...prose(insertNote(kind)),
  })),
  {
    id: 'review.suggest',
    label: 'command.suggest',
    icon: FilePenLine,
    group: 'review',
    where: PROPOSING,
    enabled: ({ view }) => view.editable,
    active: ({ suggesting }) => suggesting,
    run: ({ suggesting, suggest }) => suggest(!suggesting),
  },
  {
    id: 'comment.add',
    label: 'command.comment',
    icon: MessageSquarePlus,
    group: 'comment',
    where: TEXT,
    keys: ['Mod-Alt-m'],
    enabled: ({ view, desk, place }) => Boolean(desk && place.tab && commentable(view.state)),
    run: ({ view, desk, place }) => {
      const draft = draftOf(view.state);
      if (draft && desk && place.tab) desk.start({ tab: place.tab, ...draft });
    },
  },
  {
    id: 'task.add',
    label: 'command.task',
    icon: ListTodo,
    group: 'comment',
    where: TEXT,
    enabled: ({ view, place }) =>
      Boolean(place.tab) && view.state.selection.$from.parent.isTextblock,
    run: ({ open }) => open('task'),
  },
  {
    id: 'table.rowAbove',
    label: 'command.rowAbove',
    icon: BetweenHorizontalStart,
    group: 'table',
    where: TABLE,
    ...addLine('rows', false),
  },
  {
    id: 'table.rowBelow',
    label: 'command.rowBelow',
    icon: BetweenHorizontalEnd,
    group: 'table',
    where: TABLE,
    ...addLine('rows', true),
  },
  {
    id: 'table.columnLeft',
    label: 'command.columnLeft',
    icon: BetweenVerticalStart,
    group: 'table',
    where: TABLE,
    ...addLine('cols', false),
  },
  {
    id: 'table.columnRight',
    label: 'command.columnRight',
    icon: BetweenVerticalEnd,
    group: 'table',
    where: TABLE,
    ...addLine('cols', true),
  },
  {
    id: 'table.deleteRow',
    label: 'command.deleteRow',
    icon: ListMinus,
    group: 'table',
    where: TABLE,
    ...removeLines('rows'),
  },
  {
    id: 'table.deleteColumn',
    label: 'command.deleteColumn',
    icon: SquareMinus,
    group: 'table',
    where: TABLE,
    ...removeLines('cols'),
  },
  ...(['rows', 'cols'] as const).flatMap((axis): EditorCommand[] => {
    const name = axis === 'rows' ? 'Rows' : 'Columns';
    return [
      {
        id: `table.hide${name}`,
        label: `command.hide${name}`,
        icon: EyeOff,
        group: 'table',
        where: TABLE,
        ...onTable(
          ({ table, rect }) => table.hidesIn(axis, rect, false),
          ({ table, rect }) => table.hide(axis, rect, true),
        ),
      },
      {
        id: `table.show${name}`,
        label: `command.show${name}`,
        icon: Eye,
        group: 'table',
        where: TABLE,
        ...onTable(
          ({ table, rect }) => table.hidesIn(axis, rect, true),
          ({ table, rect }) => table.hide(axis, rect, false),
        ),
      },
    ];
  }),
  {
    id: 'table.merge',
    label: 'command.mergeCells',
    icon: TableCellsMerge,
    group: 'table',
    where: TABLE,
    ...onTable(
      ({ table, rect, range }) => range && several(table.layout.cellsIn(rect)),
      ({ table, rect }) => table.merge(rect),
    ),
  },
  {
    id: 'table.split',
    label: 'command.splitCell',
    icon: TableCellsSplit,
    group: 'table',
    where: TABLE,
    ...onTable(spanned, ({ table, rect }) => table.split(rect)),
  },
  {
    id: 'table.name',
    label: 'command.tableName',
    icon: Tag,
    group: 'table',
    where: TABLE,
    enabled: editing(({ view }) => targetOf(view) !== null),
    run: ({ open }) => open('tableName'),
  },
  {
    id: 'table.goTo',
    label: 'command.goTo',
    icon: LocateFixed,
    group: 'table',
    where: TABLE,
    keys: ['Mod-g'],
    enabled: ({ view }) => targetOf(view) !== null,
    run: ({ open }) => {
      if (!focusNameBox()) open('goTo');
    },
  },
  {
    id: 'table.design',
    label: 'command.tableDesign',
    icon: Grid2x2,
    group: 'table',
    where: TABLE,
    sub: ['tableDesign', 'tablePart'],
    ...onTable(
      () => true,
      () => {},
    ),
  },
  ...[...Object.keys(CATALOGUE), null].map((id): EditorCommand => ({
    id: `tableDesign.${id ?? 'plain'}`,
    label: 'command.tableDesign',
    detail: `tableDesign.${id ?? 'plain'}` as MessageKey,
    icon: DESIGN_ICONS[id ?? 'plain'] ?? Grid2x2,
    group: 'tableDesign',
    where: TABLE,
    active: ({ view }) => {
      const table = targetOf(view)?.table;
      if (!table) return false;
      return id === null ? !designsIn(table.node.attrs.designs) : table.ours === id;
    },
    ...onTable(
      () => true,
      ({ table }) => table.designIn(id),
    ),
  })),
  ...SWITCHES.map((part): EditorCommand => ({
    id: `tablePart.${part}`,
    label: 'command.tablePart',
    detail: `tablePart.${part}`,
    icon: PART_ICONS[part],
    group: 'tablePart',
    where: TABLE,
    active: ({ view }) => {
      const table = targetOf(view)?.table;
      return !!table && !!designsIn(table.node.attrs.designs)?.[0].on?.[part];
    },
    ...onTable(
      ({ table }) => designsIn(table.node.attrs.designs) !== null,
      ({ table }) => table.toggle(part),
    ),
  })),
  {
    id: 'table.freeze',
    label: 'command.freezeRows',
    icon: Pin,
    group: 'table',
    where: TABLE,
    ...onTable(
      ({ table, rect }) => rect.top > 0 && rect.top !== table.lines?.frozenRows(),
      ({ table, rect }) => table.freeze(rect.top),
    ),
  },
  {
    id: 'table.unfreeze',
    label: 'command.unfreezeRows',
    icon: PinOff,
    group: 'table',
    where: TABLE,
    ...onTable(
      ({ table }) => !!table.lines?.frozenRows(),
      ({ table }) => table.freeze(0),
    ),
  },
  {
    id: 'table.delete',
    label: 'command.deleteTable',
    icon: Trash2,
    group: 'table',
    where: TABLE,
    ...onTable(
      () => true,
      ({ table }) => table.remove(),
    ),
  },
  {
    id: 'table.sortAscending',
    label: 'command.sortAscending',
    icon: ArrowDownAZ,
    group: 'tableData',
    where: TABLE,
    ...sortBy(false),
  },
  {
    id: 'table.sortDescending',
    label: 'command.sortDescending',
    icon: ArrowDownZA,
    group: 'tableData',
    where: TABLE,
    ...sortBy(true),
  },
  {
    id: 'table.filter',
    label: 'command.filter',
    icon: Funnel,
    group: 'tableData',
    where: TABLE,
    enabled: ({ view }) => targetOf(view)?.table.filterable() ?? false,
    run: ({ view }) => {
      const target = targetOf(view);
      if (target) target.table.openFilter(columnOf(view, target));
    },
  },
  {
    id: 'table.filterByValue',
    label: 'command.filterByValue',
    icon: FunnelPlus,
    group: 'tableData',
    where: TABLE,
    enabled: ({ view }) => {
      const target = targetOf(view);
      return !!target?.table.filterable() && !target.range;
    },
    run: (context) => {
      const target = targetOf(context.view);
      if (target) later(context, target.table.filterByValue(target.rect.top, target.rect.left));
    },
  },
  {
    id: 'table.unfilter',
    label: 'command.unfilter',
    icon: FunnelX,
    group: 'tableData',
    where: TABLE,
    enabled: ({ view }) => {
      const table = targetOf(view)?.table;
      return !!table?.filterable() && !!table.lines?.filter.length;
    },
    run: (context) => {
      const target = targetOf(context.view);
      if (target) later(context, target.table.unfilter());
    },
  },
  {
    id: 'table.fillDown',
    label: 'command.fillDown',
    icon: ChevronsDown,
    group: 'tableData',
    where: TABLE,
    keys: ['Mod-d'],
    ...onTable(
      ({ table, rect }) => table.fillsOver(rect, 'rows'),
      ({ table, rect }) => table.fillOver(rect, 'rows'),
    ),
  },
  {
    id: 'table.fillRight',
    label: 'command.fillRight',
    icon: ChevronsRight,
    group: 'tableData',
    where: TABLE,
    keys: ['Mod-r'],
    ...onTable(
      ({ table, rect }) => table.fillsOver(rect, 'cols'),
      ({ table, rect }) => table.fillOver(rect, 'cols'),
    ),
  },
  {
    id: 'table.duplicateValues',
    label: 'command.duplicateValues',
    icon: CopyPlus,
    group: 'tableData',
    where: TABLE,
    enabled: editing(({ view }) => targetOf(view) !== null),
    run: (context) => targetOf(context.view)?.table.duplicateAsValues(),
  },
  {
    id: 'table.cellFormat',
    label: 'command.cellFormat',
    icon: Hash,
    group: 'tableData',
    where: TABLE,
    sub: 'cellFormat',
    ...onTable(
      () => true,
      () => {},
    ),
  },
  {
    id: 'table.fill',
    label: 'command.fill',
    icon: PaintBucket,
    group: 'tableData',
    where: TABLE,
    sub: 'fill',
    ...onTable(
      () => true,
      () => {},
    ),
  },
  {
    id: 'cellFormat.general',
    label: 'command.cellFormat',
    detail: 'cellFormat.general',
    icon: CaseSensitive,
    group: 'cellFormat',
    where: TABLE,
    ...onTable(
      () => true,
      ({ table, rect }) => table.setFormat(rect, null),
    ),
  },
  ...PRESETS.map((preset): EditorCommand => ({
    id: `cellFormat.${preset}`,
    label: 'command.cellFormat',
    detail: `cellFormat.${preset}`,
    icon: PRESET_ICONS[preset],
    group: 'cellFormat',
    where: TABLE,
    ...onTable(
      () => true,
      ({ table, rect }) => table.setFormat(rect, presetCode(preset, table.spec.locale())),
    ),
  })),
  {
    id: 'cellFormat.custom',
    label: 'command.cellFormat',
    detail: 'cellFormat.custom',
    icon: PencilLine,
    group: 'cellFormat',
    where: TABLE,
    enabled: editing(({ view }) => targetOf(view) !== null),
    run: ({ open }) => open('cellFormat'),
  },
  {
    id: 'note.back',
    label: 'command.noteBack',
    icon: CornerUpLeft,
    group: 'note',
    where: NOTE,
    keys: ['Escape'],
    enabled: () => true,
    run: ({ view }) => noteOf(view)?.back(),
  },
  ...(['foot', 'end'] as const).map((kind): EditorCommand => ({
    id: `note.to${kind === 'foot' ? 'Foot' : 'End'}`,
    label: kind === 'foot' ? 'command.toFootnote' : 'command.toEndnote',
    icon: kind === 'foot' ? PanelBottom : ListEnd,
    group: 'note',
    where: NOTE,
    enabled: editing(({ view }) => noteOf(view)?.kind !== kind),
    run: ({ view }) => noteOf(view)?.setKind(kind),
  })),
  {
    id: 'note.restart',
    label: 'command.notesRestart',
    icon: ListRestart,
    group: 'note',
    where: NOTE,
    enabled: editing(({ notes }) => !!notes && !notes.first && !notes.restart),
    run: ({ notes }) => notes?.setRestart(true),
  },
  {
    id: 'note.continue',
    label: 'command.notesContinue',
    icon: ListOrdered,
    group: 'note',
    where: NOTE,
    enabled: editing(({ notes }) => !!notes && notes.restart),
    run: ({ notes }) => notes?.setRestart(false),
  },
  {
    id: 'note.delete',
    label: 'command.deleteNote',
    icon: Trash2,
    group: 'note',
    where: NOTE,
    enabled: editing(),
    run: ({ view }) => noteOf(view)?.remove(),
  },
  {
    id: 'part.firstApart',
    label: 'command.firstApart',
    icon: FileStack,
    group: 'part',
    where: PART,
    active: ({ parts }) => Boolean(parts?.firstApart),
    enabled: editing(({ parts }) => parts !== null),
    run: ({ parts }) => parts?.setFirstApart(!parts.firstApart),
  },
  {
    id: 'part.linked',
    label: 'command.partLinked',
    icon: Link2,
    group: 'part',
    where: PART,
    active: ({ parts }) => parts?.linked === true,
    enabled: editing(({ parts }) => parts !== null && parts.linked !== null),
    run: ({ parts }) => parts?.setLinked(!parts.linked),
  },
  {
    id: 'slide.hide',
    label: 'command.hideSlide',
    icon: EyeOff,
    group: 'slide',
    where: TEXT,
    active: ({ view }) => slideAt(view.state.doc, view.state.selection.from)?.hidden === true,
    enabled: editing(({ slides, view }) => slides !== null && startOf(view) !== null),
    run: ({ view }) => {
      const start = startOf(view);
      if (start) {
        view.dispatch(
          view.state.tr.setNodeAttribute(start.pos, 'hidden', !start.node.attrs.hidden),
        );
      }
    },
  },
  {
    id: 'slide.present',
    label: 'command.present',
    icon: Play,
    group: 'slide',
    where: ANYWHERE,
    enabled: ({ present }) => present !== null,
    run: ({ present }) => present?.('cursor'),
  },
  {
    id: 'slide.present.start',
    label: 'command.presentStart',
    icon: MonitorPlay,
    group: 'slide',
    where: ANYWHERE,
    enabled: ({ present }) => present !== null,
    run: ({ present }) => present?.('start'),
  },
  ...(['wide', 'standard'] as const).map((size): EditorCommand => ({
    id: `slide.size.${size}`,
    label: `command.slideSize.${size}`,
    icon: size === 'wide' ? RectangleHorizontal : Square,
    group: 'slideSize',
    where: TEXT,
    active: ({ slides }) => Boolean(slides && sameSize(slides.template.size, SIZES[size])),
    enabled: editing(({ slides }) => slides !== null),
    run: ({ slides }) => slides?.setSize(SIZES[size]),
  })),
  {
    id: 'part.close',
    label: 'command.closePart',
    icon: X,
    group: 'part',
    where: PART,
    keys: ['Escape'],
    enabled: ({ parts }) => Boolean(parts?.writing),
    run: ({ parts }) => parts?.close(),
  },
  {
    id: 'clipboard.cut',
    label: 'command.cut',
    icon: Scissors,
    group: 'clipboard',
    where: ANYWHERE,
    keys: ['Mod-x'],
    native: true,
    enabled: editing((context) => clipboardReady() && !context.view.state.selection.empty),
    run: (context) => later(context, cutSelection(context.view)),
  },
  {
    id: 'clipboard.copy',
    label: 'command.copy',
    icon: Copy,
    group: 'clipboard',
    where: ANYWHERE,
    keys: ['Mod-c'],
    native: true,
    enabled: (context) => clipboardReady() && !context.view.state.selection.empty,
    run: (context) => later(context, copySelection(context.view)),
  },
  {
    id: 'clipboard.paste',
    label: 'command.paste',
    icon: ClipboardPaste,
    group: 'clipboard',
    where: ANYWHERE,
    keys: ['Mod-v'],
    native: true,
    enabled: editing(clipboardReady),
    run: (context) => later(context, pasteInto(context.view, false)),
  },
  {
    id: 'clipboard.blockLink',
    label: 'command.blockLink',
    icon: Link2,
    group: 'clipboard',
    where: ANYWHERE,
    enabled: (context) => clipboardReady() && !!context.place.tab && !!blockId(context),
    run: (context) => later(context, navigator.clipboard.writeText(blockLink(context))),
  },
  {
    id: 'clipboard.pasteText',
    label: 'command.pasteText',
    icon: ClipboardType,
    group: 'clipboard',
    where: ANYWHERE,
    keys: ['Shift-Mod-v'],
    native: true,
    enabled: editing(clipboardReady),
    run: (context) => later(context, pasteInto(context.view, true)),
  },
  {
    id: 'image.edit',
    label: 'command.imageEdit',
    icon: SlidersHorizontal,
    group: 'image',
    where: IMAGE,
    enabled: editing(({ view }) => selectedImage(view.state)?.node.attrs.blob != null),
    run: (context) => context.open('imageEdit'),
  },
  {
    id: 'image.alt',
    label: 'command.imageAlt',
    icon: Captions,
    group: 'image',
    where: IMAGE,
    enabled: editing(({ view }) => selectedImage(view.state) !== null),
    run: (context) => context.open('imageAlt'),
  },
  {
    id: 'image.delete',
    label: 'command.deleteImage',
    icon: Trash2,
    group: 'image',
    where: IMAGE,
    enabled: editing(({ view }) => selectedImage(view.state) !== null),
    run: ({ view }) => view.dispatch(view.state.tr.deleteSelection().scrollIntoView()),
  },
  {
    id: 'pdf.pages',
    label: 'command.pdfPages',
    icon: Files,
    group: 'pdf',
    where: PDF,
    enabled: editing(({ view }) => selectedPdf(view.state)?.node.attrs.blob != null),
    run: (context) => context.open('pdfPages'),
  },
  {
    id: 'pdf.open',
    label: 'command.pdfOpen',
    icon: ExternalLink,
    group: 'pdf',
    where: PDF,
    enabled: ({ view }) => selectedPdf(view.state)?.node.attrs.blob != null,
    run: ({ view }) =>
      window.open(pdfUrl(selectedPdf(view.state)!.node.attrs.blob), '_blank', 'noreferrer'),
  },
  {
    id: 'pdf.delete',
    label: 'command.deletePdf',
    icon: Trash2,
    group: 'pdf',
    where: PDF,
    enabled: editing(({ view }) => selectedPdf(view.state) !== null),
    run: ({ view }) => view.dispatch(view.state.tr.deleteSelection().scrollIntoView()),
  },
  {
    id: 'chart.edit',
    label: 'command.editChart',
    icon: ChartColumn,
    group: 'chart',
    where: CHART,
    enabled: editing(({ view }) => selectedChart(view.state) !== null),
    run: (context) => context.open('chart'),
  },
  {
    id: 'chart.delete',
    label: 'command.deleteChart',
    icon: Trash2,
    group: 'chart',
    where: CHART,
    enabled: editing(({ view }) => selectedChart(view.state) !== null),
    run: ({ view }) => view.dispatch(view.state.tr.deleteSelection().scrollIntoView()),
  },
  {
    id: 'find.find',
    label: 'command.find',
    icon: TextSearch,
    group: 'find',
    where: ANYWHERE,
    keys: ['Mod-f'],
    enabled: () => true,
    run: (context) => context.open('find'),
  },
  {
    id: 'find.replace',
    label: 'command.replace',
    icon: Replace,
    group: 'find',
    where: ANYWHERE,
    keys: ['Ctrl-h'],
    enabled: () => true,
    run: (context) => context.open('replace'),
  },
  {
    id: 'help.search',
    label: 'command.search',
    icon: Search,
    group: 'help',
    where: ANYWHERE,
    keys: ['Alt-/'],
    native: true,
    enabled: () => true,
    run: () => focusSearch(),
  },
  {
    id: 'help.shortcuts',
    label: 'command.shortcuts',
    icon: Keyboard,
    group: 'help',
    where: ANYWHERE,
    keys: ['Mod-/'],
    enabled: () => true,
    run: (context) => context.open('shortcuts'),
  },
];

export const GROUPS: readonly Group[] = [
  'history',
  'clipboard',
  'style',
  'format',
  'script',
  'color',
  'highlight',
  'list',
  'numberForm',
  'bulletForm',
  'numbering',
  'align',
  'indent',
  'paragraph',
  'insert',
  'comment',
  'review',
  'writing',
  'rewrite',
  'translate',
  'table',
  'tableData',
  'total',
  'cellFormat',
  'fill',
  'image',
  'pdf',
  'chart',
  'note',
  'part',
  'slide',
  'slideLayout',
  'slideSize',
  'document',
  'find',
  'help',
];

/** The groups of the commands of a table, an image or a note, each a part of their menus. */
export const PLACED_GROUPS: Record<Exclude<Where, 'text'>, readonly Group[]> = {
  table: ['table', 'tableData'],
  image: ['image'],
  pdf: ['pdf'],
  chart: ['chart'],
  note: ['note'],
  part: ['part'],
};

export function commandOf(id: string): EditorCommand | undefined {
  return COMMANDS.find((command) => command.id === id);
}

export function inGroup(group: Group): EditorCommand[] {
  return [...COMMANDS, ...offeredCommands()].filter((command) => command.group === group);
}

/** The document's own styles, by name, each applied as its kind of block. */
export function styleCommands(styling: Styling): EditorCommand[] {
  return ownStyles(styling).map(([id, style]): EditorCommand => {
    const { type, attrs } = blockOf(style.kind);
    return {
      id: `style.custom.${id}`,
      label: KIND_LABELS[style.kind],
      name: style.name,
      icon: STYLE_ICONS[style.kind],
      group: 'style',
      where: PROSE,
      active: styled(style.kind, id),
      ...formatting(retype(type, { ...attrs, style: id })),
    };
  });
}

function startOf(view: EditorView) {
  return slideAt(view.state.doc, view.state.selection.from)?.start ?? null;
}

function sameSize(a: Size, b: Size): boolean {
  return Math.abs(a.width - b.width) < 0.01 && Math.abs(a.height - b.height) < 0.01;
}

/** A layout for the cursor's slide: the one its kind of slide takes, or one of the template's. */
export function layoutCommands({ template }: Slides): EditorCommand[] {
  const choose = (id: string | null): Pick<EditorCommand, 'active' | 'enabled' | 'run'> => ({
    active: ({ view }) =>
      (slideAt(view.state.doc, view.state.selection.from)?.layout ?? null) === id,
    enabled: editing(({ view }) => startOf(view) !== null),
    run: ({ view }) => {
      const start = startOf(view);
      if (start) view.dispatch(view.state.tr.setNodeAttribute(start.pos, 'layout', id));
    },
  });
  return [
    {
      id: 'slide.layout',
      label: 'slides.layout.auto',
      icon: LayoutTemplate,
      group: 'slideLayout',
      where: TEXT,
      ...choose(null),
    },
    ...template.layouts.map((layout): EditorCommand => ({
      id: `slide.layout.${layout.id}`,
      label: `slides.layout.${layout.kind}`,
      name: template.builtIn ? undefined : layout.name,
      icon: LayoutTemplate,
      group: 'slideLayout',
      where: TEXT,
      ...choose(layout.id),
    })),
  ];
}

/** Every command, the document's own styles following the built-in ones. */
export function commandsOf(styling: Styling): EditorCommand[] {
  const after = COMMANDS.findLastIndex((command) => command.group === 'style') + 1;
  return [
    ...COMMANDS.slice(0, after),
    ...styleCommands(styling),
    ...COMMANDS.slice(after),
    ...offeredCommands(),
  ];
}

export function whereOf({ view }: Context): Where {
  if (selectedImage(view.state)) return 'image';
  if (selectedPdf(view.state)) return 'pdf';
  if (selectedChart(view.state)) return 'chart';
  if (inPart(view.state)) return 'part';
  if (noteOf(view)) return 'note';
  if (cellOf(view)) return 'table';
  const { selection } = view.state;
  if (selection instanceof CellRange) return 'table';
  return selection instanceof NodeSelection && selection.node.type === table ? 'table' : 'text';
}

export function available(command: EditorCommand, context: Context): boolean {
  return command.where.includes(whereOf(context)) && command.enabled(context);
}

export function refocus({ view }: Context): void {
  if (!refocusCell(view) && !openSelected(view) && !focusedCell(view)) view.focus();
}

export function perform(command: EditorCommand, context: Context): boolean {
  if (!available(command, context)) return false;
  command.run(context);
  return true;
}

/** Key bindings for every command that applies here. A bound key is always ours, also when the
 * command is disabled, so the browser's own undo never runs on text it did not write. */
export function bindings(where: Where, context: (view: EditorView) => Context) {
  const bound: Record<string, Command> = {};
  for (const command of COMMANDS) {
    if (command.native) continue;
    const here = command.where.includes(where);
    // Cells selected whole are the text editor's selection, which takes their keys while it lasts.
    const ranged = where === 'text' && command.where.includes('table');
    if (!here && !ranged) continue;
    for (const key of command.keys ?? []) {
      const before = bound[key];
      bound[key] = (state, dispatch, view) => {
        if (!here && !(view && whereOf(context(view)) === 'table'))
          return before?.(state, dispatch, view) ?? false;
        if (dispatch && view) perform(command, context(view));
        return true;
      };
    }
  }
  return bound;
}

export function labelOf(command: EditorCommand, t: (key: MessageKey) => string): string {
  if (command.name) return command.name;
  if (command.sample) return `${t(command.label)}: ${command.sample}`;
  return command.detail
    ? `${t(command.label)}: ${t(command.detail).toLocaleLowerCase()}`
    : t(command.label);
}

export function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

export function choices(
  commands: readonly EditorCommand[],
  context: Context,
  label: (key: MessageKey) => string,
  query = '',
): Choice[] {
  const wanted = fold(query.trim());
  return commands
    .filter((command) => !command.sub && command.where.includes(whereOf(context)))
    .map((command) => ({ command, label: labelOf(command, label) }))
    .filter(({ label }) => fold(label).includes(wanted))
    .map(({ command, label }) => ({
      id: command.id,
      label,
      icon: command.icon,
      keys: command.keys?.[0],
      disabled: !command.enabled(context),
      run: () => {
        if (perform(command, context)) refocus(context);
      },
    }));
}
