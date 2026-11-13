import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Files, Presentation, ScrollText, type LucideIcon } from 'lucide-react';
import { baseKeymap } from 'prosemirror-commands';
import { dropCursor } from 'prosemirror-dropcursor';
import { gapCursor } from 'prosemirror-gapcursor';
import 'prosemirror-gapcursor/style/gapcursor.css';
import { InputRule, inputRules } from 'prosemirror-inputrules';
import { keydownHandler, keymap } from 'prosemirror-keymap';
import type { Node } from 'prosemirror-model';
import {
  EditorState,
  Plugin,
  Selection,
  TextSelection,
  type Command,
  type Transaction,
} from 'prosemirror-state';
import { Decoration, DecorationSet, EditorView } from 'prosemirror-view';
import 'prosemirror-view/style/prosemirror.css';
import {
  Fragment,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type RefObject,
} from 'react';
import { useLocation, useNavigate } from 'react-router';
import {
  defaultDeleteFilter,
  defaultProtectedNodes,
  ySyncPlugin,
  ySyncPluginKey,
  yUndoPlugin,
  yXmlFragmentToProseMirrorRootNode,
} from 'y-prosemirror';
import type { Awareness } from 'y-protocols/awareness';
import type { WebsocketProvider } from 'y-websocket';
import * as Y from 'yjs';
import { ApiError, getBytes, getJson, postJson } from '../api';
import { useSession } from '../auth';
import { useReachable } from '../live';
import { joinRoom, useKept, useRecheck } from '../room';
import { Choices, ZoomChoices } from '../choices';
import { useDesk, useThreads, type Desk, type InText } from '../comments';
import { Close, Modal } from '../dialogs';
import { type Language, useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { ContextMenuArea, MenuSeparator } from '../menu';
import { useProvidePalette, type Choice } from '../palette';
import { tabHref, type Found, type OutlineStore } from '../tabs';
import { presenceColor } from '../theme';
import { errorMessage, Failure, type DocumentLocale, type Tab, type TreeNode } from '../tree';
import { CompareDialog } from '../versions';
import { CompareFileDialog } from './CompareFileDialog';
import { useView, useZoom, VIEWS, type View } from '../views';
import { blockIds, textblocks } from './blocks';
import { clipboardSerializer, clipboardText, pastedHTML } from './clipboard';
import { GridClient, KeptGrids, placesOf, type GridSource, type KeptOutlines } from './grids';
import { History, historyIn, historyPlugin, ownUndo, type Undo } from './history';
import { useAgent } from './agent';
import { commentsPlugin, placedOf, showComments } from './comments';
import {
  chaptersOf,
  contentsStore,
  ContentsView,
  headingsOf,
  writeHeadings,
  type ContentsStore,
} from './contents';
import { writtenAtEnd } from './ends';
import { writtenDate } from './formats';
import { selectOnFocus } from './focus';
import { formatsOf, listStore, savedLists, type ListStore } from './forms';
import { addressOf, pointedAt } from './formulas';
import { FindBar } from './FindBar';
import { findingPlugin } from './finding';
import { foundPlugin, showBlock } from './found';
import { offerActions, runAsked } from './actions';
import {
  PARAGRAPHS,
  type Context,
  type Dialog,
  type EditorCommand,
  type Place,
  type Slides,
} from './command';
import {
  available,
  bindings,
  choices,
  commandsOf,
  inGroup,
  labelOf,
  commandOf,
  perform,
  PLACED_GROUPS,
  refocus,
  whereOf,
} from './commands';
import { dealingOf, deckPlugin, showDeck } from './deck';
import { Frames } from './Deck';
import { imagePasting, ImageView, selectFigureAt } from './images';
import { ImageDialog } from './ImageDialog';
import { ImageEditDialog } from './ImageEditDialog';
import { PdfDialog, PdfPagesDialog } from './PdfDialog';
import { pdfPasting, PdfBlockView } from './pdfs';
import { AltDialog, LinkDialog, LinkPopover } from './LinkDialog';
import { proposalsAt, proposalsPlugin } from './proposals';
import { ProposalPopover } from './Proposals';
import { suggesting, type Proposer } from './suggesting';
import { CellFormatDialog } from './CellFormatDialog';
import { CalculateDialog } from './CalculateDialog';
import { ChartDialog } from './ChartDialog';
import { FilterDialog } from './FilterDialog';
import { ChartView } from './charts';
import { ListFormatDialog } from './ListFormatDialog';
import { autolink, followLinks } from './links';
import { checkBoxes, listKeys, listMarkers, listRules } from './lists';
import { presentFullScreen, type From } from './show';
import {
  setSlideSize,
  slideAt,
  slidesBefore,
  slidesOf,
  speakerKeys,
  speakerLabels,
  templateOf,
  writeSlideCount,
  type Template,
} from './slides';
import {
  countsOf,
  NO_NOTES,
  NoteList,
  notesIn,
  notesPlugin,
  NoteView,
  numberFrom,
  offsetOf,
  showNote,
  tabNotesOf,
  writeCounts,
  type Counts,
  type TabNotes,
} from './notes';
import {
  numberIn,
  numberingPlugin,
  numbersOf,
  renumber,
  startOf,
  writeTally,
  type Counters,
} from './numbering';
import { outlineOf } from './outline';
import {
  breaksOf,
  clearOfParts,
  geometryOf,
  linkPart,
  numberingOf,
  opensSection,
  ownsPages,
  pageAt,
  pageNumbersOf,
  pagesPlugin,
  pagingOf,
  partLinked,
  partOwner,
  PX_PER_CM,
  saveSection,
  savePages,
  sectionAt,
  sectionPart,
  sectionsOf,
  setFirstPage,
  showPages,
  stackOf,
  writePages,
  type PageSetup,
  type PartHeights,
} from './pages';
import type { SectionPages } from './PageDialog';
import { Papers, PartMeasures, partOn, partPlace } from './Papers';
import { fieldView, partPlugin, valueOf, type Parts, type Writing } from './parts';
import { presence } from './presence';
import { indentsOf } from './rulers';
import { TaskDialog, type Draft } from '../tasks';
import { ConsentDialog } from './ConsentDialog';
import { RunBar } from './RunBar';
import {
  ended,
  runningIn,
  stopRun,
  undoRun,
  type Action,
  type Consent,
  type Run,
  type Running,
} from './runs';
import { HorizontalRuler, VerticalRuler } from './Rulers';
import { decimalOf, tabStops } from './stops';
import { isInternal, listOf, schema, stopsOf } from './schema';
import { Shortcuts } from './Shortcuts';
import { slashMenu, SlashMenu } from './slash';
import { stylesheet, stylingOf, useStyling, type Styling } from './styling';
import { bodyOf } from './tab';
import { linesOf } from './tables';
import { GoToDialog } from './NameBox';
import { TableNameDialog } from './TableNameDialog';
import { TabStopsDialog } from './TabStopsDialog';
import { cellOf, cellViewAt, tableIn, type Write } from './tableBase';
import { cellKeys, showCell, tablesPlugin } from './tablesPlugin';
import { CommandItem, Toolbar } from './Toolbar';

type Status = 'connecting' | 'connected' | 'disconnected';

const { heading } = schema.nodes;

const headingRule = new InputRule(/^(#{1,4})\s$/, (state, match, start, end) => {
  const $start = state.doc.resolve(start);
  const index = $start.index(-1);
  if (!$start.node(-1).canReplaceWith(index, index + 1, heading)) return null;
  return state.tr.delete(start, end).setBlockType(start, start, heading, (node) => ({
    id: node.attrs.id,
    level: match[1].length,
  }));
});

export interface Actions {
  /** The document's grids, which its tables' rows and cells are in. */
  grids: GridClient;
  open: (dialog: Dialog) => void;
  /** Opens the user's filter of the table's column. */
  filter: (table: string, col: string) => void;
  fail: (error: unknown) => void;
  ran: (run: Run) => void;
  consent: Context['consent'];
  follow: (href: string) => void;
  visitTab: Context['visitTab'];
  label: RefObject<(key: MessageKey) => string>;
  styling: RefObject<Styling>;
  place: Place;
  notes: RefObject<TabNotes | null>;
  numbers: RefObject<Counters>;
  desk: RefObject<Desk | null>;
  parts: RefObject<Parts | null>;
  slides: RefObject<Slides | null>;
  present: RefObject<Context['present']>;
  contents: ContentsStore;
  lists: ListStore;
  locale: RefObject<DocumentLocale>;
  /** Who proposes what the user writes, while the Suggesting mode is on. */
  proposer: RefObject<Proposer | null>;
  suggest: (on: boolean) => void;
}

/** Leads to one of PONISTRA's own pages. */
function useGo(): (href: string) => void {
  const navigate = useNavigate();
  const latest = useRef(navigate);
  latest.current = navigate;
  return useCallback((href: string) => latest.current(href), []);
}

/** Leads to a link's address: PONISTRA's own pages here, any other in a new tab. */
function useFollow(): (href: string) => void {
  const go = useGo();
  return useCallback(
    (href: string) => {
      if (isInternal(href)) go(href);
      else window.open(href, '_blank', 'noopener,noreferrer');
    },
    [go],
  );
}

function emptyHint(): Plugin {
  return new Plugin({
    props: {
      decorations({ doc }) {
        const only = doc.firstChild!;
        if (doc.childCount > 1 || !only.isTextblock || only.content.size) return null;
        return DecorationSet.create(doc, [
          Decoration.node(0, only.nodeSize, { class: 'ponistra-empty' }),
        ]);
      },
    },
  });
}

function writeBelow(): Plugin {
  return new Plugin({
    props: {
      handleDOMEvents: {
        mousedown(view, event) {
          const { doc } = view.state;
          const last = doc.lastChild!;
          if (event.target !== view.dom || last.isTextblock || !view.editable) return false;
          const shown = view.nodeDOM(doc.content.size - last.nodeSize);
          if (
            !(shown instanceof HTMLElement) ||
            event.clientY < shown.getBoundingClientRect().bottom
          )
            return false;
          const end = doc.content.size;
          const tr = view.state.tr.insert(end, schema.nodes.paragraph.create());
          view.dispatch(tr.setSelection(TextSelection.create(tr.doc, end + 1)).scrollIntoView());
          view.focus();
          event.preventDefault();
          return true;
        },
      },
    },
  });
}

/** On Windows Ctrl+Alt is AltGr, and with a letter the key names the character the layout puts
 * there (Ctrl+Alt+M is § on a Croatian keyboard), so those chords are matched by the key itself. */
function chords(bound: ReturnType<typeof bindings>): Plugin {
  const handle = keydownHandler(bound);
  return new Plugin({
    props: {
      handleKeyDown(view, event) {
        const letter = /^Key([A-Z])$/.exec(event.code)?.[1];
        if (!letter || !event.ctrlKey || !event.altKey) return false;
        const key = event.shiftKey ? letter : letter.toLowerCase();
        const { shiftKey, metaKey } = event;
        const named = new KeyboardEvent('keydown', {
          key,
          ctrlKey: true,
          altKey: true,
          shiftKey,
          metaKey,
        });
        return handle(view, named);
      },
    },
  });
}

function commandKeys(
  where: 'text' | 'note' | 'table' | 'part',
  context: (view: EditorView) => Context,
): Plugin[] {
  const bound = bindings(where, context);
  return [keymap(bound), chords(bound)];
}

/** A note's own editor: the document's keys that apply in a note, and no paragraphs. */
function notePlugins(
  context: (view: EditorView) => Context,
  follow: (href: string) => void,
  lists: ListStore,
  proposer: () => Proposer | null,
) {
  return [
    new Plugin({ props: { clipboardSerializer: clipboardSerializer(lists) } }),
    ...commandKeys('note', context),
    keymap({ Enter: () => true, 'Shift-Enter': () => true }),
    keymap(baseKeymap),
    followLinks(follow),
    writtenAtEnd(),
    proposalsPlugin(),
    suggesting(proposer),
  ];
}

/** What the undo commands take back in an editor: a light cell's own typing while it has any,
 * else the history of the editor the view writes into. */
function undoOf(view: EditorView, main: Undo): Undo {
  const cell = cellOf(view);
  if (cell?.light) {
    const own = ownUndo(view);
    if (own.canUndo() || own.canRedo()) return own;
  }
  return historyIn((cell?.table.outer ?? view).state) ?? main;
}

/** A history over the Yjs text of `doc` the editor writes, and the edits of the grids it sends
 * with `write`, as the tab `tab` names them, or the headers and footers with null. */
function historyOver(
  type: Y.XmlFragment,
  grids: GridClient,
  tab: () => string | null,
  fail: (error: unknown) => void,
): { manager: Y.UndoManager; history: History; write: Write } {
  const doc = type.doc!;
  const manager = new Y.UndoManager([type], {
    trackedOrigins: new Set([ySyncPluginKey]),
    deleteFilter: (item) => defaultDeleteFilter(item, defaultProtectedNodes),
    captureTransaction: (transaction) => transaction.meta.get('addToHistory') !== false,
  });
  const history = new History(manager, () => ({ client: grids, doc }), fail);
  const write: Write = (operations, written) => {
    const { token, answer } = grids.do(tab(), operations, { doc, written });
    history.wrote(token);
    answer.catch(fail);
  };
  return { manager, history, write };
}

/** A header's or a footer's own editor over its part of the document's own state: the document's
 * keys that apply there, and an undo of its own. */
function partView(
  host: HTMLElement,
  fragment: Y.XmlFragment,
  options: {
    context: (view: EditorView) => Context;
    value: (kind: string) => string;
    decimal: () => string;
    onState: (view: EditorView) => void;
    actions: Actions;
  },
): EditorView {
  const { actions } = options;
  const { manager, history, write } = historyOver(
    fragment,
    actions.grids,
    () => null,
    actions.fail,
  );
  const context = (view: EditorView): Context => ({
    ...options.context(view),
    history: undoOf(view, history),
  });
  return new EditorView(host, {
    state: EditorState.create({
      schema,
      plugins: [
        ySyncPlugin(fragment),
        yUndoPlugin({ undoManager: manager }),
        historyPlugin(history),
        tablesPlugin({
          doc: fragment.doc!,
          grids: actions.grids,
          write,
          history,
          tab: () => null,
          inner: cellPlugins(context, actions),
          nodeViews: { field: fieldView(options.value) },
          onCell: options.onState,
          filtering: actions.filter,
          label: () => actions.label.current,
          locale: () => actions.locale.current,
          fail: actions.fail,
        }),
        partPlugin(),
        ...commandKeys('part', context),
        keymap(baseKeymap),
        tabStops(options.decimal),
        proposalsPlugin(),
      ],
    }),
    nodeViews: { field: fieldView(options.value) },
    dispatchTransaction(this: EditorView, tr: Transaction) {
      this.updateState(this.state.apply(tr));
      options.onState(this);
    },
    handleDOMEvents: {
      focus: (view) => {
        selectOnFocus(view);
        options.onState(view);
        return false;
      },
    },
  });
}

/** A cell's own editor: the document's keys that apply in a cell, and the cell's way out. */
function cellPlugins(context: (view: EditorView) => Context, actions: Actions): Plugin[] {
  return [
    new Plugin({
      props: {
        clipboardSerializer: clipboardSerializer(actions.lists),
        clipboardTextSerializer: clipboardText(actions.lists),
        transformPastedHTML: pastedHTML,
      },
    }),
    inputRules({ rules: [...listRules, autolink] }),
    cellKeys(),
    keymap(listKeys),
    ...commandKeys('table', context),
    keymap(baseKeymap),
    imagePasting(() => ({
      document: actions.place.document,
      fail: actions.fail,
      label: actions.label.current,
    })),
    listMarkers(actions.lists),
    checkBoxes(),
    followLinks(actions.follow),
    gapCursor(),
    writtenAtEnd(),
    tabStops(() => decimalOf(actions.locale.current)),
    proposalsPlugin(),
    suggesting(() => actions.proposer.current),
  ];
}

export function editingPlugins(
  doc: Y.Doc,
  actions: Actions,
  list: NoteList | null = null,
  onInner: (view: EditorView) => void = () => {},
): Plugin[] {
  const { grids } = actions;
  const { manager, history, write } = historyOver(
    bodyOf(doc),
    grids,
    () => actions.place.tab,
    actions.fail,
  );
  const context = (view: EditorView): Context => ({
    view,
    doc,
    history: undoOf(view, history),
    styling: actions.styling.current,
    place: actions.place,
    notes: actions.notes.current,
    desk: actions.desk.current,
    parts: actions.parts.current,
    slides: actions.slides.current,
    present: actions.present.current,
    lists: actions.lists,
    open: actions.open,
    ran: actions.ran,
    consent: actions.consent,
    fail: actions.fail,
    label: actions.label.current,
    suggesting: actions.proposer.current !== null,
    suggest: actions.suggest,
    visitTab: actions.visitTab,
  });
  return [
    yUndoPlugin({ undoManager: manager }),
    historyPlugin(history),
    tablesPlugin({
      doc,
      grids,
      write,
      history,
      tab: () => actions.place.tab,
      inner: cellPlugins(context, actions),
      nodeViews: {
        image: (node, view, getPos) =>
          new ImageView(node, view, getPos, actions.label.current('image.waiting')),
        contents: (node, view) =>
          new ContentsView(node, view, actions.contents, () => actions.label.current),
      },
      onCell: onInner,
      filtering: actions.filter,
      label: () => actions.label.current,
      locale: () => actions.locale.current,
      fail: actions.fail,
    }),
    slashMenu((view, query) =>
      choices(inGroup('insert'), context(view), actions.label.current, query),
    ),
    inputRules({ rules: [headingRule, ...listRules, autolink] }),
    keymap(listKeys),
    keymap(speakerKeys),
    ...commandKeys('text', context),
    keymap(baseKeymap),
    speakerLabels(() => actions.label.current('command.speakerNotes')),
    pdfPasting(() => ({
      document: actions.place.document,
      fail: actions.fail,
      label: actions.label.current,
    })),
    imagePasting(() => ({
      document: actions.place.document,
      fail: actions.fail,
      label: actions.label.current,
    })),
    blockIds(),
    notesPlugin({
      list,
      inner: notePlugins(context, actions.follow, actions.lists, () => actions.proposer.current),
      offset: actions.notes.current?.offset ?? NO_NOTES,
    }),
    listMarkers(actions.lists),
    tabStops(() => decimalOf(actions.locale.current)),
    numberingPlugin(actions.styling.current, actions.numbers.current, grids),
    checkBoxes(),
    followLinks(actions.follow),
    emptyHint(),
    writeBelow(),
    dropCursor({ color: 'var(--focus)' }),
    gapCursor(),
    writtenAtEnd(),
    proposalsPlugin(),
    suggesting(
      () => actions.proposer.current,
      linesOf(grids),
      (table) => {
        const grid = grids.grid(table.attrs.id);
        if (grid) void grids.rowIds(grid.table, placesOf(0, grid.rowCount - 1));
        actions.fail(new Error(actions.label.current('table.loading')));
      },
    ),
  ];
}

export function liveView(
  host: HTMLElement,
  doc: Y.Doc,
  awareness: Awareness,
  options: {
    /** Where the tab's notes are listed, under its text. */
    notes: HTMLElement | null;
    editable: () => boolean;
    onState: (state: EditorState) => void;
    onFocus: (focused: boolean) => void;
    /** A note's or a cell's own editor took the focus or changed its state. */
    onInner: (view: EditorView) => void;
    actions: Actions;
  },
): EditorView {
  const list =
    options.notes &&
    new NoteList(options.notes, {
      label: () => options.actions.label.current,
      onNote: options.onInner,
    });
  const numberOf = (block: Node) => numberIn(view.state, block);
  const view: EditorView = new EditorView(host, {
    state: EditorState.create({
      schema,
      plugins: [
        ySyncPlugin(bodyOf(doc)),
        ...presence(awareness, () => options.actions.label.current),
        foundPlugin(),
        findingPlugin(),
        pagesPlugin(),
        deckPlugin(),
        commentsPlugin((thread) => options.actions.desk.current?.show(thread)),
        ...editingPlugins(doc, options.actions, list, options.onInner),
      ],
    }),
    editable: options.editable,
    nodeViews: {
      image: (node, view, getPos) =>
        new ImageView(node, view, getPos, options.actions.label.current('image.waiting')),
      pdf: (node, view, getPos, decorations) =>
        new PdfBlockView(node, view, getPos, decorations, {
          waiting: options.actions.label.current('pdf.waiting'),
          unshown: options.actions.label.current('pdf.unshown'),
          printing: false,
        }),
      footnote: (node, view, getPos) => new NoteView(node, view, getPos),
      contents: (node, view) =>
        new ContentsView(node, view, options.actions.contents, () => options.actions.label.current),
      chart: (node, view) =>
        new ChartView(node, doc, {
          label: () => options.actions.label.current,
          locale: () => options.actions.locale.current,
          edit: () => view.editable && options.actions.open('chart'),
        }),
    },
    clipboardSerializer: clipboardSerializer(options.actions.lists, numberOf),
    clipboardTextSerializer: clipboardText(options.actions.lists, numberOf),
    transformPastedHTML: pastedHTML,
    handleDOMEvents: {
      focus: (view) => {
        selectOnFocus(view);
        options.onFocus(true);
        return false;
      },
      blur: () => {
        options.onFocus(false);
        return false;
      },
    },
    // The sync plugin dispatches while the view is still being constructed, and the cursor
    // plugin from a timer that can fire after it is destroyed.
    dispatchTransaction(this: EditorView, transaction: Transaction) {
      if (this.isDestroyed) return;
      const next = this.state.apply(transaction);
      this.updateState(next);
      options.onState(next);
    },
  });
  return view;
}

/** A right click in the text outside the selection puts the cursor there, as the browser does;
 * the menu takes the focus before the editor would read the browser's cursor. */
function cursorAt(
  view: EditorView,
  { target, clientX, clientY }: { target: EventTarget | null; clientX: number; clientY: number },
): void {
  if (!(target instanceof Element) || target.closest('.ProseMirror') !== view.dom) return;
  const found = view.posAtCoords({ left: clientX, top: clientY });
  const { from, to } = view.state.selection;
  if (!found || (found.pos >= from && found.pos <= to)) return;
  const $pos = view.state.doc.resolve(found.pos);
  if (!$pos.parent.isTextblock) return;
  view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, found.pos)));
}

