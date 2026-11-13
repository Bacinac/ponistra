// @vitest-environment jsdom
import { NodeSelection, TextSelection } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Awareness } from 'y-protocols/awareness';
import * as Y from 'yjs';
import { segment } from '../address';
import { hr } from '../i18n/hr';
import { shortcutLabel } from '../keys';
import { actionLabel, offerActions, offeredAction, runAsked } from './actions';
import type { Context, Dialog } from './command';
import {
  available,
  choices,
  COMMANDS,
  commandsOf,
  inGroup,
  labelOf,
  perform,
  styleCommands,
  whereOf,
} from './commands';
import { ApiError } from '../api';
import { contentsStore } from './contents';
import { formatsOf, listStore, standard } from './forms';
import { GridClient } from './grids';
import { historyIn } from './history';
import { formatList, levelsAt } from './lists';
import { liveView, type Actions } from './Editor';
import { linkAt, removeLink, setLink } from './links';
import type { Consent, Run } from './runs';
import { slashKey } from './slash';
import { INDENT_MAX, INDENT_STEP, schema } from './schema';
import type { Style, Styling } from './styling';

/** Grids no server answers: these tests write no table's cells. */
function closedGrids(): GridClient {
  const grids = new GridClient('00000000-0000-0000-0000-000000000001');
  grids.close();
  return grids;
}

const views: EditorView[] = [];
afterEach(() => {
  views.splice(0).forEach((view) => view.destroy());
  vi.restoreAllMocks();
});

function style(kind: Style['kind'], look: Partial<Style> = {}): Style {
  return {
    kind,
    name: '',
    font: 'text',
    size: 12,
    bold: false,
    italic: false,
    color: null,
    align: null,
    before: 0,
    after: 9,
    line: 1.6,
    numbering: '',
    prefix: '',
    suffix: '',
    nested: false,
    kerning: true,
    ...look,
  };
}

const STYLING: Styling = {
  theme: { headings: 'Inter', text: 'Inter' },
  styles: {
    text: style('text'),
    h2: style('h2', { font: 'headings', size: 16, bold: true }),
    note: style('text', { name: 'Napomena', italic: true }),
  },
};

const ACTIONS: Actions = {
  open: () => {},
  filter: () => {},
  ran: () => {},
  consent: () => {},
  fail: (error) => {
    throw error;
  },
  follow: () => {},
  label: { current: (key) => hr[key] },
  place: {
    document: '00000000-0000-0000-0000-000000000001',
    tab: '00000000-0000-0000-0000-000000000002',
    address: '/d/probni-dokument-0000000000000000000001',
  },
  styling: { current: STYLING },
  notes: { current: null },
  numbers: { current: {} },
  locale: { current: 'hr' },
  proposer: { current: null },
  suggest: () => {},
  visitTab: () => false,
  desk: { current: null },
  parts: { current: null },
  slides: { current: null },
  present: { current: null },
  contents: contentsStore(() => {}),
  lists: listStore(new Y.Doc()),
  grids: closedGrids(),
};

function editor(ydoc = new Y.Doc(), actions = ACTIONS): EditorView {
  const view = liveView(
    document.body.appendChild(document.createElement('div')),
    ydoc,
    new Awareness(ydoc),
    {
      notes: null,
      editable: () => true,
      onState: () => {},
      onFocus: () => {},
      onInner: () => {},
      actions,
    },
  );
  views.push(view);
  return view;
}

function contextOf(view: EditorView, ydoc: Y.Doc, inner: EditorView | null = null): Context {
  const history = historyIn(view.state)!;
  return {
    view: inner ?? view,
    doc: ydoc,
    history,
    styling: STYLING,
    place: ACTIONS.place,
    notes: null,
    desk: null,
    parts: null,
    slides: null,
    present: null,
    lists: ACTIONS.lists,
    open: ACTIONS.open,
    ran: ACTIONS.ran,
    consent: ACTIONS.consent,
    fail: ACTIONS.fail,
    label: ACTIONS.label.current,
    suggesting: false,
    suggest: ACTIONS.suggest,
    visitTab: ACTIONS.visitTab,
  };
}

function command(id: string) {
  return COMMANDS.find((found) => found.id === id)!;
}

function paste(): ClipboardEvent {
  return new Event('paste') as ClipboardEvent;
}

function press(view: EditorView, key: string, init: KeyboardEventInit = {}): void {
  view.dom.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...init }));
}

function written(...lines: string[]): { view: EditorView; ydoc: Y.Doc } {
  const ydoc = new Y.Doc();
  const view = editor(ydoc);
  lines.forEach((line, index) => {
    if (index) view.dispatch(view.state.tr.split(view.state.selection.from));
    view.dispatch(view.state.tr.insertText(line));
  });
  const end = view.state.doc.content.size - 1;
  view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1, end)));
  return { view, ydoc };
}

function marksOf(view: EditorView): string[] {
  return view.state.doc.firstChild!.firstChild!.marks.map((mark) =>
    mark.attrs.color ? `${mark.type.name}:${mark.attrs.color}` : mark.type.name,
  );
}

