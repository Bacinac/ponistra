/** A page as it will stand in the file being put together: a page of a file, counted from 1,
 * turned clockwise by quarters. */
export interface Sheet {
  key: string;
  file: string;
  page: number;
  turn: number;
}

export interface History {
  past: Sheet[][];
  present: Sheet[];
  future: Sheet[][];
}

export function sheetsOf(file: string, count: number, key: () => string): Sheet[] {
  return Array.from({ length: count }, (_, index) => ({
    key: key(),
    file,
    page: index + 1,
    turn: 0,
  }));
}

export function turned(sheets: Sheet[], chosen: Set<string>, by: 1 | -1): Sheet[] {
  return sheets.map((sheet) =>
    chosen.has(sheet.key) ? { ...sheet, turn: (sheet.turn + by + 4) % 4 } : sheet,
  );
}

export function without(sheets: Sheet[], chosen: Set<string>): Sheet[] {
  return sheets.filter((sheet) => !chosen.has(sheet.key));
}

/** The chosen sheets, in their order, put in the gap before the sheet now at `to`. */
export function moved(sheets: Sheet[], chosen: Set<string>, to: number): Sheet[] {
  const picked = sheets.filter((sheet) => chosen.has(sheet.key));
  const rest = without(sheets, chosen);
  const before = without(sheets.slice(0, to), chosen).length;
  return [...rest.slice(0, before), ...picked, ...rest.slice(before)];
}

/** The chosen sheets one place earlier or later, gathered where they were apart. */
export function stepped(sheets: Sheet[], chosen: Set<string>, by: 1 | -1): Sheet[] {
  const at = sheets.flatMap((sheet, index) => (chosen.has(sheet.key) ? [index] : []));
  if (at.length === 0) return sheets;
  const to = by < 0 ? Math.max(0, at[0] - 1) : Math.min(sheets.length, at[at.length - 1] + 2);
  return moved(sheets, chosen, to);
}

export function inserted(sheets: Sheet[], added: Sheet[], at: number): Sheet[] {
  return [...sheets.slice(0, at), ...added, ...sheets.slice(at)];
}

export function same(one: Sheet[], other: Sheet[]): boolean {
  return (
    one.length === other.length &&
    one.every(
      (sheet, index) =>
        sheet.file === other[index].file &&
        sheet.page === other[index].page &&
        sheet.turn === other[index].turn,
    )
  );
}

/** The pages as the server takes them. */
export function entries(sheets: Sheet[]) {
  return sheets.map(({ file, page, turn }) => (turn ? { file, page, turn } : { file, page }));
}

/** Page numbers as a reader writes them, runs joined by an en dash: 2–5, 7. */
export function span(pages: number[], number: (value: number) => string): string {
  const runs: [number, number][] = [];
  for (const page of pages) {
    const last = runs[runs.length - 1];
    if (last && page === last[1] + 1) last[1] = page;
    else runs.push([page, page]);
  }
  return runs
    .map(([from, to]) => (from === to ? number(from) : `${number(from)}–${number(to)}`))
    .join(', ');
}

export function begun(sheets: Sheet[]): History {
  return { past: [], present: sheets, future: [] };
}

export function done(history: History, next: Sheet[]): History {
  if (next === history.present) return history;
  return { past: [...history.past, history.present], present: next, future: [] };
}

export function undone(history: History): History {
  const previous = history.past[history.past.length - 1];
  if (!previous) return history;
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
  };
}

export function redone(history: History): History {
  const [next, ...future] = history.future;
  if (!next) return history;
  return { past: [...history.past, history.present], present: next, future };
}
