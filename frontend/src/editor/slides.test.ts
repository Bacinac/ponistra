import type { Node } from 'prosemirror-model';
import { EditorState, TextSelection, type Command } from 'prosemirror-state';
import { describe, expect, it } from 'vitest';
import * as Y from 'yjs';
import { schema } from './schema';
import {
  boxOf,
  layoutOf,
  setSlideSize,
  SIZES,
  slidesOf,
  speakerKeys,
  speakerNotes,
  templateOf,
  type Layout,
} from './slides';

const { nodes } = schema;
const text = (value: string) => (value ? schema.text(value) : undefined);
const p = (value = '', attrs = {}) => nodes.paragraph.create(attrs, text(value));
const h = (value: string, level = 1, attrs = {}) =>
  nodes.heading.create({ level, ...attrs }, text(value));
const doc = (...blocks: Node[]) => nodes.doc.create(null, blocks);
const notes = (value: string) => p(value, { speaker: true });

function shown(blocks: Node) {
  return slidesOf(blocks).map((slide) => ({
    kind: slide.kind,
    placed: slide.placed.map(({ node, role }) => `${role}:${node.textContent || node.type.name}`),
    notes: slide.notes.map(({ node }) => node.textContent),
  }));
}

describe('slides of a tab', () => {
  it('starts one at each title, heading 1 and slide break, not at a lower heading', () => {
    const slides = shown(
      doc(
        nodes.title.create(null, text('Ponuda')),
        nodes.subtitle.create(null, text('Listopad')),
        h('Cijene'),
        p('Najam'),
        h('Uvjeti', 2),
        p('Plaćanje'),
        nodes.slideBreak.create(),
        p('Kontakt'),
        h('Hvala'),
      ),
    );
    expect(slides).toEqual([
      { kind: 'title', placed: ['title:Ponuda', 'subtitle:Listopad'], notes: [] },
      {
        kind: 'content',
        placed: ['title:Cijene', 'body:Najam', 'body:Uvjeti', 'body:Plaćanje'],
        notes: [],
      },
      { kind: 'blank', placed: ['body:slideBreak', 'body:Kontakt'], notes: [] },
      { kind: 'section', placed: ['title:Hvala'], notes: [] },
    ]);
  });

  it('makes a slide of what comes before the first start only when it holds anything', () => {
    expect(shown(doc(p(), h('Cijene'), p('Najam'))).map(({ kind }) => kind)).toEqual(['content']);
    expect(shown(doc(p('Uvod'), h('Cijene'))).map(({ kind }) => kind)).toEqual([
      'blank',
      'section',
    ]);
    expect(shown(doc(p()))).toEqual([{ kind: 'blank', placed: ['body:paragraph'], notes: [] }]);
  });

  it('takes speaker notes off the slide and sends the text after a column break to the second body', () => {
    const [slide] = shown(
      doc(h('Usporedba'), p('Lijevo'), notes('Reći'), nodes.columnBreak.create(), p('Desno')),
    );
    expect(slide).toEqual({
      kind: 'two',
      placed: ['title:Usporedba', 'body:Lijevo', 'second:columnBreak', 'second:Desno'],
      notes: ['Reći'],
    });
  });

  it('keeps a slide’s layout, its own background and whether it is hidden on the block that starts it', () => {
    const background = { color: '#2f6b6e' };
    const [slide, next] = slidesOf(
      doc(h('Cijene', 1, { layout: 'two', hidden: true, background }), p('Najam'), h('Kraj', 1)),
    );
    expect(slide).toMatchObject({ layout: 'two', background, hidden: true, kind: 'content' });
    expect(next.background).toBeNull();
  });
});

