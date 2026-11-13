// @vitest-environment jsdom
import type { Node } from 'prosemirror-model';
import { EditorState, TextSelection } from 'prosemirror-state';
import { describe, expect, it } from 'vitest';
import * as Y from 'yjs';
import { insertBreak } from './blocks';
import {
  breaksOf,
  clearOfParts,
  geometryOf,
  insetOf,
  laidOut,
  linkPart,
  marginsOf,
  numberingOf,
  ownsPages,
  pageAt,
  pageNumbersOf,
  paperOf,
  partLinked,
  partsOf,
  roomForText,
  saveSection,
  savePages,
  scaleOf,
  sectionAt,
  sectionPart,
  sectionsOf,
  SEPARATOR,
  setupOf,
  stackOf,
  STANDARD,
  writePages,
  type Geometry,
  type Line,
  type Measured,
  type Row,
} from './pages';
import { schema } from './schema';

const page: Geometry = {
  width: 600,
  height: 1000,
  top: 100,
  right: 50,
  bottom: 100,
  left: 50,
  header: 40,
  footer: 40,
  gap: 20,
  firstTop: 100,
  firstBottom: 100,
};
/** From the end of one page's text to the start of the next's. */
const skip = 100 + 20 + 100;

let at = 0;
function block(height: number, more: Partial<Measured> = {}): Measured {
  at += 10;
  return { pos: at, height, before: 0, after: 0, keep: false, forces: false, ...more };
}

function lines(count: number, height = 20): () => Line[] {
  const pos = at + 1000;
  return () =>
    Array.from({ length: count }, (_, index) => ({
      top: index * height,
      bottom: (index + 1) * height,
      pos: pos + index * 7,
    }));
}

function rows(heights: number[], joined: number[] = [], header = 0): () => Row[] {
  return () => {
    let top = 0;
    return heights.map((height, index) => {
      const row = {
        top,
        bottom: top + height,
        joined: joined.includes(index),
        header: index < header,
      };
      top += height;
      return row;
    });
  };
}

