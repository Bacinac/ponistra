// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { compact } from './address';
import type { Account } from './mailData';
import {
  allotted,
  asksVault,
  eventHref,
  mailHref,
  markWords,
  EVERYWHERE,
  marked,
  personHref,
  plainWords,
  placeOf,
  replaced,
  resultHref,
  searchQuery,
  taskHref,
  versionHref,
  withFilter,
  type EventResult,
  type PersonResult,
  type SearchFilter,
  type SearchResult,
  type VersionResult,
} from './search';

const NODE = '6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b';
const TAB = '0b7e5c1d-2a3f-4e60-9d8c-7b6a5f4e3d2c';

function result(fields: Partial<SearchResult>): SearchResult {
  return {
    id: NODE,
    parent: null,
    kind: 'document',
    title: 'Ponuda',
    locale: 'hr',
    updated_at: '2026-10-16T10:00:00Z',
    updated_by: null,
    size: null,
    media_type: null,
    picture: null,
    holds: null,
    origin: null,
    extension: null,
    href: null,
    description: '',
    trashed_at: null,
    original: null,
    macros: null,
    imported: null,
    company: false,
    confined: false,
    notes: false,
    links: false,
    boards: false,
    columns: null,
    agent_folder: null,
    path: [],
    root: 'mine',
    source: 'title',
    tab: null,
    page: null,
    block: null,
    address: null,
    thread: null,
    hits: 1,
    snippet: 'Ponuda',
    ...fields,
  };
}

const [MARK, END] = ['\ue000', '\ue001'];

describe('searchQuery', () => {
  it('sends the folder it looks in, and a kind alone among the filters', () => {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    expect(searchQuery('ponuda', EVERYWHERE, 8)).toBe(`q=ponuda&limit=8&zone=${zone}`);
    const query = new URLSearchParams(searchQuery('ponuda', { kind: 'file', in: 'f1' }, 50));
    expect(Object.fromEntries(query)).toEqual({
      q: 'ponuda kind:file',
      limit: '50',
      zone,
      in: 'f1',
    });
  });
});

describe('allotted', () => {
  it('shares the places equally and gives what a short group leaves to the longer ones', () => {
    expect(allotted([10, 1, 3], 8)).toEqual([4, 1, 3]);
    expect(allotted([5, 5], 8)).toEqual([4, 4]);
    expect(allotted([0, 20, 0, 0, 0], 8)).toEqual([0, 8, 0, 0, 0]);
    expect(allotted([3, 3, 3, 3, 3], 8)).toEqual([2, 2, 2, 1, 1]);
    expect(allotted([0, 0], 8)).toEqual([0, 0]);
  });
});

describe('hrefs of events, tasks and people', () => {
  const event: EventResult = {
    id: 7,
    master: null,
    calendar: { id: 1, name: 'Moj', color: 2, account: null },
    summary: 'Zamjena guma',
    marked: 'Zamjena guma',
    snippet: '',
    location: '',
    all_day: true,
    start: '2026-11-03',
    end: '2026-11-03',
    recurring: false,
    hits: 1,
  };
  const person: PersonResult = {
    kind: 'colleague',
    id: 3,
    name: 'Ana Kovač',
    organisation: '',
    title: '',
    email: 'ana@firma.test',
    phone: '',
  };
  it('opens the day of an event, the task and the contact or the address book searched', () => {
    expect(eventHref(event)).toBe('/calendar/day/2026-11-03?event=7');
    expect(eventHref({ ...event, all_day: false, start: '2026-11-03T23:30:00+01:00' })).toMatch(
      /^\/calendar\/day\/2026-11-0[34]\?event=7$/,
    );
    expect(taskHref({ id: 4, text: 'x', marked: 'x', due: null, done: false })).toBe(
      '/tasks?task=4',
    );
    expect(personHref(person)).toBe('/contacts?q=ana%40firma.test');
    expect(personHref({ ...person, kind: 'contact' })).toBe('/contacts/3');
  });
});

function filter(fields: Partial<SearchFilter>): SearchFilter {
  return { key: 'from', token: 'od:ana', raw: 'ana', start: 7, end: 13, ...fields };
}

describe('replaced', () => {
  it('puts a token in place of the filter, or takes it out', () => {
    const typed = filter({});
    expect(replaced('ponuda od:ana rijeka', typed, 'od:marko')).toBe('ponuda od:marko rijeka');
    expect(replaced('ponuda od:ana rijeka', typed, '')).toBe('ponuda rijeka');
  });

  it('finds the token where the box has moved it, and leaves a box without it alone', () => {
    expect(replaced('nova ponuda od:ana', filter({}), '')).toBe('nova ponuda');
    expect(replaced('ponuda', filter({}), '')).toBe('ponuda');
  });
});