function EditorMenu({ context }: { context: Context }) {
  const { t } = useI18n();
  const item = (command: EditorCommand) => (
    <CommandItem key={command.id} command={command} label={labelOf(command, t)} context={context} />
  );
  const where = whereOf(context);
  const own = where === 'text' ? [inGroup('writing')] : PLACED_GROUPS[where].map(inGroup);
  const review = inGroup('review');
  const offered = [
    proposalsAt(context.view.state).length ? review : [],
    ...(['numbering', 'paragraph'] as const).map(inGroup),
  ]
    .map((commands) => commands.filter((command) => available(command, context)))
    .filter((commands) => commands.length > 0);
  return (
    <>
      {inGroup('clipboard').map(item)}
      <MenuSeparator />
      {inGroup('comment').map(item)}
      {offered.map((commands, at) => (
        <Fragment key={`offered-${at}`}>
          <MenuSeparator />
          {commands.map(item)}
        </Fragment>
      ))}
      {own.map((commands, at) => (
        <Fragment key={at}>
          <MenuSeparator />
          {commands.map(item)}
        </Fragment>
      ))}
    </>
  );
}

/** What a search hit, a heading or a cell's address leads to shown; false while the tab has none
 * of it. An address leads into the block it comes with, else into the table its name names, else
 * into the tab's first table. */