describe('pages', () => {
  it('holds blocks that fit on one page', () => {
    expect(laidOut([block(300), block(500)], [page])).toEqual({
      breaks: [],
      pages: 1,
      feet: [],
      sections: [0],
    });
  });

  it('takes a block that does not fit over to the next page, its space before dropped there', () => {
    const second = block(400, { before: 12 });
    const laid = laidOut([block(500, { after: 8 }), second], [page]);
    expect(laid.pages).toBe(2);
    expect(laid.breaks).toEqual([{ kind: 'block', pos: second.pos, gap: 800 - 508 + skip - 12 }]);
  });

  it('collapses the space between two blocks as the browser does', () => {
    const laid = laidOut([block(390, { after: 10 }), block(390, { before: 20 })], [page]);
    expect(laid.pages).toBe(1);
    const over = laidOut([block(390, { after: 10 }), block(391, { before: 20 })], [page]);
    expect(over.pages).toBe(2);
  });

  it('breaks a paragraph between its lines', () => {
    const paragraph = block(200, { lines: lines(10) });
    const laid = laidOut([block(700), paragraph], [page]);
    const line = paragraph.lines!()[5];
    expect(laid.breaks).toEqual([{ kind: 'line', pos: line.pos, gap: 800 - 800 + skip }]);
  });

  it('keeps two lines at the foot of a page, or takes the paragraph over whole', () => {
    const paragraph = block(200, { lines: lines(10) });
    const laid = laidOut([block(770), paragraph], [page]);
    expect(laid.breaks).toEqual([{ kind: 'block', pos: paragraph.pos, gap: 800 - 770 + skip }]);
  });

  it('keeps two lines at the head of the next page', () => {
    const paragraph = block(100, { lines: lines(5) });
    const laid = laidOut([block(720), paragraph], [page]);
    expect(laid.breaks).toEqual([
      { kind: 'line', pos: paragraph.lines!()[3].pos, gap: 800 - 780 + skip },
    ]);
  });

  it('breaks a paragraph longer than a page as often as it takes', () => {
    const paragraph = block(2000, { lines: lines(100) });
    const laid = laidOut([paragraph], [page]);
    expect(laid.pages).toBe(3);
    expect(laid.breaks.map((each) => each.kind)).toEqual(['line', 'line']);
    expect(laid.breaks[1]).toMatchObject({ pos: paragraph.lines!()[80].pos, gap: skip });
  });

  it('takes a heading over with the paragraph that follows it', () => {
    const heading = block(50, { keep: true, before: 6 });
    const laid = laidOut([block(700), heading, block(100)], [page]);
    expect(laid.breaks).toEqual([{ kind: 'block', pos: heading.pos, gap: 800 - 700 + skip - 6 }]);
    expect(laid.pages).toBe(2);
  });

  it('leaves a heading where the paragraph after it starts on the same page', () => {
    const heading = block(40, { keep: true });
    const paragraph = block(200, { lines: lines(10) });
    const laid = laidOut([block(700), heading, paragraph], [page]);
    expect(laid.breaks).toEqual([
      { kind: 'line', pos: paragraph.lines!()[3].pos, gap: 800 - 800 + skip },
    ]);
  });

  it('does not take over a heading that starts its page', () => {
    const laid = laidOut([block(50, { keep: true }), block(900)], [page]);
    expect(laid.breaks).toMatchObject([{ kind: 'block' }]);
    expect(laid.pages).toBe(2);
  });

  it('breaks a table between its rows, never inside a merged cell', () => {
    const table = block(330, { rows: rows([30, 100, 100, 100], [3]) });
    const laid = laidOut([block(500), table], [page]);
    expect(laid.breaks).toEqual([{ kind: 'row', pos: table.pos, row: 2, gap: 800 - 630 + skip }]);
    expect(laid.pages).toBe(2);
  });

  it('stands the header rows of a table again atop the page it runs onto, where they leave room', () => {
    const table = block(850, { rows: rows([50, 100, 100, 100, 100, 100, 100, 100, 100], [], 1) });
    const laid = laidOut([block(500), table], [page]);
    expect(laid.breaks).toEqual([
      { kind: 'row', pos: table.pos, row: 3, gap: 800 - 750 + skip + 50, header: 50 },
    ]);
    expect(laid.pages).toBe(2);
    const tall = block(1200, { rows: rows([600, 300, 300], [], 1) });
    expect(laidOut([block(100), tall], [page]).breaks).toEqual([
      { kind: 'row', pos: tall.pos, row: 1, gap: 800 - 700 + skip },
    ]);
  });

  it('takes a table over whole when not even its first row fits', () => {
    const table = block(300, { rows: rows([100, 100, 100]) });
    const laid = laidOut([block(750), table], [page]);
    expect(laid.breaks).toEqual([{ kind: 'block', pos: table.pos, gap: 800 - 750 + skip }]);
  });

  it('starts a new page after a page break', () => {
    const next = block(20);
    const laid = laidOut([block(20), block(10, { forces: true }), next], [page]);
    expect(laid.breaks).toEqual([{ kind: 'block', pos: next.pos, gap: 800 - 30 + skip }]);
  });

  it('gives the first page the room its own header leaves, and the next pages theirs', () => {
    const blocks = [block(500), block(250), block(700), block(60)];
    expect(laidOut(blocks, [page]).pages).toBe(2);
    const laid = laidOut(blocks, [{ ...page, firstTop: 200, top: 120 }]);
    expect(laid.breaks).toEqual([
      { kind: 'block', pos: blocks[1].pos, gap: 700 - 500 + 100 + 20 + 120 },
      { kind: 'block', pos: blocks[2].pos, gap: 780 - 250 + 100 + 20 + 120 },
    ]);
    expect(laid.pages).toBe(3);
  });

  it('keeps the text clear of a header or footer taller than its margin', () => {
    expect(clearOfParts(page, { header: 30, footer: 80 }, false)).toEqual({
      ...page,
      bottom: 120,
      firstBottom: 120,
    });
    expect(clearOfParts(page, { header: 90, headerFirst: 20 }, true)).toMatchObject({
      top: 130,
      firstTop: 100,
    });
  });

  it('lets a block taller than a page stand at its head and starts the next after it', () => {
    const blocks = [block(10), block(900), block(20)];
    const laid = laidOut(blocks, [page]);
    expect(laid.pages).toBe(3);
    expect(laid.breaks.map((each) => each.kind === 'block' && each.pos)).toEqual([
      blocks[1].pos,
      blocks[2].pos,
    ]);
  });

  it('runs a block taller than pages on over them, the next starting atop the page after it', () => {
    const blocks = [block(10), block(2500), block(20)];
    const laid = laidOut(blocks, [page]);
    expect(laid.breaks).toEqual([
      { kind: 'block', pos: blocks[1].pos, gap: 800 - 10 + skip },
      { kind: 'block', pos: blocks[2].pos, gap: 3 * (800 + skip) - 2500, pages: 3 },
    ]);
    expect(laid.pages).toBe(5);
    expect(pageAt(laid, blocks[2].pos)).toBe(4);
  });

  it('runs a row taller than pages on over them, never with a gap below nought', () => {
    const table = block(2100, { rows: rows([100, 300, 1500, 200], [], 1) });
    const laid = laidOut([block(100), table], [page]);
    expect(laid.breaks).toEqual([
      { kind: 'row', pos: table.pos, row: 2, gap: 800 - 500 + skip },
      {
        kind: 'row',
        pos: table.pos,
        row: 3,
        gap: 2 * (800 + skip) - 1500 + 100,
        header: 100,
        pages: 2,
      },
    ]);
    expect(laid.pages).toBe(4);
    for (const each of laid.breaks) expect(each.gap).toBeGreaterThanOrEqual(0);
  });

  it('sets footnotes at the foot of their marks’ page, which leaves them room', () => {
    const blocks = [
      block(500),
      block(250, { notes: [{ index: 0, y: 100, height: 60 }] }),
      block(200, { notes: [{ index: 1, y: 10, height: 40 }] }),
    ];
    const laid = laidOut(blocks, [page]);
    expect(laid.breaks).toEqual([{ kind: 'block', pos: blocks[1].pos, gap: 800 - 500 + skip }]);
    const foot = 1020 + 1000 - 100 - (60 + 40 + SEPARATOR) + SEPARATOR;
    expect(laid.feet).toEqual([
      { index: 0, page: 1, top: foot },
      { index: 1, page: 1, top: foot + 60 },
    ]);
  });

  it('keeps a line with its footnote, taking it to the next page where both do not fit', () => {
    const mark = { index: 0, y: 24 * 20 + 15 };
    const fits = [block(150), block(600, { lines: lines(30), notes: [{ ...mark, height: 100 }] })];
    const laid = laidOut(fits, [page]);
    expect(laid.breaks).toMatchObject([{ kind: 'line', pos: fits[1].lines!()[26].pos }]);
    expect(laid.feet).toEqual([{ index: 0, page: 0, top: 1000 - 100 - 100 }]);

    const tall = [block(150), block(600, { lines: lines(30), notes: [{ ...mark, height: 200 }] })];
    const over = laidOut(tall, [page]);
    expect(over.breaks).toMatchObject([{ kind: 'line', pos: tall[1].lines!()[24].pos }]);
    expect(over.feet).toMatchObject([{ index: 0, page: 1 }]);
  });

  it('breaks before an endnote in its list', () => {
    const laid = laidOut([block(700), block(150, { endnote: 0 })], [page]);
    expect(laid.breaks).toEqual([{ kind: 'note', index: 0, gap: 800 - 700 + skip }]);
  });
});