function blockAttrs(view: EditorView, name: string): unknown[] {
  const found: unknown[] = [];
  view.state.doc.forEach((node) => found.push(node.attrs[name]));
  return found;
}

function type(view: EditorView, text: string): void {
  const { from, to } = view.state.selection;
  const handled = view.someProp('handleTextInput', (handle) =>
    handle(view, from, to, text, () => view.state.tr.insertText(text, from, to)),
  );
  if (!handled) view.dispatch(view.state.tr.insertText(text, from, to));
}

describe('shortcut labels', () => {
  it('read as each platform writes them', () => {
    expect(['Mod-b', 'Shift-Mod-z', 'Mod-/'].map((keys) => shortcutLabel(keys, false))).toEqual([
      'Ctrl+B',
      'Ctrl+Shift+Z',
      'Ctrl+/',
    ]);
    expect(['Mod-b', 'Shift-Mod-z'].map((keys) => shortcutLabel(keys, true))).toEqual([
      '⌘B',
      '⇧⌘Z',
    ]);
  });
});

describe('the registry', () => {
  it('names every command once', () => {
    const ids = COMMANDS.map((found) => found.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('binds its shortcuts in the text', () => {
    const view = editor();
    view.dispatch(view.state.tr.insertText('Ukupno', 1));
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1, 7)));
    press(view, 'b', { ctrlKey: true });
    expect(view.state.doc.firstChild!.firstChild!.marks.map((mark) => mark.type.name)).toEqual([
      'strong',
    ]);
  });

  it('offers the backend’s actions, each with its label, none where its target is not', () => {
    const totals = {
      id: 'table.totals',
      target: 'table',
      parameters: {},
      review: 'apply',
      model: null,
    } as const;
    try {
      offerActions([totals], false, 'hr');
      const { view, ydoc } = written('Uvod');
      const offered = inGroup('tableData').find((found) => found.id === 'action.table.totals')!;
      expect(labelOf(offered, (key) => hr[key])).toBe('Zbroji stupce');
      expect(available(offered, contextOf(view, ydoc))).toBe(false);
      offerActions(
        [totals, { ...totals, id: 'table.analyse', model: 'claude-opus-5-5' }],
        true,
        'hr',
      );
      const analyse = offeredAction('table.analyse')!;
      expect([analyse.group, labelOf(analyse, (key) => hr[key])]).toEqual([
        'tableData',
        'Analiziraj u novoj kartici',
      ]);
      expect(() => offerActions([{ ...totals, id: 'table.unknown' }], false, 'hr')).toThrow();
    } finally {
      offerActions([], false, 'hr');
    }
  });

  it('offers the calculated column as a command that opens its dialog', () => {
    const calculate = {
      id: 'table.calculate',
      target: 'column',
      parameters: {
        type: 'object',
        properties: {
          operation: { enum: ['sum', 'product'] },
          columns: { type: 'array', items: { type: 'string' }, minItems: 2 },
        },
        required: ['operation', 'columns'],
        additionalProperties: false,
      },
      review: 'apply',
      model: null,
    } as const;
    try {
      offerActions([calculate], false, 'hr');
      const opens = offeredAction('table.calculate')!;
      expect(opens.group).toBe('tableData');
      expect(labelOf(opens, (key) => hr[key])).toBe('Izračunati stupac…');
      const opened: string[] = [];
      const { view, ydoc } = written('Uvod');
      opens.run({ ...contextOf(view, ydoc), open: (dialog) => opened.push(dialog) });
      expect(opened).toEqual(['calculate']);
    } finally {
      offerActions([], false, 'hr');
    }
  });

  it('offers the total of a column one of several ways, each labelled in the submenu', () => {
    const total = {
      id: 'table.total',
      target: 'column',
      parameters: {
        type: 'object',
        properties: { function: { enum: ['sum', 'none'] } },
        required: ['function'],
        additionalProperties: false,
      },
      review: 'apply',
      model: null,
    } as const;
    try {
      offerActions([total], false, 'hr');
      const opens = offeredAction('table.total')!;
      expect([opens.group, opens.sub]).toEqual(['tableData', 'total']);
      expect(inGroup('total').map((way) => labelOf(way, (key) => hr[key]))).toEqual([
        'Ukupno u stupcu: zbroj',
        'Ukupno u stupcu: ništa',
      ]);
    } finally {
      offerActions([], false, 'hr');
    }
  });

  it('leaves an action on documents to the folder, labelled for the runs it shows', () => {
    const gathering = {
      id: 'nodes.extract',
      target: 'nodes',
      parameters: {},
      review: 'apply',
      model: 'claude-sonnet-5-5',
    } as const;
    try {
      offerActions([gathering], true, 'hr');
      expect(offeredAction('nodes.extract')).toBeUndefined();
      expect(hr[actionLabel('nodes.extract')]).toBe('Izvuci podatke u tablicu');
    } finally {
      offerActions([], false, 'hr');
    }
  });
});

