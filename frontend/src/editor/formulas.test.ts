import { describe, expect, it } from 'vitest';
import {
  addressOf,
  CANONICAL,
  formulaText,
  placeText,
  pointedAt,
  readFormula,
  rectOfAddress,
  syntaxOf,
  tableNameText,
  takesReference,
  type Book,
} from './formulas';

const size = { rows: 4, cols: 2 };
const tables = new Map([
  ['CIJENE 2026', { rows: 2, cols: 2 }],
  ['SKLADIŠTE', size],
]);
const book: Book = {
  named: (name) => tables.get(name.toUpperCase()) ?? null,
  name: (name) => (name.toUpperCase() === 'STOPA' ? 'Stopa' : null),
};
const hr = syntaxOf('hr');

describe('syntaxOf', () => {
  it('separates arguments with semicolons where decimals take a comma', () => {
    for (const locale of ['hr', 'de', 'fr', 'it', 'es'] as const) {
      expect(syntaxOf(locale)).toEqual({ decimal: ',', list: ';', row: '/' });
    }
    expect(syntaxOf('en')).toBe(CANONICAL);
    expect(syntaxOf('en-GB')).toBe(CANONICAL);
  });
});

describe('readFormula', () => {
  // Each pair is the same formula in Croatian and in the canonical form.
  it.each([
    ['=SUM(1,5;{1;2/3;4};TRUE)&"a,b"', '=SUM(1.5,{1,2;3,4},TRUE)&"a,b"'],
    ['=round(2,5;0)+(0,1+0,2=0,3)', '=ROUND(2.5,0)+(0.1+0.2=0.3)'],
    ['={1;2\\3;4}', '={1,2;3,4}'],
    ['=LEN("a,b;c")&\'x;y\'', '=LEN("a,b;c")&\'x;y\''],
    ['=#ref!+1,5E3+50%', '=#REF!+1.5E3+50%'],
    ['=STDEV.S(1;2)', '=STDEV.S(1,2)'],
  ])('reads %s in Croatian as %s', (text, canonical) => {
    expect(readFormula(text, size, hr, book)).toBe(canonical);
  });

  it('reads the canonical form in English unchanged', () => {
    const text = '=SUM(1.5,{1,2;3,4},.5)';
    expect(readFormula(text, size, syntaxOf('en'), book)).toBe(text);
  });

  it('leaves addresses as written, the server keeping them by their rows and columns', () => {
    expect(readFormula('=sum(b3:A1;$B$2)+B:B+2:$4*LOG10(a1)', size, hr, book)).toBe(
      '=SUM(b3:A1,$B$2)+B:B+2:$4*LOG10(a1)',
    );
    expect(readFormula("='cijene 2026'!$B1*Skladište!A2:B3+stopa*sum(1)", size, hr, book)).toBe(
      "='cijene 2026'!$B1*Skladište!A2:B3+Stopa*SUM(1)",
    );
  });

  it('refuses a table the tab has not, and an address outside the table named', () => {
    expect(readFormula('=1+Nema!A1', size, hr, book)).toEqual({
      problem: 'table',
      from: 3,
      to: 10,
    });
    expect(readFormula("='Cijene 2026'!C1", size, hr, book)).toEqual({
      problem: 'outside',
      from: 1,
      to: 17,
    });
  });

  it('refuses an address outside the table, and a separator of the other kind', () => {
    expect(readFormula('=A1+A9', size, hr, book)).toEqual({ problem: 'outside', from: 4, to: 6 });
    expect(readFormula('=SUM(C:C)', size, hr, book)).toEqual({
      problem: 'outside',
      from: 5,
      to: 8,
    });
    expect(readFormula('=SUM(1,5,2)', size, hr, book)).toEqual({
      problem: 'separators',
      from: 8,
      to: 9,
    });
    expect(readFormula('=1.5', size, hr, book)).toEqual({ problem: 'separators', from: 2, to: 3 });
    expect(readFormula('=SUM(1;2)', size, syntaxOf('en'), book)).toEqual({
      problem: 'separators',
      from: 6,
      to: 7,
    });
  });
});