describe('scale', () => {
  it('reads an element on a fraction of a pixel as drawn at its size, as a transform alone scales it', () => {
    const element = document.body.appendChild(document.createElement('div'));
    element.style.width = '1046.4px';
    element.getBoundingClientRect = () => ({ width: 1046.4 }) as DOMRect;
    expect(scaleOf(element)).toBe(1);
    element.getBoundingClientRect = () => ({ width: 523.2 }) as DOMRect;
    expect(scaleOf(element)).toBe(0.5);
  });
});

describe('sections', () => {
  const wide: Geometry = { ...page, width: 800, left: 60, right: 40, firstTop: 80 };

  it('starts a section on a page of its own paper, the room above its first block kept', () => {
    const opening = block(100, { section: 1, before: 12 });
    const blocks = [block(100), block(10, { forces: true }), opening, block(900, { section: 1 })];
    const laid = laidOut(blocks, [page, wide]);
    expect(laid.breaks[0]).toEqual({
      kind: 'block',
      pos: opening.pos,
      gap: 800 - 110 + 100 + 20 + 80,
    });
    expect(laid.sections).toEqual([0, 1, 1]);
    expect(laid.breaks[1]).toMatchObject({
      pos: blocks[3].pos,
      gap: 1000 - 80 - 100 - 112 + 100 + 20 + 100,
    });
  });

  it('stands each page centred on the widest and sets a section’s text in by its own margins', () => {
    const laid = laidOut(
      [block(100), block(10, { forces: true }), block(100, { section: 1 })],
      [page, wide],
    );
    const stack = stackOf([page, wide], laid);
    expect(stack.width).toBe(800);
    expect(stack.pages.map(({ top, left, section }) => [top, left, section])).toEqual([
      [0, 100, 0],
      [1020, 0, 1],
    ]);
    expect(stack.height).toBe(2020);
    expect(insetOf([page, wide], 0)).toEqual([0, 0]);
    expect(insetOf([page, wide], 1)).toEqual([60 - 150, 40 - 150]);
  });

  it('numbers on through a section, again from one that starts its own', () => {
    const setups = [STANDARD, { ...STANDARD, start: null }, { ...STANDARD, start: 1 }];
    expect(pageNumbersOf(5, setups, [0, 0, 1, 1, 2, 2])).toEqual([5, 6, 7, 8, 1, 2]);
  });

  it('takes what a section does not set from the one before, its own headers kept apart', () => {
    const own = new Y.Doc();
    own.getMap('page').set('start', 3);
    own.getXmlFragment('header').insert(0, [new Y.XmlElement('paragraph')]);
    const doc = schema.node('doc', null, [
      schema.node('paragraph'),
      schema.node('sectionBreak', { id: 's1' }),
      schema.node('paragraph'),
      schema.node('sectionBreak', { id: 's2' }),
      schema.node('paragraph'),
    ]);
    const breaks = breaksOf(doc);
    expect(breaks).toEqual(['s1', 's2']);
    expect(sectionAt(doc, 1)).toBe(0);
    expect(sectionAt(doc, doc.content.size - 1)).toBe(2);
    saveSection(own, 'a', 's1', { ...STANDARD, width: 29.7, height: 21 });
    linkPart(own, 'a', breaks, 2, 'header', false);
    const sections = sectionsOf(own, 'a', breaks);
    expect(sections.map(({ setup }) => [setup.width, setup.start])).toEqual([
      [21, 3],
      [29.7, null],
      [29.7, null],
    ]);
    expect(sections[1].parts.header).toBe(own.getXmlFragment('header'));
    expect(sections[2].parts.header).not.toBe(own.getXmlFragment('header'));
    expect(sections[2].parts.header!.length).toBe(1);
    expect(partLinked(own, 'a', 's1', 'header')).toBe(true);
    expect(sectionPart(own, 'a', breaks, 1, 'header')).toBe(own.getXmlFragment('header'));
    linkPart(own, 'a', breaks, 2, 'header', true);
    expect(sectionsOf(own, 'a', breaks)[2].parts.header).toBe(own.getXmlFragment('header'));
    saveSection(own, 'a', 's1', null);
    expect(sectionsOf(own, 'a', breaks)[1].setup.width).toBe(21);
  });
});