function showFound(view: EditorView, grids: GridSource, { block, cell }: Found): boolean {
  const pointed = cell === null ? null : pointedAt(cell);
  if (pointed && 'rect' in pointed) {
    const table = tableIn(view.state.doc, grids, block, pointed.table);
    if (table !== null) showCell(view, table, addressOf(pointed.rect));
    return table !== null;
  }
  if (block === null) return true;
  return showBlock(view, block) || showNote(view, block);
}

function Problem({ error, onClose }: { error: unknown; onClose: () => void }) {
  const { t } = useI18n();
  const denied = error instanceof DOMException && error.name === 'NotAllowedError';
  return (
    <Modal heading={t('command.failed')} onClose={onClose}>
      <p>
        {denied
          ? t('clipboard.denied')
          : error instanceof ApiError
            ? errorMessage(error, t)
            : error instanceof Error
              ? error.message
              : String(error)}
      </p>
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}

const page = 'ponistra-document mx-auto w-full max-w-(--column) py-4';

const VIEW_ICONS: Record<View, LucideIcon> = {
  text: ScrollText,
  pages: Files,
  slides: Presentation,
};
/** Counts the changes to the document's own room, which the tab's note numbers and numbered
 * blocks follow from the tabs before it. */
function useChanges(own: Y.Doc): number {
  const [changes, setChanges] = useState(0);
  useEffect(() => {
    const changed = () => setChanges((count) => count + 1);
    own.on('update', changed);
    return () => own.off('update', changed);
  }, [own]);
  return changes;
}

/** The rules of the document's styles, for the blocks inside the element given its scope. */
export function useStylesheet(styling: Styling): { scope: string; sheet: string } {
  const scope = useId();
  return {
    scope,
    sheet: useMemo(() => stylesheet(scope, styling), [scope, styling]),
  };
}

export function LiveEditor({
  own,
  grids,
  room,
  documentId,
  original,
  tab,
  home,
  tabs,
  readOnly,
  found,
  outline,
  locale,
  title,
  requested,
  onRequested,
  onPresent,
  onSection,
}: {
  /** The document's own state, its theme and styles. */
  own: Y.Doc;
  grids: GridClient;
  room: string;
  documentId: string;
  original: TreeNode['original'];
  tab: string | null;
  /** The document's address, under which each tab has its own. */
  home: string;
  /** The document's tabs in reading order, which the note numbers follow. */
  tabs: readonly Pick<Tab, 'id' | 'title'>[];
  readOnly: boolean;
  /** Where a search hit or a heading leads, shown once the room has brought it. */
  found: Found | null;
  outline: OutlineStore;
  locale: DocumentLocale;
  /** The document's title, which a header or footer can show. */
  title: string;
  /** A command or a backend's action asked for outside the editor, run here once it can be. */
  requested: string | null;
  onRequested: () => void;
  onPresent: (from: From) => void;
  /** The section after a break the cursor is in, whose pages the page setup sets; null in the
   * tab's first. */
  onSection: (section: SectionPages | null) => void;
}) {
  const { t, language } = useI18n();
  const { key: visit } = useLocation();
  const recheck = useRecheck(documentId);
  const keep = useKept(documentId);
  // Re-rendering when the server goes or comes back is what enables the actions that need it.
  useReachable();
  const session = useSession();
  const user = session.data?.user;
  const host = useRef<HTMLDivElement>(null);
  const notesHost = useRef<HTMLDivElement>(null);
  const around = useRef<HTMLDivElement>(null);
  const sheets = useRef<HTMLDivElement>(null);
  const partBox = useRef<HTMLDivElement>(null);
  const partHost = useRef<HTMLDivElement>(null);
  const partsNow = useRef<Parts | null>(null);
  const slidesNow = useRef<Slides | null>(null);
  const presentNow = useRef<Context['present']>(null);
  const bar = useRef<HTMLDivElement>(null);
  const editable = useRef(!readOnly);
  editable.current = !readOnly;
  const label = useRef(t);
  label.current = t;
  const localeNow = useRef(locale);
  localeNow.current = locale;
  const styling = useStyling(own);
  const stylingNow = useRef(styling);
  stylingNow.current = styling;
  const { scope, sheet } = useStylesheet(styling);
  const changes = useChanges(own);
  const ids = useMemo(() => tabs.map(({ id }) => id), [tabs]);
  const tabNotes = useMemo(
    () => (tab ? tabNotesOf(own, ids, tab) : null),
    [own, ids, tab, changes],
  );
  const tabNotesNow = useRef(tabNotes);
  tabNotesNow.current = tabNotes;
  const start = useMemo(() => (tab ? startOf(own, ids, tab) : {}), [own, ids, tab, changes]);
  const startNow = useRef(start);
  startNow.current = start;
  const desk = useDesk();
  const agent = useAgent();
  const agentNow = useRef(agent);
  agentNow.current = agent;
  const deskNow = useRef(desk);
  deskNow.current = desk;
  const threads = useThreads(documentId);
  const [status, setStatus] = useState<Status>('connecting');
  const [synced, setSynced] = useState(false);
  const [shownIn, setShownIn] = useState<string | null>(null);
  const [editor, setEditor] = useState<{
    view: EditorView;
    doc: Y.Doc;
    provider: WebsocketProvider;
    actions: Actions;
  } | null>(null);
  const [state, setState] = useState<EditorState | null>(null);
  // The note or cell being written stays the toolbar's target while a menu or dialog has the focus.
  const [inner, setInner] = useState<{
    view: EditorView;
    state: EditorState;
  } | null>(null);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [filtering, setFiltering] = useState<{ table: string; col: string } | null>(null);
  const [problem, setProblem] = useState<{ error: unknown } | null>(null);
  const [done, setDone] = useState<Run | null>(null);
  const [consenting, setConsenting] = useState<((consent: Consent) => void) | null>(null);
  const queryClient = useQueryClient();
  const settle = useCallback((run: Run, awareness: Awareness) => {
    ended(run, awareness).then(
      (found) =>
        found.state === 'failed'
          ? setProblem({ error: new ApiError(`/api/runs/${found.id}`, 422, found.error) })
          : setDone(found),
      (error: unknown) => setProblem({ error }),
    );
  }, []);
  const consent = useCallback((go: (consent: Consent) => void) => setConsenting(() => go), []);
  const openDialog = useCallback(
    (opened: Dialog) => (opened === 'ask' ? agentNow.current?.open() : setDialog(opened)),
    [],
  );
  const [running, setRunning] = useState<Running[]>([]);
  const [focused, setFocused] = useState(false);
  const [suggestingOn, setSuggesting] = useState(false);
  const proposer = useRef<Proposer | null>(null);
  proposer.current =
    suggestingOn && user ? { author: user.name || user.email, user: user.id } : null;
  const offered = useActions(language);
  const follow = useFollow();
  const go = useGo();
  const contents = useMemo(() => contentsStore(go), [go]);
  const lists = useMemo(() => listStore(own), [own]);
  const address = useMemo(() => {
    const open = tabs.find(({ id }) => id === tab);
    return open ? tabHref(home, open, tabs) : home;
  }, [home, tabs, tab]);
  const place = useMemo(() => ({ document: documentId, tab, address }), [documentId, tab, address]);
  const tabsNow = useRef({ home, tabs });
  tabsNow.current = { home, tabs };
  const visitTab = useCallback(
    (to: string, query: string) => {
      const { home, tabs } = tabsNow.current;
      const found = tabs.find(({ id }) => id === to);
      if (found) follow(`${tabHref(home, found, tabs)}?${query}`);
      return found !== undefined;
    },
    [follow],
  );
  const [view, setView] = useView(documentId, original);
  const [zoom, setZoom] = useZoom();
  const [pane, setPane] = useState(0);
  const breaksText = state ? breaksOf(state.doc).join(' ') : '';
  const breaks = useMemo(() => (breaksText ? breaksText.split(' ') : []), [breaksText]);
  const sections = useMemo(() => sectionsOf(own, tab, breaks), [own, tab, breaks, changes]);
  const setupsText = JSON.stringify(sections.map(({ setup }) => setup));
  const setups = useMemo(() => JSON.parse(setupsText) as PageSetup[], [setupsText]);
  const [heights, setHeights] = useState<PartHeights[]>([]);
  const keepHeights = useCallback(
    (next: PartHeights[]) =>
      setHeights((kept) => (JSON.stringify(kept) === JSON.stringify(next) ? kept : next)),
    [],
  );
  const geometries = useMemo(
    () =>
      view === 'pages'
        ? setups.map((setup, index) =>
            clearOfParts(geometryOf(setup), heights[index] ?? {}, setup.firstPage),
          )
        : null,
    [view, setups, heights],
  );
  const templateText = JSON.stringify(templateOf(own));
  const template = useMemo(() => JSON.parse(templateText) as Template, [templateText]);
  const deckOn = view === 'slides';
  const [opened, setOpened] = useState<Writing | null>(null);
  const laid = state ? (pagingOf(state)?.laid ?? null) : null;
  const stack = useMemo(() => geometries && stackOf(geometries, laid), [geometries, laid]);
  const owners = laid?.sections ?? [0];
  const deck = deckOn && state ? (dealingOf(state)?.deck ?? null) : null;
  const pages = laid?.pages ?? 1;
  const { first, total } = useMemo(
    () => (tab ? numberingOf(own, ids, tab, pages) : { first: 1, total: pages }),
    [own, ids, tab, pages, changes],
  );
  const numbers = useMemo(
    () => pageNumbersOf(first, setups, laid?.sections ?? [0]),
    [first, setups, laid],
  );
  const numbersNow = useRef(numbers);
  numbersNow.current = numbers;
  const date = useMemo(() => writtenDate(new Date(), locale), [locale]);
  const decimal = useMemo(() => decimalOf(locale), [locale]);
  const fields = useMemo(() => ({ first, total, title, date }), [first, total, title, date]);
  const fieldsNow = useRef(fields);
  fieldsNow.current = fields;
  const partShown = stack && tab && !readOnly && opened && opened.page < pages ? opened : null;
  const partSection = partShown ? stack!.pages[partShown.page].section : 0;
  const partName =
    partShown &&
    partOn(partShown.side, opensSection(owners, partShown.page), setups[partSection].firstPage);
  const partPage = partShown?.page ?? 0;
  const partFrom = partShown && tab ? partOwner(own, tab, breaks, partSection, partName!) : null;
  const here = partShown ? partSection : state ? sectionAt(state.doc, state.selection.from) : 0;
  const setup = setups[here];
  const sectionText = JSON.stringify(
    here > 0 ? { id: breaks[here - 1], setup, before: { ...setups[here - 1], start: null } } : null,
  );
  const partNow = useRef<EditorView | null>(null);
  const extent = stack
    ? { width: stack.width, height: stack.height }
    : deckOn
      ? { width: template.size.width * PX_PER_CM, height: deck?.total ?? 0 }
      : null;
  const scale =
    extent && pane
      ? zoom === 'width'
        ? pane / extent.width
        : Math.min(1, pane / extent.width)
      : 1;

  useEffect(() => {
    if (tab) grids.watch(tab);
    const doc = new Y.Doc();
    const { provider, leave, onReady } = joinRoom(room, doc, recheck, keep);
    provider.on('status', (event) => setStatus(event.status));
    onReady((ready) => {
      setSynced(ready);
      if (ready) setShownIn(room);
    });
    const actions: Actions = {
      grids,
      open: openDialog,
      filter: (table, col) => setFiltering({ table, col }),
      ran: (run) => settle(run, provider.awareness),
      consent,
      fail: (error) => setProblem({ error }),
      follow,
      visitTab,
      label,
      styling: stylingNow,
      place,
      notes: tabNotesNow,
      numbers: startNow,
      desk: deskNow,
      parts: partsNow,
      slides: slidesNow,
      present: presentNow,
      contents,
      lists,
      locale: localeNow,
      proposer,
      suggest: setSuggesting,
    };
    const view = liveView(host.current!, doc, provider.awareness, {
      notes: notesHost.current,
      editable: () => editable.current,
      onState: setState,
      onFocus: (focus) => {
        setFocused(focus);
        if (focus) setInner(null);
      },
      onInner: (view) => setInner({ view, state: view.state }),
      actions,
    });
    const changed = () => setRunning(runningIn(provider.awareness));
    provider.awareness.on('change', changed);
    setEditor({ view, doc, provider, actions });
    setState(view.state);
    return () => {
      provider.awareness.off('change', changed);
      setRunning([]);
      setDone(null);
      view.destroy();
      leave();
      doc.destroy();
    };
  }, [grids, tab, room, recheck, keep, follow, visitTab, place, contents, lists, settle, consent]);

  useEffect(() => {
    if (offered.error) setProblem({ error: offered.error });
  }, [offered.error]);

  useEffect(() => {
    if (!editor || !user) return;
    editor.provider.awareness.setLocalStateField('user', {
      id: user.id,
      name: user.name || user.email,
      color: presenceColor(user.id),
    });
  }, [editor, user]);

  useEffect(() => {
    editor?.view.setProps({ editable: () => !readOnly });
  }, [editor, readOnly]);

  useEffect(() => {
    if (!editor) return;
    const element = bar.current!;
    let pane = element.parentElement;
    while (pane && !/auto|scroll/.test(getComputedStyle(pane).overflowY)) pane = pane.parentElement;
    // Unmounting detaches the ref before this effect is cleaned up, and the removal is observed.
    const observer = new ResizeObserver(() => {
      if (!element.isConnected) return;
      const top = element.offsetHeight;
      editor.view.setProps({
        scrollThreshold: { left: 0, right: 0, bottom: 0, top },
        scrollMargin: { left: 5, right: 5, bottom: 5, top: top + 5 },
      });
      // What the bar covers of the pane it stays atop: the browser scrolls what it shows below
      // it, and the tables keep their headings and frozen rows there.
      const covered = top + parseFloat(getComputedStyle(element).top);
      if (pane) pane.style.scrollPaddingTop = `${covered}px`;
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      if (pane) pane.style.scrollPaddingTop = '';
    };
  }, [editor]);

  useEffect(() => {
    const element = around.current!;
    const observer = new ResizeObserver(() => {
      if (!element.isConnected) return;
      const style = getComputedStyle(element);
      setPane(element.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (editor) showPages(editor.view, geometries);
  }, [editor, geometries]);

  useEffect(
    () => onSection(JSON.parse(sectionText) as SectionPages | null),
    [onSection, sectionText],
  );

  useEffect(() => {
    if (editor) showDeck(editor.view, deckOn ? template : null);
  }, [editor, deckOn, template]);

  useEffect(() => {
    if (laid && synced && !readOnly && tab) writePages(own, tab, laid.pages);
  }, [own, tab, laid, synced, readOnly]);

  useEffect(() => {
    if (!editor || !partName || !tab || partFrom === null) return;
    const fragment = sectionPart(own, tab, breaks, partFrom, partName);
    const view = partView(partHost.current!, fragment, {
      context: (view) => ({ ...current.current!, view }),
      value: (kind) => valueOf(kind, numbersNow.current[partPage], fieldsNow.current),
      decimal: () => decimalOf(localeNow.current),
      onState: (view) => setInner({ view, state: view.state }),
      actions: editor.actions,
    });
    partNow.current = view;
    view.focus();
    return () => {
      partNow.current = null;
      view.destroy();
    };
  }, [editor, own, tab, breaks, partFrom, partName, partPage]);

  useEffect(() => {
    partNow.current?.setProps({
      nodeViews: { field: fieldView((kind) => valueOf(kind, numbers[partPage], fields)) },
    });
  }, [fields, numbers, partPage]);

  useEffect(() => {
    if (editor && tabNotes) numberFrom(editor.view, tabNotes.offset);
  }, [editor, tabNotes]);

  useEffect(() => {
    if (editor) renumber(editor.view, styling, start);
  }, [editor, styling, start]);

  useEffect(() => {
    if (!state || !editor || !synced || readOnly || !tab) return;
    writeCounts(own, tab, countsOf(notesIn(state)));
    writeTally(own, tab, numbersOf(state)!.tally);
    writeSlideCount(own, tab, slidesOf(state.doc).length);
    writeHeadings(own, tab, headingsOf(state.doc, linesOf(editor.actions.grids)));
  }, [own, tab, state, editor, synced, readOnly]);

  const active = desk?.active ?? null;
  const drafted = desk?.draft?.tab === tab ? desk.draft.anchor : null;
  const draft = drafted && 'from' in drafted ? drafted : null;
  const anchored = useMemo(
    () =>
      (threads.data ?? []).flatMap((thread) =>
        thread.tab === tab &&
        'from' in thread.anchor &&
        (!thread.resolved_at || thread.id === active)
          ? [{ id: thread.id, anchor: thread.anchor }]
          : [],
      ),
    [threads.data, tab, active],
  );
  useEffect(() => {
    if (editor) showComments(editor.view, { threads: anchored, active, draft });
  }, [editor, anchored, active, draft]);

  const inText = useRef<InText | null>(null);
  inText.current = state && synced ? placedOf(state) : null;
  const inTextKey = inText.current && JSON.stringify(inText.current);
  useEffect(() => {
    deskNow.current?.place(inText.current);
  }, [inTextKey]);
  useEffect(() => () => deskNow.current?.place(null), []);

  const asked = desk?.shown ?? 0;
  const scrolledTo = useRef('');
  useEffect(() => {
    if (!editor || !active || scrolledTo.current === `${active} ${asked}`) return;
    const marked = editor.view.dom.querySelector(`[data-thread="${active}"]`);
    if (!marked) return;
    scrolledTo.current = `${active} ${asked}`;
    const { top, bottom } = marked.getBoundingClientRect();
    if (top < bar.current!.getBoundingClientRect().bottom || bottom > window.innerHeight)
      marked.scrollIntoView({ block: 'center' });
  }, [editor, active, asked, inTextKey]);

  const shown = useRef<string | null>(null);
  useEffect(() => {
    const key = found && `${visit} ${found.block} ${found.cell}`;
    if (!editor || !found || shown.current === key) return;
    const { view, actions } = editor;
    const show = () => {
      if (shown.current !== key && showFound(view, actions.grids, found)) shown.current = key;
    };
    show();
    return actions.grids.subscribe(null, show);
  }, [editor, state, found, visit]);

  useEffect(() => {
    if (!state || !editor) return;
    const { labels } = numbersOf(state)!;
    const shown = outlineOf(state.doc, state.selection.from, labels, linesOf(editor.actions.grids));
    outline.set(shown);
    if (tab) contents.set(chaptersOf(own, tabs, { tab, headings: shown.headings }, styling, home));
  }, [editor, outline, state, contents, own, tabs, tab, styling, home, changes]);
  useEffect(() => () => outline.set(null), [outline]);

  const writing = inner && !inner.view.isDestroyed ? inner.view : null;
  const partControl: Parts | null =
    editor && tab && !readOnly
      ? {
          firstApart: setup.firstPage,
          linked:
            partShown && partSection > 0
              ? partLinked(own, tab, breaks[partSection - 1], partName!)
              : null,
          writing: partShown,
          open: (side) => {
            const at = editor.view.state.selection.from;
            setView('pages');
            setOpened({ side, page: pageAt(pagingOf(editor.view.state)?.laid, at) });
          },
          setFirstApart: (apart) =>
            here > 0
              ? saveSection(own, tab, breaks[here - 1], { ...setup, firstPage: apart })
              : setFirstPage(own, tab, apart),
          setLinked: (linked) => linkPart(own, tab, breaks, partSection, partName!, linked),
          close: () => {
            setOpened(null);
            editor.view.focus();
          },
        }
      : null;
  partsNow.current = partControl;
  const slideControl: Slides | null =
    editor && deckOn && !readOnly ? { template, setSize: (size) => setSlideSize(own, size) } : null;
  slidesNow.current = slideControl;
  const present: Context['present'] =
    editor && tab
      ? (from) => {
          presentFullScreen();
          if (from === 'start') return onPresent('start');
          const { doc, selection } = editor.view.state;
          const slide = slideAt(doc, selection.from);
          const index = slide ? slidesOf(doc).findIndex((each) => each.from === slide.from) : 0;
          onPresent({ tab, index });
        }
      : null;
  presentNow.current = present;
  const context: Context | null = editor
    ? {
        view: writing ?? editor.view,
        doc: editor.doc,
        history: undoOf(writing ?? editor.view, historyIn(editor.view.state)!),
        styling,
        place,
        notes: tabNotes,
        desk,
        parts: partControl,
        slides: slideControl,
        present,
        lists,
        open: openDialog,
        ran: (run) => settle(run, editor.provider.awareness),
        consent,
        fail: (error) => setProblem({ error }),
        label: t,
        suggesting: proposer.current !== null,
        suggest: setSuggesting,
        visitTab,
      }
    : null;
  const current = useRef(context);
  current.current = context;

  useEffect(() => {
    if (!agent || readOnly || !editor) return;
    agent.asker.current = (request, thread, started) => {
      const now = current.current;
      if (now) runAsked({ ...now, ran: started }, 'text.ask', { request, thread });
    };
    return () => {
      agent.asker.current = null;
    };
  }, [agent, readOnly, editor]);

  useEffect(() => {
    const now = current.current;
    const command = requested ? commandOf(requested) : undefined;
    if (!now || !command) return;
    onRequested();
    perform(command, now);
  }, [requested, onRequested, editor]);

  const cursorPage = partShown ? partShown.page : state ? pageAt(laid, state.selection.from) : 0;
  const measured =
    context && PARAGRAPHS.includes(whereOf(context))
      ? textblocks(context.view.state)[0]?.node
      : undefined;
  const paragraph = measured
    ? {
        indents: indentsOf(measured.attrs),
        listed: listOf(measured) !== null,
        stops: stopsOf(measured.attrs.tabs),
      }
    : null;
  const changeSetup = (next: PageSetup) =>
    here > 0 && tab
      ? saveSection(own, tab, breaks[here - 1], next)
      : savePages(own, tab, next, ownsPages(own, tab));
  const runOnText = (command: Command) => {
    const view = current.current?.view;
    if (view) command(view.state, view.dispatch);
  };

  const toEnd = (event: ReactMouseEvent) => {
    const target = event.target as globalThis.Node;
    if (partBox.current?.contains(target)) return;
    if (partShown) setOpened(null);
    if (!editor || !stack || readOnly || event.button !== 0) return;
    const { view } = editor;
    if (view.dom.contains(target) || notesHost.current!.contains(target)) return;
    if (event.clientY < view.dom.getBoundingClientRect().bottom) return;
    event.preventDefault();
    view.focus();
    view.dispatch(view.state.tr.setSelection(Selection.atEnd(view.state.doc)).scrollIntoView());
  };

  /** Opens the header or footer of the page a double click lands in the margin of. */
  const openAt = (event: ReactMouseEvent) => {
    if (!partControl || !stack || partBox.current?.contains(event.target as globalThis.Node))
      return;
    const box = sheets.current!.getBoundingClientRect();
    const x = (event.clientX - box.left) / scale;
    const y = (event.clientY - box.top) / scale;
    const index = stack.pages.findIndex(
      ({ top, geometry }) => y >= top && y < top + geometry.height + geometry.gap,
    );
    if (index < 0) return;
    const { top: above, left, geometry } = stack.pages[index];
    const within = y - above;
    if (x < left || x > left + geometry.width) return;
    const opening = opensSection(owners, index);
    const top = opening ? geometry.firstTop : geometry.top;
    const bottom = geometry.height - (opening ? geometry.firstBottom : geometry.bottom);
    const side =
      within < top ? 'header' : within > bottom && within <= geometry.height ? 'footer' : null;
    if (!side) return;
    event.preventDefault();
    setOpened({ side, page: index });
  };

  useProvidePalette(
    useCallback(
      (query: string): Choice[] =>
        current.current
          ? choices(commandsOf(current.current.styling), current.current, label.current, query)
          : [],
      [],
    ),
  );

  return (
    <section className="flex flex-col">
      <style>{sheet}</style>
      <div
        ref={bar}
        className={`sticky -top-4 z-10 -mt-4 pt-4 pb-3 ${extent ? '-mx-4 bg-field px-4' : 'bg-surface'}`}
      >
        <div className="flex items-center gap-2 rounded-full bg-panel px-3 py-1">
          {context && state && !readOnly && <Toolbar context={context} />}
          <div className="ml-auto flex shrink-0 items-center gap-0.5">
            <Choices
              label={t('view.label')}
              choices={VIEWS}
              chosen={view}
              icons={VIEW_ICONS}
              labelOf={(each) => t(`view.${each}`)}
              onChoose={(next) => {
                setOpened(null);
                setView(next);
              }}
            />
            {extent && (
              <>
                <span aria-hidden className="mx-1 h-5 w-px bg-line" />
                <ZoomChoices zoom={zoom} onChoose={setZoom} />
              </>
            )}
            <span
              className={`ml-2 text-sm ${status === 'disconnected' ? 'text-danger' : 'text-muted'}`}
            >
              {t(`collab.${status}`)}
            </span>
          </div>
        </div>
        {(dialog === 'find' || dialog === 'replace') && context && (
          <FindBar
            context={context}
            replacing={dialog === 'replace'}
            onClose={() => setDialog(null)}
          />
        )}
        {stack && (
          <div className="mt-2 flex justify-center">
            <HorizontalRuler
              setup={setup}
              scale={scale}
              paragraph={paragraph}
              readOnly={readOnly}
              onSetup={changeSetup}
              onRun={runOnText}
              onStops={() => setDialog('tabStops')}
              onMenuClose={() => current.current && refocus(current.current)}
            />
          </div>
        )}
      </div>
      <ContextMenuArea
        onCloseFocus={() => current.current && refocus(current.current)}
        onOpen={(event) => {
          if (!editor) return;
          const view = cellViewAt(event.target) ?? editor.view;
          selectFigureAt(view, event.target);
          cursorAt(view, event);
        }}
        items={context && <EditorMenu context={context} />}
      >
        <div
          ref={around}
          className={`relative @container ${extent ? 'ponistra-field' : ''}`}
          onMouseDown={toEnd}
          onDoubleClick={openAt}
        >
          <div
            className={extent ? 'ponistra-stack' : 'contents'}
            style={
              extent ? { width: extent.width * scale, height: extent.height * scale } : undefined
            }
          >
            {stack && (
              <div
                className="ponistra-vertical"
                style={{
                  top: stack.pages[cursorPage].top * scale,
                  right: `calc(100% + 0.25rem - ${stack.pages[cursorPage].left * scale}px)`,
                }}
              >
                <VerticalRuler
                  setup={setup}
                  scale={scale}
                  header={
                    heights[here]?.[
                      partOn('header', opensSection(owners, cursorPage), setup.firstPage)
                    ] ?? 0
                  }
                  footer={
                    heights[here]?.[
                      partOn('footer', opensSection(owners, cursorPage), setup.firstPage)
                    ] ?? 0
                  }
                  readOnly={readOnly}
                  onSetup={changeSetup}
                />
              </div>
            )}
            <div
              ref={sheets}
              className={extent ? 'ponistra-sheets' : 'contents'}
              style={extent ? { width: extent.width, transform: `scale(${scale})` } : undefined}
            >
              {stack && grids && (
                <>
                  <PartMeasures
                    sections={sections}
                    fields={fields}
                    decimal={decimal}
                    scope={scope}
                    grids={grids}
                    onHeights={keepHeights}
                  />
                  <Papers
                    stack={stack}
                    sections={sections}
                    numbers={numbers}
                    fields={fields}
                    decimal={decimal}
                    scope={scope}
                    writing={partShown}
                    grids={grids}
                  />
                </>
              )}
              {deck && (
                <Frames
                  deck={deck}
                  cursor={focused && state ? state.selection.from : null}
                  editable={!readOnly}
                  date={date}
                  scope={scope}
                  first={tab ? slidesBefore(own, ids, tab) : 0}
                />
              )}
              <div
                data-styling={scope}
                style={
                  {
                    '--placeholder': JSON.stringify(t('editor.placeholder')),
                    '--note-placeholder': JSON.stringify(t('note.placeholder')),
                    '--page-break': JSON.stringify(t('command.pageBreak')),
                    '--section-break': JSON.stringify(t('command.sectionBreak')),
                    '--slide-break': JSON.stringify(t('command.slideBreak')),
                    '--column-break': JSON.stringify(t('command.columnBreak')),
                    ...(stack && {
                      paddingTop: stack.pages[0].geometry.firstTop,
                      paddingRight: stack.pages[0].left + stack.pages[0].geometry.right,
                      paddingLeft: stack.pages[0].left + stack.pages[0].geometry.left,
                      '--page-left': `${stack.pages[0].left + stack.pages[0].geometry.left}px`,
                      '--page-right': `${stack.pages[0].left + stack.pages[0].geometry.right}px`,
                    }),
                  } as CSSProperties
                }
                className={
                  stack
                    ? 'ponistra-document ponistra-pages'
                    : deckOn
                      ? 'ponistra-document ponistra-slides'
                      : page
                }
              >
                {/* Text written before the room syncs is lost if the page is left before its
                    socket opens, so the tab shows only once the room or the device holds it. */}
                <div ref={host} className={shownIn === room ? undefined : 'invisible'} />
                <div ref={notesHost} className={shownIn === room ? undefined : 'invisible'} />
              </div>
              {partShown && stack && (
                <div
                  ref={partBox}
                  data-styling={scope}
                  className={`ponistra-part ponistra-part-open ponistra-${partShown.side}`}
                  style={partPlace(stack.pages[partShown.page], partShown.side)}
                >
                  <div ref={partHost} />
                  <span className="ponistra-part-label">{t(`part.${partName!}`)}</span>
                </div>
              )}
            </div>
          </div>
          {editor && state && <SlashMenu view={editor.view} state={state} around={around} />}
          {context && state && focused && !dialog && (
            <ProposalPopover context={context} around={around} editable={!readOnly} />
          )}
          {editor && state && focused && !readOnly && !dialog && (
            <LinkPopover
              view={editor.view}
              state={state}
              around={around}
              onFollow={follow}
              onEdit={() => setDialog('link')}
            />
          )}
        </div>
      </ContextMenuArea>
      {dialog === 'shortcuts' && <Shortcuts onClose={() => setDialog(null)} />}
      {dialog === 'link' && editor && (
        <LinkDialog view={writing ?? editor.view} onClose={() => setDialog(null)} />
      )}
      {dialog === 'image' && editor && (
        <ImageDialog
          view={writing ?? editor.view}
          host={{ document: place.document, fail: (error) => setProblem({ error }), label: t }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'imageAlt' && editor && (
        <AltDialog view={editor.view} onClose={() => setDialog(null)} />
      )}
      {dialog === 'imageEdit' && editor && (
        <ImageEditDialog
          view={editor.view}
          host={{ document: place.document, fail: (error) => setProblem({ error }), label: t }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'pdf' && editor && (
        <PdfDialog
          view={editor.view}
          host={{ document: place.document, fail: (error) => setProblem({ error }), label: t }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'pdfPages' && editor && (
        <PdfPagesDialog view={editor.view} onClose={() => setDialog(null)} />
      )}
      {dialog === 'tableName' && editor && (
        <TableNameDialog view={editor.view} onClose={() => setDialog(null)} />
      )}
      {dialog === 'goTo' && context && (
        <GoToDialog context={context} onClose={() => setDialog(null)} />
      )}
      {dialog === 'compare' && context && (
        <CompareDialog
          documentId={place.document}
          onCompare={(version) => runAsked(context, 'document.compare', { version })}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'compareFile' && context && (
        <CompareFileDialog
          documentId={place.document}
          onCompare={(file) => runAsked(context, 'file.compare', { file })}
          onFail={context.fail}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'task' && editor && (
        <TaskDialog
          draft={lineTask(editor.view.state, place.address)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'calculate' && context && editor && (
        <CalculateDialog
          view={writing ?? editor.view}
          onCalculate={(parameters) => runAsked(context, 'table.calculate', parameters)}
          onClose={() => setDialog(null)}
        />
      )}
      {filtering && editor && (
        <FilterDialog
          grids={editor.actions.grids}
          {...filtering}
          onClose={() => setFiltering(null)}
        />
      )}
      {dialog === 'chart' && editor && (
        <ChartDialog
          view={editor.view}
          writing={writing ?? editor.view}
          grids={editor.actions.grids}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'cellFormat' && editor && (
        <CellFormatDialog view={writing ?? editor.view} onClose={() => setDialog(null)} />
      )}
      {dialog === 'listFormat' && editor && (
        <ListFormatDialog
          view={writing ?? editor.view}
          lists={lists}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'tabStops' && editor && (
        <TabStopsDialog
          view={writing ?? editor.view}
          width={setup.width - setup.left - setup.right}
          onClose={() => setDialog(null)}
        />
      )}
      {consenting && (
        <ConsentDialog
          onChoose={(given) => {
            setConsenting(null);
            if (given === 'once') return consenting('once');
            postJson(`/api/nodes/${documentId}/ai`).then(
              (found) => {
                queryClient.setQueryData(['ai-consent', documentId], found);
                consenting('always');
              },
              (error: unknown) => setProblem({ error }),
            );
          }}
          onClose={() => setConsenting(null)}
        />
      )}
      <RunBar
        running={running}
        done={done}
        onStop={
          readOnly ? null : (run) => stopRun(run).catch((error: unknown) => setProblem({ error }))
        }
        onUndo={() => {
          if (!done) return;
          undoRun(done.id).then(
            () => setDone(null),
            (error) => setProblem({ error }),
          );
        }}
        onClose={() => setDone(null)}
      />
      {problem && <Problem error={problem.error} onClose={() => setProblem(null)} />}
    </section>
  );
}

/** The backend's actions, offered among the commands once they arrive. */
function useActions(language: Language) {
  return useQuery({
    queryKey: ['actions', language],
    queryFn: async () => {
      const { actions, ai } = await getJson<{ actions: Action[]; ai: boolean }>('/api/actions');
      offerActions(actions, ai, language);
      return actions;
    },
    staleTime: Infinity,
  });
}

/** A tab's text as saved, for reading only, `plugins` before the rest. */
export function savedView(
  host: HTMLElement,
  saved: Y.Doc,
  options: {
    /** The tab the text is, and where its tables' grids are. */
    tab: string;
    grids: GridSource;
    /** Its tables laid out whole for paper. */
    paper?: boolean;
    notes: HTMLElement;
    styling: Styling;
    lists: ListStore;
    start: Counters;
    offset: Counts;
    follow: (href: string) => void;
    contents: ContentsStore;
    label: RefObject<(key: MessageKey) => string>;
    locale: RefObject<DocumentLocale>;
    plugins: readonly Plugin[];
    /** Leaves each PDF page's place for the server to put the page in. */
    printing?: boolean;
    onState?: (state: EditorState) => void;
  },
): EditorView {
  const { lists, follow, contents, label, locale } = options;
  const list = new NoteList(options.notes, { label: () => label.current, onNote: () => {} });
  const numberOf = (block: Node) => numberIn(view.state, block);
  const view: EditorView = new EditorView(host, {
    state: EditorState.create({
      doc: yXmlFragmentToProseMirrorRootNode(bodyOf(saved), schema),
      plugins: [
        ...options.plugins,
        listMarkers(lists),
        tabStops(() => decimalOf(locale.current)),
        numberingPlugin(options.styling, options.start, options.grids),
        followLinks(follow),
        notesPlugin({
          list,
          inner: [followLinks(follow), proposalsPlugin()],
          offset: options.offset,
        }),
        proposalsPlugin(),
        tablesPlugin({
          doc: saved,
          grids: options.grids,
          write: null,
          history: null,
          tab: () => options.tab,
          paper: options.paper,
          inner: [
            listMarkers(lists),
            followLinks(follow),
            tabStops(() => decimalOf(locale.current)),
            proposalsPlugin(),
          ],
          nodeViews: {
            contents: (node, view) => new ContentsView(node, view, contents, () => label.current),
          },
          onCell: () => {},
          label: () => label.current,
          locale: () => locale.current,
          fail: (error) => {
            throw error;
          },
        }),
      ],
    }),
    editable: () => false,
    nodeViews: {
      pdf: (node, view, getPos, decorations) =>
        new PdfBlockView(node, view, getPos, decorations, {
          waiting: label.current('pdf.waiting'),
          unshown: label.current('pdf.unshown'),
          printing: Boolean(options.printing),
        }),
      footnote: (node, view, getPos) => new NoteView(node, view, getPos),
      contents: (node, view) => new ContentsView(node, view, contents, () => label.current),
      chart: (node) =>
        new ChartView(node, saved, { label: () => label.current, locale: () => locale.current }),
    },
    clipboardSerializer: clipboardSerializer(lists, numberOf),
    clipboardTextSerializer: clipboardText(lists, numberOf),
    dispatchTransaction(this: EditorView, transaction: Transaction) {
      if (this.isDestroyed) return;
      const next = this.state.apply(transaction);
      this.updateState(next);
      options.onState?.(next);
    },
  });
  return view;
}

function SavedDocument({
  state,
  own,
  grids,
  home,
  tabs,
  tab,
  found,
  outline,
  locale,
}: {
  state: Uint8Array;
  own: Uint8Array;
  grids: GridSource;
  home: string;
  tabs: readonly Pick<Tab, 'id' | 'title'>[];
  tab: string;
  found: Found | null;
  outline: OutlineStore;
  locale: DocumentLocale;
}) {
  const { key: visit } = useLocation();
  const host = useRef<HTMLDivElement>(null);
  const notesHost = useRef<HTMLDivElement>(null);
  const { t } = useI18n();
  const label = useRef(t);
  label.current = t;
  const localeNow = useRef(locale);
  localeNow.current = locale;
  const { styling, offset, start, lists } = useMemo(() => {
    const saved = new Y.Doc();
    Y.applyUpdate(saved, own);
    const ids = tabs.map(({ id }) => id);
    const found = {
      styling: stylingOf(saved),
      offset: offsetOf(saved, ids, tab),
      start: startOf(saved, ids, tab),
      lists: savedLists(formatsOf(saved)),
    };
    saved.destroy();
    return found;
  }, [own, tabs, tab]);
  const { scope, sheet } = useStylesheet(styling);
  const [saved, setSaved] = useState<EditorView | null>(null);
  const follow = useFollow();
  const go = useGo();
  const contents = useMemo(() => contentsStore(go), [go]);

  useEffect(() => {
    const saved = new Y.Doc();
    Y.applyUpdate(saved, state);
    const view = savedView(host.current!, saved, {
      tab,
      grids,
      notes: notesHost.current!,
      styling,
      lists,
      start,
      offset,
      follow,
      contents,
      label,
      locale: localeNow,
      plugins: [foundPlugin()],
    });
    setSaved(view);
    const shown = outlineOf(view.state.doc, null, numbersOf(view.state)!.labels, linesOf(grids));
    outline.set(shown);
    const kept = new Y.Doc();
    Y.applyUpdate(kept, own);
    contents.set(chaptersOf(kept, tabs, { tab, headings: shown.headings }, styling, home));
    kept.destroy();
    return () => {
      outline.set(null);
      view.destroy();
      saved.destroy();
    };
  }, [
    state,
    own,
    grids,
    home,
    tabs,
    tab,
    follow,
    offset,
    styling,
    start,
    outline,
    contents,
    lists,
  ]);

  const shown = useRef<string | null>(null);
  useEffect(() => {
    const key = found && `${visit} ${found.block} ${found.cell}`;
    if (!saved || !found || shown.current === key) return;
    if (showFound(saved, grids, found)) shown.current = key;
  }, [saved, grids, found, visit]);

  return (
    <div className="@container">
      <style>{sheet}</style>
      <div data-styling={scope} className={page}>
        <div ref={host} />
        <div ref={notesHost} />
      </div>
    </div>
  );
}

function useSaved(url: string) {
  return useQuery({
    queryKey: ['saved', url],
    queryFn: () => getBytes(url),
    staleTime: Infinity,
  });
}

/** A tab as the version `version` holds it, with the version's own state and the tab's grids. */
export function SavedEditor({
  version,
  home,
  tabs,
  tab,
  found,
  outline,
  locale,
}: {
  version: string;
  /** The version's address, under which each of its tabs has its own. */
  home: string;
  tabs: readonly Pick<Tab, 'id' | 'title'>[];
  tab: string;
  found: Found | null;
  outline: OutlineStore;
  locale: DocumentLocale;
}) {
  const { t } = useI18n();
  const saved = useSaved(`/api/versions/${version}/tabs/${tab}/state`);
  const own = useSaved(`/api/versions/${version}/state`);
  const wholes = useQuery({
    queryKey: ['saved', version, tab, 'grids'],
    queryFn: () => getJson<KeptOutlines>(`/api/versions/${version}/tabs/${tab}/grids`),
    staleTime: Infinity,
  });
  const grids = useMemo(
    () =>
      wholes.data &&
      new KeptGrids(wholes.data, (path) => getJson(`/api/versions/${version}/${path}`)),
    [wholes.data, version],
  );
  const failed = saved.error ?? own.error ?? wholes.error;
  if (failed) return <Failure error={failed} />;
  if (!saved.data || !own.data || !grids) return <p className="text-muted">{t('tree.loading')}</p>;
  return (
    <SavedDocument
      state={saved.data}
      own={own.data}
      grids={grids}
      home={home}
      tabs={tabs}
      tab={tab}
      found={found}
      outline={outline}
      locale={locale}
    />
  );
}

/** The task a line of the document starts: its selected words, else the whole line, leading
 * back to the block it is in. */
function lineTask(state: EditorState, address: string): Draft {
  const { $from, from, to, empty } = state.selection;
  const text = (empty ? $from.parent.textContent : state.doc.textBetween(from, to, ' '))
    .replace(/\s+/g, ' ')
    .trim();
  const block = typeof $from.parent.attrs.id === 'string' ? $from.parent.attrs.id : null;
  return {
    text,
    source: {
      kind: 'document',
      label: document.title.replace(/ – Ponistra$/, ''),
      link: block ? `${address}?${new URLSearchParams({ block })}` : address,
    },
  };
}
