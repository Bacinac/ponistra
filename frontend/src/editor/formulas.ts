import type { DocumentLocale } from '../tree';
import type { Rect } from './tables';

/** What a cell with a formula or a number format shows, as the server computed it. */
export interface Value {
  text: string;
  kind: 'number' | 'text' | 'bool' | 'error';
}

/** How a language writes a formula: its decimal mark, what separates arguments (and an array's
 * columns) and what separates an array's rows. */
export interface Syntax {
  decimal: string;
  list: string;
  row: string;
}

export const CANONICAL: Syntax = { decimal: '.', list: ',', row: ';' };
const SEMICOLONS: Syntax = { decimal: ',', list: ';', row: '/' };

/** How formulas are written: a language with a decimal comma separates arguments with
 * semicolons and an array's rows with slashes. */
export function syntaxOf(locale: DocumentLocale): Syntax {
  const parts = new Intl.NumberFormat(locale).formatToParts(1.5);
  return parts.find((part) => part.type === 'decimal')?.value === ',' ? SEMICOLONS : CANONICAL;
}

/** How many rows and columns a table has. */
export interface Size {
  rows: number;
  cols: number;
}

/** The tables a formula can refer to by name, as a workbook's sheets, and the defined names. */
export interface Book {
  /** The table a name names, whatever the case it is written in. */
  named(name: string): Size | null;
  /** A defined name as it was given, whatever the case it is written in. */
  name(name: string): string | null;
}

/** Why a formula could not be read, and where in its text. */
export interface Misread {
  problem: 'outside' | 'separators' | 'table';
  from: number;
  to: number;
}

interface Address {
  col?: { index: number; abs: boolean };
  row?: { index: number; abs: boolean };
}

interface Found {
  text: string;
  from: Address;
  to?: Address;
}

type Token =
  | { kind: 'text' | 'number' | 'list' | 'row' | 'stray'; text: string; at: number }
  | ({ kind: 'reference'; at: number; table?: string } & Found);

const CELL = String.raw`(\$?)([A-Za-z]{1,3})(\$?)(\d+)`;
const CELLS = new RegExp(String.raw`${CELL}(?::${CELL})?(?![\w.(])`, 'y');
const COLUMNS = /(\$?)([A-Za-z]{1,3}):(\$?)([A-Za-z]{1,3})(?![\w.(])/y;
const LINES = /(\$?)(\d+):(\$?)(\d+)(?![\w.(])/y;
const NAME = /[\p{L}_\\][\p{L}\p{N}_.]*/uy;
/** A table's name before an address, as a sheet's: in quotes, which double within it, where it
 * is no bare name. */
const TABLE_NAME = /(?:'((?:[^']|'')+)'|([\p{L}_][\p{L}\p{N}_.]*))!/uy;
const BARE = /^[\p{L}_][\p{L}\p{N}_.]*$/u;
const ADDRESS_LIKE = /^(?:[A-Za-z]{1,3}\d+|[Rr]\d*[Cc]\d*|true|false)$/i;
const ERROR = /#[A-Za-z0-9/]+[!?]?/y;
const OPERATORS = '=(+-*/^&<>:';

function escaped(mark: string): string {
  return mark.replace(/[.\\/]/g, '\\$&');
}

/** A number may start with its decimal mark where that is a point, never a comma, which would
 * take in a stray separator. */
function numbers(syntax: Syntax): RegExp {
  const mark = escaped(syntax.decimal);
  const exponent = String.raw`(?:[eE][+-]?\d+)?`;
  const bare = syntax.decimal === '.' ? String.raw`|${mark}\d+${exponent}` : '';
  return new RegExp(String.raw`\d+(?:${mark}\d*)?${exponent}${bare}`, 'y');
}

export function columnName(index: number): string {
  let name = '';
  for (let rest = index + 1; rest > 0; rest = Math.floor((rest - 1) / 26)) {
    name = String.fromCharCode(65 + ((rest - 1) % 26)) + name;
  }
  return name;
}

function columnIndex(name: string): number {
  return (
    [...name.toUpperCase()].reduce((index, char) => index * 26 + char.charCodeAt(0) - 64, 0) - 1
  );
}