describe('page setup', () => {
  it('is the document’s, or the tab’s own where it has one, in centimetres', () => {
    const own = new Y.Doc();
    expect(setupOf(own, 'a')).toEqual(STANDARD);
    own.getMap('page').set('top', 3);
    const mine = new Y.Map<unknown>();
    own.getMap<Y.Map<unknown>>('tabs').set('b', mine);
    mine.set('page', new Y.Map(Object.entries({ width: 29.7, height: 21, start: 5 })));
    expect(setupOf(own, 'a')).toEqual({ ...STANDARD, top: 3 });
    expect(setupOf(own, 'b')).toEqual({ ...STANDARD, width: 29.7, height: 21, start: 5 });
    expect(geometryOf(STANDARD).width).toBeCloseTo(793.7, 1);
  });

  it('numbers pages on through the tabs, again where a tab starts its own', () => {
    const own = new Y.Doc();
    writePages(own, 'a', 3);
    writePages(own, 'b', 4);
    writePages(own, 'c', 2);
    const mine = new Y.Map<unknown>();
    own.getMap<Y.Map<unknown>>('tabs').set('c', mine);
    mine.set('page', new Y.Map(Object.entries({ start: 1 })));
    const tabs = ['a', 'b', 'c'];
    expect(numberingOf(own, tabs, 'b', 5)).toEqual({ first: 4, total: 10 });
    expect(numberingOf(own, tabs, 'c', 2)).toEqual({ first: 1, total: 9 });
  });

  it('counts a tab not counted yet as the one page of a new empty tab', () => {
    const own = new Y.Doc();
    writePages(own, 'a', 3);
    expect(numberingOf(own, ['a', 'b', 'c'], 'c', 2)).toEqual({ first: 5, total: 6 });
  });
});