describe('withFilter', () => {
  it('replaces the filter of the same keys, or adds the token after the words', () => {
    const date = filter({ key: 'date', token: 'datum:2025', raw: '2025', start: 7, end: 17 });
    const keys: SearchFilter['key'][] = ['date', 'changed'];
    expect(withFilter('ponuda datum:2025', [date], keys, 'datum:tjedan')).toBe(
      'ponuda datum:tjedan',
    );
    expect(withFilter('ponuda ', [], ['kind'], 'vrsta:pošta')).toBe('ponuda vrsta:pošta');
  });
});

describe('the vault among the results', () => {
  const kind: SearchFilter = {
    key: 'kind',
    token: 'vrsta:sef',
    raw: 'sef',
    value: 'vault',
    start: 6,
    end: 15,
  };
  it('is left in by no filter or its kind alone', () => {
    expect(asksVault([])).toBe(true);
    expect(asksVault([kind])).toBe(true);
    expect(asksVault([kind, filter({})])).toBe(false);
    expect(asksVault([{ ...kind, value: 'mail' }])).toBe(false);
  });
  it('takes the words typed besides the filters and the operators, folded', () => {
    expect(plainWords('banka vrsta:sef -x OR Žiro', [kind])).toEqual(['banka', 'ziro']);
    expect(plainWords('"Ana Kovač"', [])).toEqual(['ana', 'kovac']);
  });
  it('marks each word one of the words starts', () => {
    expect(markWords('Banka Žiro', ['zir'])).toBe(`Banka ${MARK}Žiro${END}`);
    expect(markWords('Banka', ['x'])).toBe('Banka');
  });
});

describe('marked', () => {
  it('splits a snippet into plain and marked parts', () => {
    expect(marked(`Godišnja ${MARK}kalibracija${END} osi`)).toEqual([
      { text: 'Godišnja ', mark: false },
      { text: 'kalibracija', mark: true },
      { text: ' osi', mark: false },
    ]);
  });

  it('keeps a snippet without marks whole', () => {
    expect(marked('Ponuda')).toEqual([{ text: 'Ponuda', mark: false }]);
  });

  it('marks several hits and drops empty parts', () => {
    expect(marked(`${MARK}Ugovor${END} ${MARK}ugovora${END}`)).toEqual([
      { text: 'Ugovor', mark: true },
      { text: ' ', mark: false },
      { text: 'ugovora', mark: true },
    ]);
  });
});

describe('resultHref', () => {
  const [node, tab] = [compact(NODE), compact(TAB)];

  it('opens a title hit at the node', () => {
    expect(resultHref(result({}))).toBe(`/d/ponuda-${node}`);
  });

  it('opens a link at its page, whatever of it was found', () => {
    const page = 'https://www.example.com/katalog';
    expect(resultHref(result({ kind: 'link', href: page }))).toBe(page);
    expect(resultHref(result({ kind: 'link', href: page, source: 'link' }))).toBe(page);
  });

  it('opens a tab hit at its tab', () => {
    expect(resultHref(result({ source: 'tab', tab: { id: TAB, title: 'Cjenik' } }))).toBe(
      `/d/ponuda-${node}/cjenik-${tab}`,
    );
  });

  it('opens a page hit at its page, finding the word it marked there', () => {
    expect(resultHref(result({ kind: 'file', source: 'page', page: 3 }))).toBe(
      `/p/ponuda-${node}?page=3`,
    );
    const snippet = `cijena ${MARK}najma${END} i ${MARK}najam${END} prostora`;
    expect(resultHref(result({ kind: 'file', source: 'page', page: 3, snippet }))).toBe(
      `/p/ponuda-${node}?page=3&find=najma`,
    );
  });

  it('opens a block hit at its block in its tab', () => {
    const hit = result({
      source: 'block',
      tab: { id: TAB, title: '' },
      block: 'a+b/c',
    });
    expect(resultHref(hit)).toBe(`/d/ponuda-${node}/${tab}?block=a%2Bb%2Fc`);
  });

  it("opens a cell hit at its cell, in a table after the tab's first by the table's name", () => {
    const hit = (address: object) =>
      resultHref(
        result({ source: 'block', tab: { id: TAB, title: '' }, block: 'tablica', address }),
      );
    expect(hit({ table: 1, cell: 'C3', name: 'Ulaz' })).toBe(`/d/ponuda-${node}/${tab}?cell=C3`);
    expect(hit({ table: 2, cell: 'C3', name: '2044' })).toBe(
      `/d/ponuda-${node}/${tab}?cell='2044'!C3`,
    );
    expect(hit({ table: 2, cell: 'C3' })).toBe(`/d/ponuda-${node}/${tab}?block=tablica&cell=C3`);
  });

  it('opens a comment hit at its thread in the comments of its tab', () => {
    const thread = '7d1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b';
    const hit = result({
      source: 'comment',
      tab: { id: TAB, title: '' },
      thread,
    });
    expect(resultHref(hit)).toBe(`/d/ponuda-${node}/${tab}?panel=comments&comment=${thread}`);
  });

  it('opens a comment hit on a file at its thread beside the file', () => {
    const thread = '7d1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b';
    const hit = result({ kind: 'file', source: 'comment', thread });
    expect(resultHref(hit)).toBe(`/p/ponuda-${node}?panel=comments&comment=${thread}`);
  });
});

