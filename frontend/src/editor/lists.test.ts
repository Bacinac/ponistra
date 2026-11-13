// @vitest-environment jsdom
import type { Attrs } from 'prosemirror-model';
import { describe, expect, it } from 'vitest';
import { LIST_LEVELS, reformed, standard, type ListFormats, type ListLevel } from './forms';
import { continuable, flattenLists, markers } from './lists';
import { INDENT_STEP, schema } from './schema';

const { doc, paragraph, heading } = schema.nodes;

function item(list: string | null, level = 0, attrs: Attrs = {}) {
  return paragraph.create(
    { list, indent: level ? level * INDENT_STEP : null, ...attrs },
    schema.text('x'),
  );
}

function shown(...blocks: ReturnType<typeof item>[]): (string | undefined)[] {
  return shownIn(new Map(), ...blocks);
}

function shownIn(formats: ListFormats, ...blocks: ReturnType<typeof item>[]) {
  const content = doc.create(null, blocks).content;
  const found = markers(content, formats);
  const all: (string | undefined)[] = [];
  content.forEach((_, offset) => all.push(found.get(offset)));
  return all;
}

function flat(html: string): string {
  const body = new DOMParser().parseFromString(html, 'text/html').body;
  flattenLists(body);
  return body.innerHTML;
}

const form = (numbering: ListLevel['numbering'], prefix: string, suffix = '', nested = false) => ({
  numbering,
  prefix,
  suffix,
  nested,
});

/** The format each pasted item came to carry, by the form of each level it does not show as
 * standard. */
function formatsOf(html: string): (Record<number, string> | null)[] {
  const body = new DOMParser().parseFromString(html, 'text/html').body;
  flattenLists(body);
  return [...body.querySelectorAll<HTMLElement>('p[data-list]')].map((item) => {
    if (!item.dataset.format) return null;
    const levels: ListLevel[] = JSON.parse(item.dataset.format);
    expect(levels).toHaveLength(LIST_LEVELS);
    const own: Record<number, string> = {};
    levels.forEach((level, at) => {
      const plain = standard('number', at);
      if (JSON.stringify(level) !== JSON.stringify(plain)) own[at] = JSON.stringify(level);
    });
    return own;
  });
}

describe('list markers', () => {
  it('number 1., a. and i. by level and bullet •, ◦ and ▪, and so again further in', () => {
    const levels = [0, 1, 2, 3];
    expect(shown(...levels.map((level) => item('number', level)))).toEqual([
      '1.',
      'a.',
      'i.',
      '1.',
    ]);
    expect(shown(...levels.map((level) => item('bullet', level)))).toEqual(['•', '◦', '▪', '•']);
  });

  it("show each level in its list's format, a level of the other kind as standard", () => {
    const letters = reformed(undefined, 0, form('a', '', ')'));
    const outline = reformed(letters, 1, form('1', '', '.', true));
    const formats: ListFormats = new Map([
      ['outline', reformed(outline, 2, form('', '–'))],
      ['article', reformed(undefined, 0, form('1', 'Članak ', '.'))],
    ]);
    const outlined = { format: 'outline' };
    expect(
      shownIn(
        formats,
        item('number', 0, outlined),
        item('number', 0, outlined),
        item('number', 1, outlined),
        item('bullet', 2, outlined),
        item('number', 2, outlined),
        item('bullet', 1, outlined),
        item('number', 0, { format: 'article' }),
        item('number', 0, { format: 'gone' }),
      ),
    ).toEqual(['a)', 'b)', 'b.1.', '–', 'i.', '◦', 'Članak 3.', '4.']);
  });

  it('count on within a run, by level and kind, and start again after any other block', () => {
    expect(
      shown(
        item('number'),
        item('number', 1),
        item('number', 1),
        item('number'),
        item('bullet', 1),
        item('number', 1),
        item('number'),
        item(null),
        item('number'),
        item('number', 0, { restart: true }),
        item('bullet', 2),
        item('check'),
      ),
    ).toEqual(['1.', 'a.', 'b.', '2.', '◦', 'a.', '3.', undefined, '1.', '1.', '▪', undefined]);
    const content = doc.create(null, [item('number'), heading.create(), item('number')]).content;
    expect([...markers(content).values()]).toEqual(['1.', '1.']);
  });

  it('continue a list across other blocks and lists, unless the item starts again', () => {
    const continued = { continued: true };
    expect(
      shown(
        item('number'),
        item('number', 1),
        item(null),
        item('bullet'),
        item('number', 1, continued),
        item('number', 0, continued),
        item(null),
        item('number', 0, { ...continued, restart: true }),
        item('number', 0, continued),
        item('bullet', 0, continued),
      ),
    ).toEqual(['1.', 'a.', undefined, '•', 'b.', '2.', undefined, '1.', '2.', '•']);
  });

  it('tell whether continuing would count an item on', () => {
    const content = doc.create(null, [
      item('number'),
      item(null),
      item('number'),
      item('number'),
      item('number', 0, { continued: true }),
    ]).content;
    const offsets: number[] = [];
    content.forEach((_, offset) => offsets.push(offset));
    expect(offsets.map((offset) => continuable(content, offset))).toEqual([
      false,
      false,
      true,
      false,
      false,
    ]);
  });
});