describe('formulaText', () => {
  it('writes the canonical form in the language', () => {
    const canonical = '=SUM(A1:A3,$B$2,2.5,{1,2;3,4})+B:B';
    expect(formulaText(canonical, hr, book)).toBe('=SUM(A1:A3;$B$2;2,5;{1;2/3;4})+B:B');
    expect(formulaText(canonical, syntaxOf('en'), book)).toBe(canonical);
  });

  it("keeps a reference in another table after the table's name, and a defined name as given", () => {
    expect(formulaText("='Cijene 2026'!A2:B$2+Skladište!B1+#REF!+stopa", hr, book)).toBe(
      "='Cijene 2026'!A2:B$2+Skladište!B1+#REF!+Stopa",
    );
  });

  it('reads back as the canonical form it was written from', () => {
    const canonical = '=IF(A1>0.5,"da;ne",ROUND(B2*1.25,2))';
    expect(readFormula(formulaText(canonical, hr, book), size, hr, book)).toBe(canonical);
  });
});

describe('pointing', () => {
  it('takes a reference after an operator, a bracket or a separator', () => {
    expect(takesReference('=SUM(', hr)).toBe(true);
    expect(takesReference('=A1+ ', hr)).toBe(true);
    expect(takesReference('=SUM(A1;', hr)).toBe(true);
    expect(takesReference('=SUM(A1,', hr)).toBe(false);
    expect(takesReference('=A1', hr)).toBe(false);
  });

  it('writes the address of a cell or of a rectangle', () => {
    expect(addressOf({ top: 0, left: 0, bottom: 0, right: 0 })).toBe('A1');
    expect(addressOf({ top: 1, left: 0, bottom: 4, right: 27 })).toBe('A2:AB5');
  });
});

describe('tableNameText', () => {
  it('quotes a name that is no bare word or reads as an address', () => {
    expect(
      ['Prodaja', 'Čaj_2', 'Cijene 2026', "O'Neil", 'AB12', 'R1C1', 'true', '2026'].map(
        tableNameText,
      ),
    ).toEqual([
      'Prodaja',
      'Čaj_2',
      "'Cijene 2026'",
      "'O''Neil'",
      "'AB12'",
      "'R1C1'",
      "'true'",
      "'2026'",
    ]);
  });
});

describe('rectOfAddress', () => {
  it('reads a cell or a rectangle in either order', () => {
    expect(rectOfAddress(' b2:A1 ')).toEqual({ top: 0, left: 0, bottom: 1, right: 1 });
    expect(rectOfAddress('C3')).toEqual({ top: 2, left: 2, bottom: 2, right: 2 });
    expect(rectOfAddress('A0')).toBeNull();
    expect(rectOfAddress('Prodaja!A1')).toBeNull();
  });
});

describe('pointedAt', () => {
  const b4 = { top: 3, left: 1, bottom: 3, right: 1 };

  it('reads cells, after the name of their table where it is given', () => {
    expect(pointedAt(' B4 ')).toEqual({ table: null, rect: b4 });
    expect(pointedAt("'2044'!B4:d9")).toEqual({
      table: '2044',
      rect: { top: 3, left: 1, bottom: 8, right: 3 },
    });
    expect(pointedAt('Ulaz!$B$4')).toEqual({ table: 'Ulaz', rect: b4 });
    expect(pointedAt("'Jure''s'!B4")).toEqual({ table: "Jure's", rect: b4 });
  });

  it('takes a name for a defined name, and nothing else for anything', () => {
    expect(pointedAt('Ukupno')).toEqual({ name: 'Ukupno' });
    expect(pointedAt('Ulaz!')).toBeNull();
    expect(pointedAt('R1C1')).toBeNull();
    expect(pointedAt('B4 C5')).toBeNull();
  });

  it('reads what placeText writes', () => {
    for (const table of [null, 'Ulaz', '2044', 'Cijene 2026']) {
      expect(pointedAt(placeText(table, b4))).toEqual({ table, rect: b4 });
    }
    expect(placeText('2044', b4)).toBe("'2044'!B4");
  });
});