describe('the actions of a model', () => {
  const summarise = {
    id: 'text.summarise',
    target: 'text',
    parameters: {},
    review: 'propose',
    model: 'claude-sonnet-5-5',
  } as const;
  const json = { 'Content-Type': 'application/json' };

  it('are shown disabled, with why, while the installation’s AI is off', () => {
    try {
      offerActions([summarise], false, 'hr');
      const { view, ydoc } = written('Uvod');
      const offered = inGroup('writing').find((found) => found.id === 'action.text.summarise')!;
      expect(labelOf(offered, (key) => hr[key])).toBe('Sažmi');
      expect(available(offered, contextOf(view, ydoc))).toBe(false);
      expect(offered.why).toBe('ai.off');
    } finally {
      offerActions([], false, 'hr');
    }
  });

  it('send the blocks selected once the user lets them, asked first', async () => {
    const answers = [
      new Response(JSON.stringify({ error: 'consent_needed' }), { status: 428, headers: json }),
      new Response(JSON.stringify({ run: { id: 'r', state: 'running' } }), {
        status: 202,
        headers: json,
      }),
    ];
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => answers.shift()!);
    const asked: ((consent: Consent) => void)[] = [];
    const ran: Run[] = [];
    try {
      offerActions([summarise], true, 'hr');
      const { view, ydoc } = written('Uvod', 'Cijena');
      const context: Context = {
        ...contextOf(view, ydoc),
        consent: (go) => asked.push(go),
        ran: (run) => ran.push(run),
      };
      const offered = offeredAction('text.summarise')!;
      expect(offered.why).toBeUndefined();
      expect(available(offered, context)).toBe(true);
      perform(offered, context);
      await vi.waitFor(() => expect(asked).toHaveLength(1));
      const ids: string[] = [];
      view.state.doc.forEach((node) => ids.push(node.attrs.id));
      expect(ids).toHaveLength(2);
      expect(JSON.parse(fetch.mock.calls[0][1]!.body as string)).toEqual({
        action: 'text.summarise',
        target: { blocks: ids },
        parameters: {},
      });
      asked[0]('once');
      await vi.waitFor(() => expect(ran).toEqual([{ id: 'r', state: 'running' }]));
      expect(JSON.parse(fetch.mock.calls[1][1]!.body as string).consent).toBe('once');
    } finally {
      offerActions([], false, 'hr');
      fetch.mockRestore();
    }
  });

  it('run one of several ways from a submenu, the way chosen sent with the run', async () => {
    const rewrite = {
      id: 'text.rewrite',
      target: 'text',
      parameters: {
        type: 'object',
        properties: { way: { enum: ['formal', 'correct'] } },
        required: ['way'],
        additionalProperties: false,
      },
      review: 'propose',
      model: 'claude-opus-5-5',
    } as const;
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response(JSON.stringify({ run: { id: 'r', state: 'running' } }), {
          status: 202,
          headers: json,
        }),
    );
    const ran: Run[] = [];
    try {
      offerActions([rewrite], true, 'hr');
      const { view, ydoc } = written('Uvod');
      const context: Context = { ...contextOf(view, ydoc), ran: (run) => ran.push(run) };
      const opens = offeredAction('text.rewrite')!;
      expect([opens.group, opens.sub]).toEqual(['writing', 'rewrite']);
      const ways = inGroup('rewrite');
      expect(ways.map((way) => labelOf(way, (key) => hr[key]))).toEqual([
        'Prepiši: formalnije',
        'Prepiši: ispravi pravopis i gramatiku',
      ]);
      perform(ways[1], context);
      await vi.waitFor(() => expect(ran).toHaveLength(1));
      const body = JSON.parse(fetch.mock.calls[0][1]!.body as string);
      expect([body.action, body.parameters]).toEqual(['text.rewrite', { way: 'correct' }]);
      const unknown = { ...rewrite.parameters, properties: { way: { enum: ['poetic'] } } };
      expect(() => offerActions([{ ...rewrite, parameters: unknown }], true, 'hr')).toThrow(
        'The action text.rewrite has no look for poetic',
      );
    } finally {
      offerActions([], false, 'hr');
      fetch.mockRestore();
    }
  });

  it('ask for the parameters an action needs in its own dialog, then run where the cursor is', async () => {
    const compare = {
      id: 'document.compare',
      target: 'document',
      parameters: {
        type: 'object',
        properties: { version: { type: 'string' } },
        required: ['version'],
        additionalProperties: false,
      },
      review: 'propose',
      model: 'claude-sonnet-5-5',
    } as const;
    const ask = {
      ...compare,
      id: 'text.ask',
      target: 'text',
      parameters: {
        type: 'object',
        properties: { request: { type: 'string', minLength: 1, maxLength: 4000 } },
        required: ['request'],
        additionalProperties: false,
      },
      model: 'claude-opus-5-5',
    } as const;
    const fetch = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response(JSON.stringify({ run: { id: 'r', state: 'running' } }), {
          status: 202,
          headers: json,
        }),
    );
    const opened: Dialog[] = [];
    const ran: Run[] = [];
    try {
      offerActions([compare, ask], true, 'hr');
      const { view, ydoc } = written('Uvod', 'Cijena');
      const context: Context = {
        ...contextOf(view, ydoc),
        open: (dialog) => opened.push(dialog),
        ran: (run) => ran.push(run),
      };
      const commands = [offeredAction('document.compare')!, offeredAction('text.ask')!];
      expect(commands.map((command) => [command.group, command.sub])).toEqual([
        ['writing', undefined],
        ['writing', undefined],
      ]);
      expect(commands.map((command) => labelOf(command, (key) => hr[key]))).toEqual([
        'Usporedi s verzijom…',
        'Drugo…',
      ]);
      for (const command of commands) perform(command, context);
      expect(opened).toEqual(['compare', 'ask']);
      expect(fetch).not.toHaveBeenCalled();
      runAsked(context, 'document.compare', { version: 'v' });
      runAsked(context, 'text.ask', { request: 'Skrati.' });
      await vi.waitFor(() => expect(ran).toHaveLength(2));
      const ids: string[] = [];
      view.state.doc.forEach((node) => ids.push(node.attrs.id));
      const bodies = fetch.mock.calls.map(([, init]) => JSON.parse(init!.body as string));
      expect(bodies.map((body) => [body.action, body.target, body.parameters])).toEqual([
        ['document.compare', {}, { version: 'v' }],
        ['text.ask', { blocks: ids }, { request: 'Skrati.' }],
      ]);
      expect(() => runAsked(context, 'text.missing', {})).toThrow(
        'The action text.missing is not offered',
      );
    } finally {
      offerActions([], false, 'hr');
      fetch.mockRestore();
    }
  });

  it('name the languages a document translates into in the interface’s language', () => {
    const translate = {
      id: 'document.translate',
      target: 'document',
      parameters: {
        type: 'object',
        properties: { language: { enum: ['en', 'en-GB', 'de'] } },
        required: ['language'],
        additionalProperties: false,
      },
      review: 'apply',
      model: 'claude-opus-5-5',
    } as const;
    try {
      offerActions([translate], true, 'hr');
      expect([
        offeredAction('document.translate')!.group,
        offeredAction('document.translate')!.sub,
      ]).toEqual(['writing', 'translate']);
      const named = () => inGroup('translate').map((way) => labelOf(way, (key) => hr[key]));
      expect(named()).toEqual([
        'Prevedi u novu karticu: Američki engleski',
        'Prevedi u novu karticu: Britanski engleski',
        'Prevedi u novu karticu: Njemački',
      ]);
      offerActions([translate], true, 'en');
      expect(inGroup('translate').map((way) => way.sample)).toEqual([
        'American English',
        'British English',
        'German',
      ]);
    } finally {
      offerActions([], false, 'hr');
    }
  });
});