describe('the slide template', () => {
  it('is the built-in one at 16:9 while the document has no layouts of its own', () => {
    const own = new Y.Doc();
    const template = templateOf(own);
    expect(template.builtIn).toBe(true);
    expect(template.size).toEqual(SIZES.wide);
    expect(template.layouts.map(({ kind }) => kind)).toEqual([
      'title',
      'content',
      'two',
      'section',
      'titleOnly',
      'blank',
    ]);
    setSlideSize(own, SIZES.standard);
    const standard = templateOf(own);
    expect(standard.size).toEqual(SIZES.standard);
    const across = SIZES.standard.width / SIZES.wide.width;
    const [wideTitle] = template.layouts;
    const [title] = standard.layouts;
    expect(title.boxes.title!.x).toBeCloseTo(wideTitle.boxes.title!.x * across);
    expect(title.boxes.title!.y).toBeCloseTo(wideTitle.boxes.title!.y);
    expect(standard.layouts[1].shapes[0].w).toBeCloseTo(template.layouts[1].shapes[0].w * across);
  });

  it('takes the document’s own layouts, the first of a kind where a slide names none', () => {
    const own = new Y.Doc();
    const mine: Layout[] = [
      { id: 'a', kind: 'content', shapes: [], boxes: { body: { x: 1, y: 1, w: 10, h: 5 } } },
      { id: 'b', kind: 'content', shapes: [], boxes: {} },
    ];
    own.getMap('slides').set('layouts', [...mine, { id: 'broken' }]);
    const template = templateOf(own);
    expect(template.builtIn).toBe(false);
    expect(template.layouts.map(({ id }) => id)).toEqual(['a', 'b']);
    expect(layoutOf({ kind: 'content', layout: null }, template).id).toBe('a');
    expect(layoutOf({ kind: 'content', layout: 'b' }, template).id).toBe('b');
    expect(layoutOf({ kind: 'two', layout: 'gone' }, template).id).toBe('two');
  });

  it('puts text a layout has no box for where the built-in layout of its kind does', () => {
    const own = new Y.Doc();
    const { size, layouts } = templateOf(own);
    const [title, content, , section, titleOnly, blank] = layouts;
    expect(boxOf(content, 'body', size).key).toBe('body');
    expect(boxOf(title, 'body', size).key).toBe('subtitle');
    expect(boxOf(content, 'subtitle', size).key).toBe('body');
    expect(boxOf(section, 'body', size).key).toBe('body');
    expect(boxOf(titleOnly, 'body', size).key).toBe('content.body');
    expect(boxOf(blank, 'title', size).key).toBe('content.title');
    expect(boxOf(content, 'second', size).key).toBe('two.second');
    const bare: Layout = { id: 'x', kind: 'two', shapes: [], boxes: {} };
    const standard = boxOf(bare, 'second', SIZES.standard).box;
    expect(standard.x).toBeCloseTo((17.145 * 25.4) / 33.867);
    expect(standard.y).toBeCloseTo(5.071);
  });
});

describe('speaker notes', () => {
  function run(command: Command, blocks: Node, at: number): EditorState {
    let state = EditorState.create({ doc: blocks });
    state = state.apply(state.tr.setSelection(TextSelection.create(state.doc, at)));
    command(state, (tr) => (state = state.apply(tr)));
    return state;
  }
  const texts = (state: EditorState) => {
    const all: string[] = [];
    state.doc.forEach((node) =>
      all.push(`${node.attrs.speaker ? 'notes:' : ''}${node.textContent || node.type.name}`),
    );
    return all;
  };

  it('open at the end of the cursor’s slide, or lead to those it has', () => {
    const blocks = doc(h('Cijene'), p('Najam'), h('Uvjeti'));
    const opened = run(speakerNotes, blocks, 3);
    expect(texts(opened)).toEqual(['Cijene', 'Najam', 'notes:paragraph', 'Uvjeti']);
    expect(opened.selection.$from.parent.attrs.speaker).toBe(true);
    const kept = doc(h('Cijene'), notes('Reći'), p('Najam'), h('Uvjeti'));
    const led = run(speakerNotes, kept, 2);
    expect(led.selection.from).toBe(kept.child(0).nodeSize + 1 + 'Reći'.length);
  });

  it('go on with Enter and end with Enter on an empty paragraph', () => {
    const blocks = doc(h('Cijene'), notes('Reći'));
    const end = blocks.content.size - 1;
    const next = run(speakerKeys.Enter, blocks, end);
    expect(texts(next)).toEqual(['Cijene', 'notes:Reći', 'notes:paragraph']);
    const out = run(speakerKeys.Enter, next.doc, next.selection.from);
    expect(texts(out)).toEqual(['Cijene', 'notes:Reći', 'paragraph']);
  });

  it('leave their first paragraph on the slide with Backspace at its start', () => {
    const blocks = doc(h('Cijene'), notes('Reći'), notes('Pitati'));
    const start = blocks.child(0).nodeSize + 1;
    expect(texts(run(speakerKeys.Backspace, blocks, start))).toEqual([
      'Cijene',
      'Reći',
      'notes:Pitati',
    ]);
    const second = start + blocks.child(1).nodeSize;
    expect(
      speakerKeys.Backspace(
        EditorState.create({ doc: blocks, selection: TextSelection.create(blocks, second) }),
      ),
    ).toBe(false);
  });
});