function word(list: string, marker: string, text: string, font = ''): string {
  const hidden = `<span style="mso-list:Ignore">${marker}<span>&nbsp;&nbsp;</span></span>`;
  return (
    `<p class="MsoListParagraph" style="margin-left:36pt;text-indent:-18pt;mso-list:${list}">` +
    `${font ? `<span style="font-family:${font}">${hidden}</span>` : hidden}${text}</p>`
  );
}

describe('pasted lists', () => {
  it('become items, a nested list one level further in', () => {
    expect(
      flat(
        '<ul><li><p>Cijevi</p><ol><li>Bakar</li><li style="text-align: center">Čelik</li></ol></li><li>Spojnice</li></ul>',
      ),
    ).toBe(
      '<p data-list="bullet">Cijevi</p>' +
        '<p data-list="number" data-indent="1.25">Bakar</p>' +
        '<p data-list="number" data-indent="1.25" style="text-align: center;">Čelik</p>' +
        '<p data-list="bullet">Spojnice</p>',
    );
  });

  it('keep the level a page gives and a tick of every kind', () => {
    expect(
      flat(
        '<ul><li aria-level="2">Dva</li><li role="checkbox" aria-checked="true">Gotovo</li>' +
          '<li><input type="checkbox" checked> Kupljeno</li><li>☐ Otvoreno</li></ul>',
      ),
    ).toBe(
      '<p data-list="bullet" data-indent="1.25">Dva</p>' +
        '<p data-list="check" data-checked="true">Gotovo</p>' +
        '<p data-list="check" data-checked="true"> Kupljeno</p>' +
        '<p data-list="check">Otvoreno</p>',
    );
  });

  it('read Word list paragraphs by their style, without the marker Word writes out', () => {
    expect(
      flat(
        word('l0 level1 lfo1', '•', 'Prva') +
          word('l1 level2 lfo2', 'a.', 'Druga') +
          word('l2 level1 lfo3', '1.', 'Treća'),
      ),
    ).toBe(
      '<p class="MsoListParagraph" style="margin-left:36pt;text-indent:-18pt;mso-list:l0 level1 lfo1" data-list="bullet">Prva</p>' +
        '<p class="MsoListParagraph" style="margin-left:36pt;text-indent:-18pt;mso-list:l1 level2 lfo2" data-list="number" data-indent="1.25">Druga</p>' +
        '<p class="MsoListParagraph" style="margin-left:36pt;text-indent:-18pt;mso-list:l2 level1 lfo3" data-list="number">Treća</p>',
    );
  });

  it("take each Word list's format from the markers Word writes out, in their fonts", () => {
    expect(
      formatsOf(
        word('l0 level1 lfo1', 'a)', 'Prva') +
          word('l0 level2 lfo1', '1.1.', 'Druga') +
          word('l0 level3 lfo1', '§', 'Treća', 'Wingdings') +
          word('l0 level3 lfo1', '§', 'Četvrta', 'Wingdings') +
          word('l1 level1 lfo2', '(iv)', 'Peta') +
          word('l2 level1 lfo3', 'Članak 1.', 'Šesta') +
          word('l3 level1 lfo4', 'o', 'Sedma', 'Courier New'),
      ),
    ).toEqual([
      ...Array.from({ length: 4 }, () => ({
        0: JSON.stringify(form('a', '', ')')),
        1: JSON.stringify(form('1', '', '.', true)),
        2: JSON.stringify(form('', '▪')),
      })),
      { 0: JSON.stringify(form('i', '(', ')')) },
      null,
      { 0: JSON.stringify(form('', '◦')) },
    ]);
  });

  it('take a format from the type or style a page gives its lists', () => {
    expect(
      formatsOf(
        '<ol type="a"><li>Prva<ul style="list-style-type: square"><li>Druga</li></ul></li></ol>' +
          '<p>Tekst</p><ul style=\'list-style-type: "– "\'><li>Treća</li></ul><ol><li>Četvrta</li></ol>',
      ),
    ).toEqual([
      { 0: JSON.stringify(form('a', '', '.')), 1: JSON.stringify(form('', '▪')) },
      { 0: JSON.stringify(form('a', '', '.')), 1: JSON.stringify(form('', '▪')) },
      { 0: JSON.stringify(form('', '–')) },
      null,
    ]);
  });
});
