import type { DocumentLocale } from '../tree';

/** Number formats a table cell can take from the menu; any other is written as its code. */
export const PRESETS = [
  'number',
  'integer',
  'currency',
  'percent',
  'scientific',
  'date',
  'time',
  'dateTime',
] as const;
export type Preset = (typeof PRESETS)[number];

const DATES: Record<DocumentLocale, string> = {
  hr: 'dd.mm.yyyy.',
  en: 'm/d/yyyy',
  'en-GB': 'dd/mm/yyyy',
  de: 'dd.mm.yyyy',
  fr: 'dd/mm/yyyy',
  it: 'dd/mm/yyyy',
  es: 'dd/mm/yyyy',
};

const EURO = '#,##0.00 "€"';
const CURRENCIES: Record<DocumentLocale, string> = {
  hr: EURO,
  en: '"$"#,##0.00',
  'en-GB': '"£"#,##0.00',
  de: EURO,
  fr: EURO,
  it: EURO,
  es: EURO,
};

/** A date code as the document's language writes one out. */
export function dateCode(locale: DocumentLocale): string {
  return DATES[locale];
}

/** A day as the document's language writes a short date. */
export function writtenDate(date: Date, locale: DocumentLocale): string {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const parts: Record<string, string> = {
    yyyy: String(date.getFullYear()),
    mm: String(month).padStart(2, '0'),
    dd: String(day).padStart(2, '0'),
    m: String(month),
    d: String(day),
  };
  return DATES[locale].replace(/yyyy|mm|dd|m|d/g, (token) => parts[token]);
}

/** The code of a preset as the document's language shows it. Codes are Excel's, in the canonical
 * form xlsx stores; the server writes them with the language's separators. The dates are Excel's
 * built-in short date and date with time, which the server shows as the language writes a date. */
export function presetCode(preset: Preset, locale: DocumentLocale): string {
  switch (preset) {
    case 'number':
      return '#,##0.00';
    case 'integer':
      return '#,##0';
    case 'currency':
      return CURRENCIES[locale];
    case 'percent':
      return '0.00%';
    case 'scientific':
      return '0.00E+00';
    case 'date':
      return 'mm-dd-yy';
    case 'time':
      return locale === 'en' ? 'h:mm AM/PM' : 'hh:mm';
    case 'dateTime':
      return 'm/d/yy h:mm';
  }
}

interface Separators {
  decimal: string;
  group: string;
}

const STORED: Separators = { decimal: '.', group: ',' };

/** The separators the language writes numbers with; a group of spaces, however narrow, is typed in
 * a code as a plain space. */
function separatorsOf(locale: DocumentLocale): Separators {
  const parts = new Intl.NumberFormat(locale).formatToParts(1234567.5);
  const part = (type: string) => parts.find((found) => found.type === type)?.value;
  const group = part('group') ?? STORED.group;
  return { decimal: part('decimal') ?? STORED.decimal, group: /\s/.test(group) ? ' ' : group };
}

interface Token {
  text: string;
  /** One of the code's own characters, not text it writes as it stands. */
  code: boolean;
}

function tokensOf(code: string): Token[] {
  const tokens: Token[] = [];
  for (let at = 0; at < code.length;) {
    const char = code[at];
    let end = at + 1;
    if (char === '"' || char === '[') {
      end = code.indexOf(char === '"' ? '"' : ']', at + 1) + 1 || code.length;
    } else if ('\\_*'.includes(char)) {
      end = Math.min(at + 2, code.length);
    }
    tokens.push({ text: code.slice(at, end), code: !'"[\\_*'.includes(char) });
    at = end;
  }
  return tokens;
}

const PLACEHOLDER = /^[0#?]$/;

function placeholder(token: Token | undefined): boolean {
  return Boolean(token?.code && PLACEHOLDER.test(token.text));
}

/** A section of dates or times writes its points and commas as they stand. */
function recodeSection(section: Token[], from: Separators, to: Separators): string {
  const timed = section.some((token) =>
    token.code ? /^[dmyhs]$/i.test(token.text) : /^\[[hms]+\]$/i.test(token.text),
  );
  if (timed) return section.map((token) => token.text).join('');
  // A space groups thousands only between digits, and never in a fraction such as "# ?/?".
  const fraction = section.some((token) => token.code && token.text === '/');
  const groups = (index: number) =>
    from.group !== ' ' ||
    (!fraction &&
      placeholder(section[index - 1]) &&
      (index === section.length - 1 || placeholder(section[index + 1])));
  return section
    .map((token, index) => {
      if (!token.code) {
        return /^\[[<>=]/.test(token.text)
          ? token.text.replaceAll(from.decimal, to.decimal)
          : token.text;
      }
      if (token.text === from.decimal) return to.decimal;
      if (token.text === from.group && groups(index)) return to.group;
      return token.text;
    })
    .join('');
}

function recode(code: string, from: Separators, to: Separators): string {
  const sections: Token[][] = [[]];
  for (const token of tokensOf(code)) {
    if (token.code && token.text === ';') sections.push([]);
    else sections.at(-1)!.push(token);
  }
  return sections.map((section) => recodeSection(section, from, to)).join(';');
}

/** A stored code as the document's language writes it, with its decimal and thousands separators;
 * dates, times and quoted text stay as they are written. */
export function localCode(code: string, locale: DocumentLocale): string {
  return recode(code, STORED, separatorsOf(locale));
}

/** A code written as the document's language writes it, in the form xlsx stores. */
export function storedCode(code: string, locale: DocumentLocale): string {
  return recode(code, separatorsOf(locale), STORED);
}