describe('formatting', () => {
  it('binds underline and keeps subscript and superscript apart', () => {
    const { view } = written('H2O');
    press(view, 'u', { ctrlKey: true });
    press(view, ',', { ctrlKey: true });
    expect(marksOf(view)).toEqual(['underline', 'sub']);
    press(view, '.', { ctrlKey: true });
    expect(marksOf(view)).toEqual(['underline', 'sup']);
  });

  it('paints from the palette and knows what is painted', () => {
    const { view, ydoc } = written('Rok');
    const context = contextOf(view, ydoc);
    perform(command('color.red'), context);
    perform(command('highlight.yellow'), context);
    expect(marksOf(view)).toEqual(['color:red', 'highlight:yellow']);
    expect(command('color.red').active!(context)).toBe(true);
    expect(command('color.none').active!(context)).toBe(false);
    perform(command('color.blue'), context);
    perform(command('highlight.none'), context);
    expect(marksOf(view)).toEqual(['color:blue']);
  });

  it('aligns and indents every selected paragraph, in steps and within bounds', () => {
    const { view, ydoc } = written('Prvi', 'Drugi');
    const context = contextOf(view, ydoc);
    perform(command('align.center'), context);
    expect(blockAttrs(view, 'align')).toEqual(['center', 'center']);
    perform(command('align.left'), context);
    expect(blockAttrs(view, 'align')).toEqual([null, null]);

    view.dispatch(view.state.tr.setNodeAttribute(0, 'indent', 0.63));
    expect(available(command('indent.less'), context)).toBe(true);
    perform(command('indent.more'), context);
    expect(blockAttrs(view, 'indent')).toEqual([1.25, 1.25]);
    perform(command('indent.less'), context);
    expect(blockAttrs(view, 'indent')).toEqual([null, null]);
    expect(available(command('indent.less'), context)).toBe(false);

    view.state.doc.forEach((_node, offset) =>
      view.dispatch(view.state.tr.setNodeAttribute(offset, 'indent', INDENT_MAX)),
    );
    expect(available(command('indent.more'), context)).toBe(false);
  });

  it('clears direct formatting and keeps the style', () => {
    const { view, ydoc } = written('Ponuda');
    const context = contextOf(view, ydoc);
    perform(command('style.heading2'), context);
    perform(command('format.bold'), context);
    perform(command('color.red'), context);
    perform(command('align.right'), context);
    const { from, to } = view.state.selection;
    const { font, size, insertion } = schema.marks;
    view.dispatch(
      view.state.tr
        .addMark(from, to, font.create({ family: 'Calibri' }))
        .addMark(from, to, size.create({ pt: 14 }))
        .addMark(from, to, insertion.create({ id: 'p', author: 'Ana Horvat' })),
    );
    perform(command('format.clear'), context);
    const block = view.state.doc.firstChild!;
    expect([block.type.name, block.attrs.level, block.attrs.align]).toEqual(['heading', 2, null]);
    expect(marksOf(view)).toEqual(['insertion']);
    expect(available(command('format.clear'), context)).toBe(false);

    const note = styleCommands(STYLING)[0];
    perform(note, context);
    perform(command('format.italic'), context);
    perform(command('format.clear'), context);
    expect([view.state.doc.firstChild!.type.name, ...blockAttrs(view, 'style')]).toEqual([
      'paragraph',
      'note',
    ]);
  });

  it("applies the document's own style as its kind of block, and the built-in one takes it off", () => {
    const { view, ydoc } = written('Pozor');
    const context = contextOf(view, ydoc);
    const note = styleCommands(STYLING)[0];
    expect([note.id, labelOf(note, ACTIONS.label.current)]).toEqual([
      'style.custom.note',
      'Napomena',
    ]);
    perform(note, context);
    expect(blockAttrs(view, 'style')).toEqual(['note']);
    expect(note.active!(context)).toBe(true);
    expect(command('style.paragraph').active!(context)).toBe(false);
    expect(view.dom.querySelector('p')!.dataset.style).toBe('note');

    perform(command('style.heading2'), context);
    expect(blockAttrs(view, 'style')).toEqual([null]);
    perform(note, context);
    perform(command('style.paragraph'), context);
    expect([view.state.doc.firstChild!.type.name, ...blockAttrs(view, 'style')]).toEqual([
      'paragraph',
      null,
    ]);

    view.dispatch(view.state.tr.setNodeAttribute(0, 'style', 'gone'));
    expect(command('style.paragraph').active!(context)).toBe(true);
  });

  it('shows the font an imported text names, or its metric equal, and its size', () => {
    const view = editor();
    const { font, size } = schema.marks;
    view.dispatch(
      view.state.tr.insert(
        1,
        schema.text('Ponuda', [font.create({ family: 'Calibri' }), size.create({ pt: 14 })]),
      ),
    );
    view.dispatch(
      view.state.tr.insert(7, schema.text(' x', [font.create({ family: 'Wingdings' })])),
    );
    const [carlito, unknown] = view.dom.querySelectorAll<HTMLElement>('span[data-font]');
    expect(carlito.style.fontFamily).toContain('Carlito');
    expect(view.dom.querySelector<HTMLElement>('span[data-font-size]')!.style.fontSize).toBe(
      'calc(14pt * var(--fit, 1))',
    );
    expect(unknown.getAttribute('style')).toBeNull();
  });

  it('copies colours as they print and takes back only its own', () => {
    const { view, ydoc } = written('Rok');
    perform(command('color.red'), contextOf(view, ydoc));
    const copied = view.serializeForClipboard(view.state.selection.content()).dom.innerHTML;
    expect(copied).toMatch(/color: (#c4321c|rgb\(196, 50, 28\))/);
    expect(copied).not.toContain('light-dark');

    const other = editor();
    other.pasteHTML(
      '<p><span style="color: #c4321c">crveno</span> <span style="color: #333">sivo</span></p>',
      paste(),
    );
    const runs = other.state.doc.firstChild!.content.content;
    expect(runs.map((run) => run.marks.map((mark) => mark.attrs.color))).toEqual([['red'], []]);
  });

  it('copies sizes in points, without the fit the Slides view shrinks them by', () => {
    const { view } = written('Rok');
    const { from, to } = view.state.selection;
    view.dispatch(view.state.tr.addMark(from, to, schema.marks.size.create({ pt: 14 })));
    const copied = view.serializeForClipboard(view.state.selection.content()).dom.innerHTML;
    expect(copied).toContain('font-size: 14pt');
    expect(copied).not.toContain('--fit');
  });

  it('reads the title and subtitle Word pastes', () => {
    const view = editor();
    view.pasteHTML(
      '<p class="MsoTitle">Ponuda</p><p class="MsoSubtitle">Najam opreme</p>',
      paste(),
    );
    const types: string[] = [];
    view.state.doc.forEach((node) => types.push(node.type.name));
    expect(types.slice(0, 2)).toEqual([schema.nodes.title.name, schema.nodes.subtitle.name]);
  });
});

describe('the "/" menu', () => {
  it('opens at the start of a line, filters, and inserts what Enter picks', () => {
    const ydoc = new Y.Doc();
    const view = editor(ydoc);
    type(view, '/');
    type(view, 'stranic');
    expect(slashKey.getState(view.state)).toMatchObject({ from: 1, query: 'stranic' });
    press(view, 'Enter');
    expect(slashKey.getState(view.state)).toBeNull();
    expect(view.state.doc.textContent).toBe('');
    expect(view.state.doc.toJSON().content.map((block: { type: string }) => block.type)).toContain(
      'pageBreak',
    );
  });

  it('stays shut inside a word and closes at a space', () => {
    const view = editor();
    type(view, 'a/');
    expect(slashKey.getState(view.state)).toBeNull();
    type(view, ' ');
    type(view, '/');
    expect(slashKey.getState(view.state)).not.toBeNull();
    type(view, ' ');
    expect(slashKey.getState(view.state)).toBeNull();
  });
});

describe('the palette', () => {
  it('finds commands by their label, diacritics or not, where they apply', () => {
    const { view, ydoc } = written('Uvod');
    const label = ACTIONS.label.current;
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1)));
    const inText = choices(COMMANDS, contextOf(view, ydoc), label, 'podeb');
    expect(inText.map((choice) => choice.id)).toEqual(['format.bold']);
    expect(choices(COMMANDS, contextOf(view, ydoc), label, 'obrisi')).toEqual([]);
  });

  it("offers the document's own styles by name, after the built-in ones", () => {
    const { view, ydoc } = written('Uvod');
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1)));
    const found = choices(commandsOf(STYLING), contextOf(view, ydoc), ACTIONS.label.current, '');
    const ids = found.map((choice) => choice.id);
    expect(ids.indexOf('style.custom.note')).toBe(ids.indexOf('style.heading4') + 1);
    expect(found.find((choice) => choice.id === 'style.custom.note')!.label).toBe('Napomena');
  });
});