describe('placeOf', () => {
  const t = (key: string) => key.replace('search.', '');
  const formatNumber = (value: number) => `#${value}`;

  it('points to a block by its tab, section and place within it', () => {
    const block = (address: object, title = '') =>
      placeOf(result({ source: 'block', tab: { id: TAB, title }, address }), t, formatNumber);
    expect(block({ section: '1.0.1', paragraph: 4 }, 'Cjenik')).toBe(
      'Cjenik · section 1.0.1 · paragraph #4',
    );
    expect(block({ paragraph: 2 })).toBe('paragraph #2');
    expect(block({ section: '2', table: 1, cell: 'C7' })).toBe('section 2 · table #1 · cell C7');
    expect(block({ section: '1', image: 2 })).toBe('section 1 · image #2');
  });

  it('points by the numbers the document shows, a number with words of its own by itself', () => {
    const block = (address: object) =>
      placeOf(result({ source: 'block', tab: { id: TAB, title: '' }, address }), t, formatNumber);
    expect(block({ section: '1.1', heading: '2.1.', paragraph: 3, number: '4.' })).toBe(
      'section 2.1. · paragraph 4.',
    );
    expect(
      block({
        section: '1',
        heading: 'Poglavlje I.',
        paragraph: 1,
        number: 'Članak 3.',
      }),
    ).toBe('Poglavlje I. · Članak 3.');
  });

  it('names a tab or a page hit by what it is', () => {
    expect(placeOf(result({ source: 'tab' }), t, formatNumber)).toBe('tab');
    expect(placeOf(result({ source: 'page', page: 3 }), t, formatNumber)).toBe('page #3');
    const comment = result({
      source: 'comment',
      tab: { id: TAB, title: 'Cjenik' },
    });
    expect(placeOf(comment, t, formatNumber)).toBe('Cjenik · comment');
  });
});

describe('a version among the results', () => {
  const VERSION = '1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d';
  const version: VersionResult = {
    id: VERSION,
    number: 2,
    title: 'Prije popusta',
    created_at: '2026-10-20T10:00:00Z',
    restored_from: null,
    editors: [],
    document: result({}),
    tab: null,
    hits: 1,
    snippet: 'Prije popusta',
  };

  it('opens the version of its document, at the tab that matched where one did', () => {
    expect(versionHref(version)).toBe(`/d/ponuda-${compact(NODE)}/versions/${compact(VERSION)}`);
    expect(versionHref({ ...version, tab: { id: TAB, title: 'Cjenik' } })).toBe(
      `/d/ponuda-${compact(NODE)}/versions/${compact(VERSION)}/${compact(TAB)}`,
    );
  });
});

describe('a message among the results', () => {
  const account = { id: 4, together: false } as Account;

  it('opens in the mailbox it is in, with the account it came to where it keeps apart', () => {
    const message = { id: 9, folder: 3, account: 4, box: null };
    expect(mailHref(message, [account])).toBe('/mail/3/9?account=4');
    expect(mailHref({ ...message, account: null, box: { id: 7, name: 'Prodaja' } }, [])).toBe(
      '/mail/3/9?box=7',
    );
    expect(mailHref({ ...message, box: { id: 7, name: 'Prodaja' } }, [account])).toBe(
      '/mail/3/9?account=4&box=7',
    );
  });
});
