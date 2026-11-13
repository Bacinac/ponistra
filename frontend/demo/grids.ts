import { tellServerNeeded } from './banner';
import { missing, recordedFile, type Frame } from './recording';
import type { DemoSocket, Peer } from './sockets';

/** What the walk heard on a document's tables socket (`/api/grids/<document>`), each frame taken
 * once however often it came. */
interface Book {
  tables?: Frame;
  names?: Frame;
  looks: Record<string, unknown>;
  /** The outlines of each tab's tables, by tab, null for the headers and footers. */
  grids: Map<string | null, Frame>;
  /** Every row of each table the walk was shown, where it stands, its number and its cells. */
  rows: Map<
    string,
    { at: Record<string, number>; numbers?: Record<string, number>; rows: Record<string, unknown> }
  >;
}

const books = new Map<string, Promise<Book | null>>();

function bookOf(frames: Frame[]): Book {
  const book: Book = { looks: {}, grids: new Map(), rows: new Map() };
  for (const frame of frames) {
    switch (frame.type) {
      case 'tables':
        book.tables = frame;
        break;
      case 'names':
        book.names = frame;
        break;
      case 'looks':
        Object.assign(book.looks, frame.looks as Record<string, unknown>);
        break;
      case 'grids':
        book.grids.set(frame.tab as string | null, frame);
        break;
      case 'rows': {
        const table = frame.table as string;
        const held = book.rows.get(table) ?? { at: {}, rows: {} };
        Object.assign(held.at, frame.at as Record<string, number>);
        Object.assign(held.rows, frame.rows as Record<string, unknown>);
        if (frame.numbers)
          held.numbers = { ...held.numbers, ...(frame.numbers as Record<string, number>) };
        book.rows.set(table, held);
        break;
      }
    }
  }
  return book;
}

/** Documents the visitor made in the tab, which have no tables yet. */
export const madeBooks = new Set<string>();

async function opened(document: string): Promise<Book | null> {
  if (madeBooks.has(document))
    return bookOf([
      { type: 'tables', tables: [] },
      { type: 'names', names: [] },
    ]);
  const file = await recordedFile(`grids/${document}.json`);
  if (!file) {
    missing(`grids ${document}`);
    return null;
  }
  return bookOf((await file.json()) as Frame[]);
}

/** A document's tables as the backend serves them (apps/collab/books.py), from what the walk was
 * shown. Their cells are reckoned by the backend's engine, which the demo does not have: an edit
 * is refused, and says so. */
export function grids(document: string, socket: DemoSocket): Peer {
  if (!books.has(document)) books.set(document, opened(document));
  let book: Book | null = null;
  const waiting: Frame[] = [];
  const say = (frame: Record<string, unknown>) => socket.deliver(JSON.stringify(frame));

  const rowsOf = (table: string) => {
    const held = book!.rows.get(table);
    if (!held) missing(`grids ${document} rows ${table}`);
    return held ?? { at: {}, rows: {} };
  };

  const take = (message: Frame) => {
    switch (message.type) {
      case 'watch': {
        const tab = message.tab as string | null;
        if (book!.tables) say(book!.tables);
        if (book!.names) say(book!.names);
        say({ type: 'looks', looks: book!.looks });
        const outlines = book!.grids.get(tab);
        if (!outlines && !madeBooks.has(document)) missing(`grids ${document} tab ${tab}`);
        say(outlines ?? { type: 'grids', tab, grids: [] });
        break;
      }
      case 'rows': {
        const table = message.table as string;
        say({ type: 'rows', table, ...rowsOf(table) });
        break;
      }
      case 'do':
      case 'undo':
        tellServerNeeded();
        say({ type: 'refused', token: message.as ?? message.token, code: 'demo_server' });
        break;
      case 'referred':
        say({ type: 'referred', table: message.table, referred: false });
        break;
      case 'where':
        say({ type: 'where', name: message.name, table: message.table, at: null });
        break;
      case 'standing': {
        const table = message.table as string;
        const { at, numbers = {} } = rowsOf(table);
        const wanted = new Set(message.numbered as number[]);
        const named = Object.fromEntries(
          Object.entries(numbers)
            .filter(([, number]) => wanted.has(number))
            .map(([row, number]) => [number, row]),
        );
        say({ ...message, type: 'standing', at, numbers, named });
        break;
      }
      case 'values':
        tellServerNeeded();
        say({ type: 'values', table: message.table, col: message.col, values: [], more: false });
        break;
      case 'filter':
        tellServerNeeded();
        say({ type: 'unfiltered', table: message.table, code: 'demo_server' });
        break;
    }
  };

  void books.get(document)!.then((found) => {
    if (!found) {
      books.delete(document);
      socket.close(4404, 'demo');
      return;
    }
    book = found;
    for (const message of waiting.splice(0)) take(message);
  });

  return {
    take: (data) => {
      if (typeof data !== 'string') return;
      const message = JSON.parse(data) as Frame;
      if (book) take(message);
      else waiting.push(message);
    },
    left: () => {},
  };
}