describe('lists', () => {
  const kinds = (view: EditorView) => blockAttrs(view, 'list');

  it('start from what is typed at the start of a paragraph', () => {
    for (const [typed, kind, checked] of [
      ['-', 'bullet', false],
      ['*', 'bullet', false],
      ['3.', 'number', false],
      ['[]', 'check', false],
      ['[x]', 'check', true],
    ] as const) {
      const view = editor();
      type(view, typed);
      type(view, ' ');
      expect([view.state.doc.textContent, ...kinds(view), ...blockAttrs(view, 'checked')]).toEqual([
        '',
        kind,
        checked,
      ]);
    }
    const view = editor();
    type(view, 'a-');
    type(view, ' ');
    expect(kinds(view)).toEqual([null]);
  });

  it('go on with Enter, step out of an empty item and leave the list from its first level', () => {
    const view = editor();
    type(view, '1.');
    type(view, ' ');
    type(view, 'Prvi');
    press(view, 'Enter');
    press(view, 'Tab');
    expect([kinds(view), blockAttrs(view, 'indent')]).toEqual([
      ['number', 'number'],
      [null, INDENT_STEP],
    ]);
    press(view, 'Enter');
    expect([kinds(view), blockAttrs(view, 'indent')]).toEqual([
      ['number', 'number'],
      [null, null],
    ]);
    press(view, 'Enter');
    expect(kinds(view)).toEqual(['number', null]);
  });

  it('lose the marker and keep the text with Backspace at the start of an item', () => {
    const view = editor();
    type(view, '-');
    type(view, ' ');
    type(view, 'Stavka');
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1)));
    press(view, 'Backspace');
    expect([view.state.doc.textContent, ...kinds(view)]).toEqual(['Stavka', null]);
  });

  it('come on from the toolbar for every selected paragraph and go off once all are items', () => {
    const { view, ydoc } = written('Cijevi', 'Spojnice');
    const context = contextOf(view, ydoc);
    perform(command('list.check'), context);
    expect(kinds(view)).toEqual(['check', 'check']);
    expect(command('list.check').active!(context)).toBe(true);
    perform(command('list.number'), context);
    expect(kinds(view)).toEqual(['number', 'number']);
    perform(command('list.number'), context);
    expect(kinds(view)).toEqual([null, null]);
    perform(command('style.heading1'), context);
    expect(available(command('list.bullet'), context)).toBe(false);
  });

  it('copy as nested lists and marked text, and paste back as the same items', () => {
    const view = editor();
    type(view, '1.');
    type(view, ' ');
    type(view, 'Prvi');
    press(view, 'Enter');
    press(view, 'Tab');
    type(view, 'Drugi');
    press(view, 'Enter');
    press(view, 'Tab', { shiftKey: true });
    type(view, 'Treći');
    const { doc } = view.state;
    const copied = view.serializeForClipboard(doc.slice(0, doc.content.size));
    expect(copied.dom.innerHTML).toBe(
      '<ol data-pm-slice="0 0 []"><li>Prvi<ol type="a"><li>Drugi</li></ol></li><li>Treći</li></ol>',
    );
    expect(copied.text).toBe('1. Prvi\n  a. Drugi\n2. Treći');

    const other = editor();
    other.pasteHTML(copied.dom.innerHTML, paste());
    expect([blockAttrs(other, 'list'), blockAttrs(other, 'indent')]).toEqual([
      ['number', 'number', 'number'],
      [null, INDENT_STEP, null],
    ]);
  });

  it("take a form at the cursor's level throughout their list, the format kept once", () => {
    const own = new Y.Doc();
    const actions = { ...ACTIONS, lists: listStore(own) };
    const view = editor(new Y.Doc(), actions);
    const context = { ...contextOf(view, new Y.Doc()), lists: actions.lists };
    const shown = (target = view) =>
      [...target.dom.querySelectorAll<HTMLElement>('p[data-list]')].map(
        (item) => item.dataset.marker,
      );
    type(view, '1.');
    type(view, ' ');
    type(view, 'Prvi');
    press(view, 'Enter');
    press(view, 'Tab');
    type(view, 'Drugi');
    press(view, 'Enter');
    press(view, 'Tab', { shiftKey: true });
    type(view, 'Treći');
    expect(available(command('numberForm.nested'), context)).toBe(false);
    expect(available(command('bulletForm.dash'), context)).toBe(false);
    perform(command('numberForm.letterParen'), context);
    expect(shown()).toEqual(['a)', 'a.', 'b)']);
    expect(command('numberForm.letterParen').active!(context)).toBe(true);
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 9)));
    perform(command('numberForm.nested'), context);
    expect(shown()).toEqual(['a)', 'a.1.', 'b)']);
    expect(formatsOf(own).size).toBe(2);

    view.dispatch(view.state.tr.setSelection(TextSelection.atEnd(view.state.doc)));
    press(view, 'Enter');
    press(view, 'Enter');
    type(view, 'Napomena');
    press(view, 'Enter');
    type(view, 'Četvrti');
    perform(command('list.number'), context);
    perform(command('numbering.continue'), context);
    expect(shown()).toEqual(['a)', 'a.1.', 'b)', 'c)']);

    const { doc } = view.state;
    const copied = view.serializeForClipboard(doc.slice(0, doc.content.size));
    expect(copied.dom.querySelector('ol')!.getAttribute('type')).toBe('a');
    expect(copied.text).toBe('a) Prvi\n  a.1. Drugi\nb) Treći\n\nNapomena\n\nc) Četvrti');
    const elsewhere = new Y.Doc();
    const other = editor(new Y.Doc(), { ...ACTIONS, lists: listStore(elsewhere) });
    other.pasteHTML(copied.dom.innerHTML, paste());
    expect(shown(other)).toEqual(['a)', 'a.1.', 'b)', 'a)']);
    expect(formatsOf(elsewhere).size).toBe(1);
    view.pasteHTML(copied.dom.innerHTML, paste());
    expect(formatsOf(own).size).toBe(2);
  });

  it('take a whole format, where each item takes the kind of its level', () => {
    const own = new Y.Doc();
    const actions = { ...ACTIONS, lists: listStore(own) };
    const view = editor(new Y.Doc(), actions);
    const open = vi.fn();
    const context = { ...contextOf(view, new Y.Doc()), lists: actions.lists, open };
    const shown = () =>
      [...view.dom.querySelectorAll<HTMLElement>('p[data-list]')].map(
        (item) => item.dataset.marker,
      );
    type(view, 'Uvod');
    expect(available(command('list.format'), context)).toBe(false);
    press(view, 'Enter');
    type(view, '1.');
    type(view, ' ');
    type(view, 'Prvi');
    press(view, 'Enter');
    press(view, 'Tab');
    type(view, 'Drugi');
    perform(command('list.format'), context);
    expect(open).toHaveBeenCalledWith('listFormat');

    const levels = levelsAt(view.state, actions.lists.get())!;
    expect(levels.slice(0, 3)).toEqual([
      standard('number', 0),
      standard('number', 1),
      standard('number', 2),
    ]);
    const article = { numbering: '1', prefix: 'Članak ', suffix: '.', nested: false } as const;
    const dash = { numbering: '', prefix: '–', suffix: '', nested: false } as const;
    const format = [article, dash, ...levels.slice(2)];
    expect(
      formatList(actions.lists, [{ ...article, nested: true }, ...format.slice(1)])(view.state),
    ).toBe(false);
    formatList(actions.lists, format)(view.state, view.dispatch);
    expect([shown(), kinds(view).slice(1)]).toEqual([
      ['Članak 1.', '–'],
      ['number', 'bullet'],
    ]);
    expect(levelsAt(view.state, actions.lists.get())).toEqual(format);
    expect(formatsOf(own).size).toBe(1);
  });

  it('keep their level when formatting is cleared', () => {
    const { view, ydoc } = written('Stavka');
    const context = contextOf(view, ydoc);
    perform(command('list.bullet'), context);
    perform(command('indent.more'), context);
    perform(command('align.center'), context);
    perform(command('format.clear'), context);
    expect([...kinds(view), ...blockAttrs(view, 'indent'), ...blockAttrs(view, 'align')]).toEqual([
      'bullet',
      INDENT_STEP,
      null,
    ]);
  });
});