function matched(pattern: RegExp, text: string, at: number): RegExpExecArray | null {
  pattern.lastIndex = at;
  return pattern.exec(text);
}

function quoted(text: string, at: number): number {
  const mark = text[at];
  for (let end = at + 1; end < text.length; end++) {
    if (text[end] !== mark) continue;
    if (text[end + 1] !== mark) return end + 1;
    end++;
  }
  return text.length;
}

/** A table's name as a formula writes it before an address. */
export function tableNameText(name: string): string {
  return BARE.test(name) && !ADDRESS_LIKE.test(name) ? name : `'${name.replace(/'/g, "''")}'`;
}

function addressAt(text: string, at: number): Found | null {
  let found = matched(CELLS, text, at);
  if (found) {
    const [, absCol, col, absRow, row, toAbsCol, toCol, toAbsRow, toRow] = found;
    const cell = (absCol: string, col: string, absRow: string, row: string): Address => ({
      col: { index: columnIndex(col), abs: absCol === '$' },
      row: { index: Number(row) - 1, abs: absRow === '$' },
    });
    return {
      text: found[0],
      from: cell(absCol, col, absRow, row),
      to: toCol ? cell(toAbsCol, toCol, toAbsRow, toRow) : undefined,
    };
  }
  found = matched(COLUMNS, text, at);
  if (found) {
    const [, absFrom, from, absTo, to] = found;
    return {
      text: found[0],
      from: { col: { index: columnIndex(from), abs: absFrom === '$' } },
      to: { col: { index: columnIndex(to), abs: absTo === '$' } },
    };
  }
  found = matched(LINES, text, at);
  if (found) {
    const [, absFrom, from, absTo, to] = found;
    return {
      text: found[0],
      from: { row: { index: Number(from) - 1, abs: absFrom === '$' } },
      to: { row: { index: Number(to) - 1, abs: absTo === '$' } },
    };
  }
  return null;
}

function lex(text: string, syntax: Syntax, start: number, book: Book): Token[] {
  const tokens: Token[] = [];
  const number = numbers(syntax);
  const push = (kind: Exclude<Token['kind'], 'reference'>, at: number, end: number) =>
    tokens.push({ kind, text: text.slice(at, end), at });
  let depth = 0;
  for (let at = start; at < text.length;) {
    const char = text[at];
    const named = matched(TABLE_NAME, text, at);
    const address = named && addressAt(text, at + named[0].length);
    if (named && address) {
      const table = named[1]?.replace(/''/g, "'") ?? named[2];
      tokens.push({ kind: 'reference', at, table, ...address, text: named[0] + address.text });
      at += named[0].length + address.text.length;
      continue;
    }
    if (char === '"' || char === "'") {
      const end = quoted(text, at);
      push('text', at, end);
      at = end;
      continue;
    }
    if (char === syntax.list) {
      push('list', at, at + 1);
      at++;
      continue;
    }
    if (depth > 0 && (char === syntax.row || (syntax.row === '/' && char === '\\'))) {
      push('row', at, at + 1);
      at++;
      continue;
    }
    let found = matched(ERROR, text, at);
    if (found) {
      tokens.push({ kind: 'text', text: found[0].toUpperCase(), at });
      at += found[0].length;
      continue;
    }
    const bare = addressAt(text, at);
    if (bare) {
      tokens.push({ kind: 'reference', at, ...bare });
      at += bare.text.length;
      continue;
    }
    found = matched(number, text, at);
    if (found) {
      push('number', at, at + found[0].length);
      at += found[0].length;
      continue;
    }
    found = matched(NAME, text, at);
    if (found) {
      const called = text[at + found[0].length] === '(';
      const name = (!called && book.name(found[0])) || found[0].toUpperCase();
      tokens.push({ kind: 'text', text: name, at });
      at += found[0].length;
      continue;
    }
    const stray = syntax.list === ';' ? char === ',' || char === '.' : char === ';' && depth === 0;
    push(stray ? 'stray' : 'text', at, at + 1);
    if (char === '{') depth++;
    if (char === '}') depth = Math.max(0, depth - 1);
    at++;
  }
  return tokens;
}