describe('page setup dialog', () => {
  it('numbers from the document’s start on its first tab only', () => {
    const own = new Y.Doc();
    own.getMap('page').set('start', 5);
    writePages(own, 'a', 2);
    expect(numberingOf(own, ['a', 'b'], 'a', 2)).toEqual({ first: 5, total: 3 });
    expect(numberingOf(own, ['a', 'b'], 'b', 3)).toEqual({ first: 7, total: 5 });
  });

  it('gives a tab pages of its own with the document’s headers, and takes them back', () => {
    const own = new Y.Doc();
    own.getXmlFragment('header').insert(0, [new Y.XmlElement('paragraph')]);
    savePages(own, 'b', { ...STANDARD, width: 29.7, height: 21, start: 1 }, true);
    expect(ownsPages(own, 'b')).toBe(true);
    expect(setupOf(own, 'b')).toEqual({ ...STANDARD, width: 29.7, height: 21, start: 1 });
    expect(setupOf(own, 'a')).toEqual(STANDARD);
    expect(partsOf(own, 'b').header?.toString()).toBe('<paragraph></paragraph>');
    expect(partsOf(own, 'b').header).not.toBe(own.getXmlFragment('header'));

    savePages(own, 'b', { ...STANDARD, top: 3 }, false);
    expect(ownsPages(own, 'b')).toBe(false);
    expect(setupOf(own, 'a')).toEqual({ ...STANDARD, top: 3 });
    expect(partsOf(own, 'b').header).toBe(own.getXmlFragment('header'));
  });

  it('names paper and margins either way the page lies, and wants room for text', () => {
    expect(paperOf({ width: 29.7, height: 21 })).toBe('a4');
    expect(paperOf({ width: 21.59, height: 27.94 })).toBe('letter');
    expect(paperOf({ width: 20, height: 20 })).toBeNull();
    expect(marginsOf({ top: 2.54, right: 5.08, bottom: 2.54, left: 5.08 })).toBe('wide');
    expect(marginsOf({ top: 2.5, right: 2.5, bottom: 2, left: 2.5 })).toBeNull();
    expect(roomForText(STANDARD)).toBe(true);
    expect(roomForText({ ...STANDARD, left: 10, right: 9.5 })).toBe(false);
  });
});

describe('page break', () => {
  const text = schema.node('doc', null, [
    schema.node('heading', { level: 1 }, schema.text('Ugovor')),
    schema.node('paragraph', null, schema.text('Prvi članak')),
  ]);

  function broken(at: number): { blocks: string[]; cursor: number; doc: Node } {
    const start = EditorState.create({ doc: text });
    let state = start.apply(start.tr.setSelection(TextSelection.create(text, at)));
    insertBreak(schema.nodes.pageBreak)(state, (tr) => (state = state.apply(tr)));
    const blocks: string[] = [];
    state.doc.forEach((node) => blocks.push(node.isTextblock ? node.textContent : node.type.name));
    return { blocks, cursor: state.selection.from, doc: state.doc };
  }

  it('takes the text after the cursor over to the next page', () => {
    const { blocks, cursor, doc } = broken(4);
    expect(blocks).toEqual(['Ugo', 'pageBreak', 'vor', 'Prvi članak']);
    expect(doc.resolve(cursor).parent.textContent).toBe('vor');
    expect(doc.child(2).type.name).toBe('heading');
  });

  it('starts the next block’s page at the end of a block, with no empty one between', () => {
    const { blocks, cursor, doc } = broken(7);
    expect(blocks).toEqual(['Ugovor', 'pageBreak', 'Prvi članak']);
    expect(doc.resolve(cursor).parentOffset).toBe(0);
    expect(doc.resolve(cursor).parent.textContent).toBe('Prvi članak');
  });

  it('starts a page with the block the cursor begins', () => {
    expect(broken(1).blocks).toEqual(['pageBreak', 'Ugovor', 'Prvi članak']);
  });

  it('opens an empty paragraph after a break at the end of the text', () => {
    const { blocks, cursor, doc } = broken(text.content.size - 1);
    expect(blocks).toEqual(['Ugovor', 'Prvi članak', 'pageBreak', '']);
    expect(doc.resolve(cursor).parent.type.name).toBe('paragraph');
  });
});