describe('links', () => {
  const NODE = segment('Ponuda', '6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b');

  function links(view: EditorView): string[] {
    const found: string[] = [];
    view.state.doc.descendants((node) => {
      const link = schema.marks.link.isInSet(node.marks);
      if (link) found.push(`${node.text}→${link.attrs.href}`);
    });
    return found;
  }

  it('come from an address typed in, once a space follows it', () => {
    const view = editor();
    type(view, 'Vidi');
    type(view, ' ');
    type(view, 'www.example.com/cjenik.');
    type(view, ' ');
    type(view, 'i');
    expect(view.state.doc.textContent).toBe('Vidi www.example.com/cjenik. i');
    expect(links(view)).toEqual(['www.example.com/cjenik→https://www.example.com/cjenik']);
  });

  it('are set on the selection, edited where the cursor is, and removed', () => {
    const { view } = written('Ponuda');
    expect(setLink('Ponuda', 'javascript:alert(1)')(view.state, view.dispatch)).toBe(false);
    setLink('Ponuda', `/d/${NODE}`)(view.state, view.dispatch);
    expect(links(view)).toEqual([`Ponuda→/d/${NODE}`]);
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 3)));
    expect(linkAt(view.state)).toEqual({ from: 1, to: 7, href: `/d/${NODE}` });
    setLink('Nova ponuda', 'https://example.com')(view.state, view.dispatch);
    expect(links(view)).toEqual(['Nova ponuda→https://example.com/']);
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 3)));
    removeLink(view.state, view.dispatch);
    expect([view.state.doc.textContent, ...links(view)]).toEqual(['Nova ponuda']);
  });

  it('take Ctrl+K in the text, which elsewhere searches', () => {
    const open = vi.spyOn(ACTIONS, 'open');
    const { view } = written('Ponuda');
    const event = new KeyboardEvent('keydown', {
      key: 'k',
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    view.dom.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(open).toHaveBeenCalledWith('link');
  });

  it('survive clearing formatting', () => {
    const { view, ydoc } = written('Ponuda');
    setLink('Ponuda', 'https://example.com')(view.state, view.dispatch);
    view.dispatch(view.state.tr.setSelection(TextSelection.create(view.state.doc, 1, 7)));
    perform(command('format.bold'), contextOf(view, ydoc));
    perform(command('format.clear'), contextOf(view, ydoc));
    expect(marksOf(view)).toEqual(['link']);
  });
});