function written(token: Token, from: Syntax, to: Syntax): string {
  switch (token.kind) {
    case 'number':
      return token.text.replace(from.decimal, to.decimal);
    case 'list':
      return to.list;
    case 'row':
      return to.row;
    default:
      return token.text;
  }
}

function inside(address: Address, size: Size): boolean {
  return (
    (!address.col || address.col.index < size.cols) &&
    (!address.row || address.row.index < size.rows)
  );
}

/** A formula written in the document's language, in the canonical form the server reads (D4), or
 * why it cannot be read: a separator of another language, a table the tab has not, or an address
 * outside the table it is in, which has `size` rows and columns where it is the cell's own. */
export function readFormula(
  text: string,
  size: Size,
  syntax: Syntax,
  book: Book,
): string | Misread {
  let canonical = '=';
  for (const token of lex(text, syntax, text.startsWith('=') ? 1 : 0, book)) {
    const end = token.at + token.text.length;
    if (token.kind === 'stray') return { problem: 'separators', from: token.at, to: end };
    if (token.kind !== 'reference') {
      canonical += written(token, syntax, CANONICAL);
      continue;
    }
    const table = token.table === undefined ? null : book.named(token.table);
    if (token.table !== undefined && !table) return { problem: 'table', from: token.at, to: end };
    const ends = [token.from, ...(token.to ? [token.to] : [])];
    if (!ends.every((each) => inside(each, table ?? size))) {
      return { problem: 'outside', from: token.at, to: end };
    }
    canonical += token.text;
  }
  return canonical;
}

export function misread(found: string | Misread): found is Misread {
  return typeof found !== 'string';
}

/** A formula the server gave in the canonical form, as the document's language writes it. */
export function formulaText(canonical: string, syntax: Syntax, book: Book): string {
  const tokens = lex(canonical, CANONICAL, canonical.startsWith('=') ? 1 : 0, book);
  return `=${tokens.map((token) => written(token, CANONICAL, syntax)).join('')}`;
}

/** The address of a cell or of a rectangle of cells, as a click or a drag points at it. */
export function addressOf(rect: Rect): string {
  const start = `${columnName(rect.left)}${rect.top + 1}`;
  const single = rect.top === rect.bottom && rect.left === rect.right;
  return single ? start : `${start}:${columnName(rect.right)}${rect.bottom + 1}`;
}

const ADDRESS = /^\$?([A-Za-z]{1,3})\$?(\d+)(?::\$?([A-Za-z]{1,3})\$?(\d+))?$/;

/** What the name box or an address's `cell` points at (D16): cells by their address, after the
 * name of their table where it is named (`'2044'!B4:D9`), or a defined name. */
export type Pointed = { table: string | null; rect: Rect } | { name: string };

export function pointedAt(text: string): Pointed | null {
  const written = text.trim();
  const named = matched(TABLE_NAME, written, 0);
  const rect = rectOfAddress(named ? written.slice(named[0].length) : written);
  if (rect) {
    return { table: named ? (named[2] ?? named[1].replace(/''/g, "'")) : null, rect };
  }
  return !named && BARE.test(written) && !ADDRESS_LIKE.test(written) ? { name: written } : null;
}

/** Cells as the name box shows them, after the name of their table where it has one. */
export function placeText(table: string | null, rect: Rect): string {
  return (table ? `${tableNameText(table)}!` : '') + addressOf(rect);
}

/** The cell or rectangle of cells an address such as `B2:D7` points at, in either order. */
export function rectOfAddress(text: string): Rect | null {
  const found = ADDRESS.exec(text.trim());
  if (!found) return null;
  const [, first, top, last = first, bottom = top] = found;
  const rows = [Number(top) - 1, Number(bottom) - 1];
  const cols = [columnIndex(first), columnIndex(last)];
  if (rows.some((row) => row < 0)) return null;
  return {
    top: Math.min(...rows),
    left: Math.min(...cols),
    bottom: Math.max(...rows),
    right: Math.max(...cols),
  };
}

/** The text before the caret ends where a formula takes a reference next. */
export function takesReference(before: string, syntax: Syntax): boolean {
  const last = before.trimEnd().at(-1);
  return last !== undefined && (OPERATORS.includes(last) || last === syntax.list);
}