describe('images', () => {
  const SHA = 'cd'.repeat(32);
  const DOCUMENT = ACTIONS.place.document;

  function answering(status: number, body: object) {
    return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  }

  function images(view: EditorView): unknown[] {
    const found: unknown[] = [];
    view.state.doc.forEach((node) => {
      if (node.type === schema.nodes.image) found.push(node.attrs.blob);
    });
    return found;
  }

  function sent(fetch: ReturnType<typeof answering>): unknown[] {
    return fetch.mock.calls.map(([path, init]) => [path, init?.body]);
  }

  it('from the web wait for the server to fetch them, and local files are refused aloud', async () => {
    const fetch = answering(201, { blob: SHA, media_type: 'image/png' });
    const fail = vi.spyOn(ACTIONS, 'fail').mockImplementation(() => {});
    const view = editor();
    view.pasteHTML(
      '<p>Shema</p><img src="https://example.com/a.png" alt="Shema"><img src="file:///C:/a.png">',
      paste(),
    );
    expect(images(view)).toEqual([null]);
    expect(fail).toHaveBeenCalledWith(new Error(hr['image.local']));
    await vi.waitFor(() => expect(images(view)).toEqual([SHA]));
    expect(sent(fetch)).toEqual([
      [`/api/nodes/${DOCUMENT}/images`, JSON.stringify({ url: 'https://example.com/a.png' })],
    ]);
  });

  it('from another document are linked to this one, and not again when moved', async () => {
    const fetch = answering(201, { blob: SHA, media_type: 'image/png' });
    const view = editor();
    const figure = `<figure data-image data-blob="${SHA}"><img src="/api/images/${SHA}"></figure>`;
    view.pasteHTML(figure, paste());
    expect(images(view)).toEqual([SHA]);
    view.pasteHTML(figure, paste());
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    expect(sent(fetch)).toEqual([[`/api/nodes/${DOCUMENT}/images`, JSON.stringify({ blob: SHA })]]);
  });

  it('that cannot be fetched leave no placeholder and say why', async () => {
    answering(422, { error: 'unreachable' });
    const fail = vi.spyOn(ACTIONS, 'fail').mockImplementation(() => {});
    const view = editor();
    view.pasteHTML('<img src="https://example.com/a.png">', paste());
    await vi.waitFor(() => expect(fail).toHaveBeenCalled());
    expect(images(view)).toEqual([]);
    expect(fail.mock.calls[0][0]).toBeInstanceOf(ApiError);
    expect((fail.mock.calls[0][0] as ApiError).code).toBe('unreachable');
  });

  it('take the image menu, alignment, description and editing where one is selected', () => {
    const { view, ydoc } = written('Uvod');
    view.dispatch(
      view.state.tr.insert(view.state.doc.content.size, schema.nodes.image.create({ blob: SHA })),
    );
    const at = view.state.doc.firstChild!.nodeSize;
    view.dispatch(view.state.tr.setSelection(NodeSelection.create(view.state.doc, at)));
    const context = contextOf(view, ydoc);
    expect(whereOf(context)).toBe('image');
    expect(available(command('image.alt'), context)).toBe(true);
    expect(available(command('image.edit'), context)).toBe(true);
    expect(available(command('format.bold'), context)).toBe(false);
    expect(available(command('align.justify'), context)).toBe(false);
    perform(command('align.right'), context);
    expect(view.state.doc.nodeAt(at)!.attrs.align).toBe('right');
  });
});
