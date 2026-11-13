import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Grid, GridClient, Refusal, type Outline } from './grids';

class FakeSocket extends EventTarget {
  static readonly CONNECTING = 0;
  static made: FakeSocket[] = [];
  readyState = FakeSocket.CONNECTING;
  sent: Record<string, unknown>[] = [];

  constructor(readonly url: string) {
    super();
    FakeSocket.made.push(this);
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(): void {
    this.readyState = 3;
    this.dispatchEvent(new Event('close'));
  }

  opened(): void {
    this.readyState = 1;
    this.dispatchEvent(new Event('open'));
  }

  receive(message: object): void {
    this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(message) }));
  }

  taken(): Record<string, unknown>[] {
    return this.sent.splice(0);
  }
}

const OUTLINE: Outline = {
  table: 't',
  name: 'Cijene',
  cols: [
    ['a', 12],
    ['b', null],
  ],
  rows: 3,
  at: { r1: 0, r2: 1, r3: 2 },
  heights: { r2: 30 },
  looks: {},
  hidden: {},
  merges: { 'r1:a': 'r1:b' },
  frozen: 'r1',
};

let client: GridClient;

function connected(): FakeSocket {
  client = new GridClient('d', 'ws://test/api/grids/d');
  client.watch('tab');
  vi.advanceTimersByTime(0);
  const socket = FakeSocket.made.at(-1)!;
  socket.opened();
  expect(socket.taken()).toEqual([{ type: 'watch', tab: 'tab' }]);
  socket.receive({ type: 'grids', tab: 'tab', grids: [OUTLINE] });
  return socket;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', FakeSocket);
  FakeSocket.made = [];
});

afterEach(() => {
  client.close();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('a grid client', () => {
  it('watches its tabs and holds their outlines', () => {
    connected();
    const grid = client.grid('t')!;
    expect([grid.name, grid.tab, grid.rowCount, grid.rowId(1), grid.cols]).toEqual([
      'Cijene',
      'tab',
      3,
      'r2',
      ['a', 'b'],
    ]);
    expect([grid.widths.get('a'), grid.heights.get('r2'), grid.merges.get('r1:a')]).toEqual([
      12,
      30,
      'r1:b',
    ]);
  });

  it('asks for the rows its views show by where they stand, in one message, and lets them go', async () => {
    const socket = connected();
    const [first, second] = [{}, {}];
    client.show(first, 't', [[0, 1]]);
    client.show(second, 't', [
      [1, 1],
      [5, 4],
    ]);
    await Promise.resolve();
    expect(socket.taken()).toEqual([{ type: 'rows', table: 't', spans: [[0, 1]] }]);

    const told = vi.fn();
    client.subscribe('t', told);
    socket.receive({
      type: 'rows',
      table: 't',
      at: { r1: 0, r2: 1 },
      rows: {
        r1: { cells: { a: { text: '5' } }, values: { a: { kind: 'number', text: '5' } } },
        r2: { cells: {}, values: {} },
      },
    });
    expect(told).toHaveBeenCalledWith({ table: 't', outline: false, rows: new Set(['r1', 'r2']) });
    expect(client.grid('t')!.cell('r1', 'a')).toEqual({ text: '5' });

    client.forget(first);
    await Promise.resolve();
    expect(socket.taken()).toEqual([{ type: 'rows', table: 't', spans: [[1, 1]] }]);
    socket.receive({ type: 'rows', table: 't', at: { r2: 1 }, rows: {} });
    expect([client.grid('t')!.holds('r1'), client.grid('t')!.holds('r2')]).toEqual([false, true]);
    expect(told).toHaveBeenLastCalledWith({ table: 't', outline: false, rows: new Set(['r1']) });

    client.show(first, 't', [[1, 1]]);
    await Promise.resolve();
    expect(socket.taken()).toEqual([]);
  });

  it('asks again for the rows shown once lines move under them', async () => {
    const socket = connected();
    client.show({}, 't', [[0, 1]]);
    await Promise.resolve();
    socket.taken();
    socket.receive({
      type: 'patch',
      patches: [{ table: 't', rows: { put: [['n', 0, null, null]] } }],
    });
    await Promise.resolve();
    expect(socket.taken()).toEqual([{ type: 'rows', table: 't', spans: [[0, 1]] }]);
    expect([client.grid('t')!.rowId(0), client.grid('t')!.rowIndex('r1')]).toEqual(['n', 1]);
  });

  it('asks once where the rows it does not know stand, by their places or their ids', async () => {
    const socket = connected();
    socket.receive({ type: 'grids', tab: 'tab', grids: [{ ...OUTLINE, rows: 5, at: { r1: 0 } }] });
    const ids = client.rowIds('t', [0, 2]);
    const again = client.rowIds('t', [0, 2]);
    const places = client.rowPlaces('t', ['r9', 'r1']);
    expect(socket.taken()).toEqual([
      { type: 'standing', table: 't', places: [0, 2], rows: [], numbered: [] },
      { type: 'standing', table: 't', places: [], rows: ['r9', 'r1'], numbered: [] },
    ]);
    socket.receive({
      type: 'standing',
      table: 't',
      places: [0, 2],
      rows: [],
      numbered: [],
      at: { r1: 0, r7: 2 },
    });
    socket.receive({
      type: 'standing',
      table: 't',
      places: [],
      rows: ['r9', 'r1'],
      numbered: [],
      at: { r1: 0 },
    });
    expect(await Promise.all([ids, again, places])).toEqual([
      ['r1', 'r7'],
      ['r1', 'r7'],
      [-1, 0],
    ]);
    expect(await client.rowIds('t', [2])).toEqual(['r7']);
    expect(socket.taken()).toEqual([]);

    const past = client.rowIds('t', [9]);
    socket.receive({ type: 'standing', table: 't', places: [9], rows: [], numbered: [], at: {} });
    await expect(past).rejects.toEqual(new Refusal('no_line', '9'));
  });

  it('numbers the rows a filter shows by their own places and lays the table out again', async () => {
    const socket = connected();
    const kava = { col: 'a', values: ['kava'] };
    const outline = { ...OUTLINE, rows: 2, at: { r1: 0, r3: 1 }, numbers: { r1: 0, r3: 2 } };
    socket.receive({ type: 'grids', tab: 'tab', grids: [{ ...outline, filter: [kava] }] });
    const grid = client.grid('t')!;
    expect([grid.plain, grid.rowNumber(0), grid.rowNumber(1), grid.filter]).toEqual([
      false,
      0,
      2,
      [kava],
    ]);
    const places = client.numberedPlaces('t', [2, 1]);
    expect(socket.taken()).toEqual([
      { type: 'standing', table: 't', places: [], rows: [], numbered: [2, 1] },
    ]);
    socket.receive({
      type: 'standing',
      table: 't',
      places: [],
      rows: [],
      numbered: [2, 1],
      at: {},
      named: { 2: 'r3' },
    });
    expect(await places).toEqual([1, -1]);

    const cleared = client.filter('t', []);
    expect(socket.taken()).toEqual([{ type: 'filter', table: 't', conditions: [] }]);
    const laid = { ...OUTLINE, rows: 3, at: { r1: 0, r2: 1, r3: 2 } };
    socket.receive({ type: 'patch', by: null, patches: [{ table: 't', laid }] });
    socket.receive({ type: 'filtered', table: 't' });
    await cleared;
    expect([grid.plain, grid.rowCount, grid.rowNumber(1), grid.filter]).toEqual([true, 3, 1, []]);

    const wrong = client.filter('t', [{ col: 'a', op: 'greater', value: 'dva' }]);
    socket.receive({ type: 'unfiltered', table: 't', code: 'number' });
    await expect(wrong).rejects.toEqual(new Refusal('number', 't'));
  });

  it('holds the looks the server sends once, and shows a cell the look of its row or column', async () => {
    const socket = connected();
    const bold = { marks: { strong: {} } };
    const centred = { attrs: { align: 'center' } };
    socket.receive({ type: 'looks', looks: { B: bold, C: centred, E: {} } });
    socket.receive({
      type: 'grids',
      tab: 'tab',
      grids: [{ ...OUTLINE, looks: { cols: { b: 'B' }, rows: { r2: 'C' } } }],
    });
    client.show({}, 't', [[0, 2]]);
    await Promise.resolve();
    socket.receive({
      type: 'rows',
      table: 't',
      at: { r1: 0, r2: 1, r3: 2 },
      rows: {
        r1: { cells: { a: { text: 'x', look: 'C' }, b: { text: 'y' } }, values: {} },
        r2: { cells: { b: { text: 'z', look: 'E' } }, values: {} },
        r3: { cells: {}, values: {} },
      },
    });
    const grid = client.grid('t')!;
    expect(grid.cell('r1', 'a')).toEqual({ text: 'x', look: centred });
    expect(grid.cell('r1', 'b')).toEqual({ text: 'y', look: bold });
    expect(grid.cell('r1', 'b')).toBe(grid.cell('r1', 'b'));
    expect(grid.cell('r3', 'b')).toEqual({ look: bold });
    expect(grid.cell('r2', 'b')).toEqual({ text: 'z', look: {} });
    expect(grid.cell('r2', 'a')).toEqual({ look: centred });
    expect(grid.cell('r3', 'a')).toBeUndefined();

    socket.receive({
      type: 'patch',
      by: null,
      patches: [{ table: 't', looks: { cols: { b: null }, rows: { r3: 'B' } } }],
    });
    expect([grid.cell('r1', 'b'), grid.cell('r3', 'a')]).toEqual([{ text: 'y' }, { look: bold }]);
    expect(() => grid.apply({ table: 't', looks: { rows: { r1: 'X' } } })).toThrow('no look X');
  });

  it('shows a written cell at once, and its value once the server has computed it', async () => {
    const socket = connected();
    client.show({}, 't', [[0, 0]]);
    socket.receive({
      type: 'rows',
      table: 't',
      at: { r1: 0 },
      rows: { r1: { cells: {}, values: {} } },
    });
    socket.taken();

    const operations = [
      { op: 'cells', table: 't', cells: [{ row: 'r1', col: 'a', value: '=2*3' }] },
    ];
    const written = { table: 't', cells: new Map([['r1:a', { formula: '=2*3' }]]) };
    const { token, answer } = client.do('tab', operations, { written });
    const grid = client.grid('t')!;
    expect([grid.cell('r1', 'a'), grid.value('r1', 'a')]).toEqual([{ formula: '=2*3' }, undefined]);
    expect(socket.taken()).toEqual([{ type: 'do', token, tab: 'tab', operations }]);

    socket.receive({
      type: 'patch',
      patches: [
        {
          table: 't',
          cells: { r1: { a: { formula: '=2*3' } } },
          values: { r1: { a: { kind: 'number', text: '6' } } },
        },
      ],
    });
    socket.receive({ type: 'done', token });
    await answer;
    expect([grid.cell('r1', 'a'), grid.value('r1', 'a')]).toEqual([
      { formula: '=2*3' },
      { kind: 'number', text: '6' },
    ]);
  });

  it('knows where each row of a table it made stands, which the outline names only at its ends', async () => {
    const socket = connected();
    const made = (id: string, by: string) =>
      socket.receive({
        type: 'patch',
        by,
        patches: [
          {
            table: id,
            tab: 'tab',
            made: { ...OUTLINE, table: id, merges: {}, frozen: null, at: { x: 0, z: 2 } },
          },
        ],
      });
    const operation = { op: 'table', id: 'own', rowIds: ['x', 'y', 'z'], colIds: ['a', 'b'] };
    const { token, answer } = client.do('tab', [operation]);
    made('own', token);
    made('theirs', 'elsewhere');
    socket.receive({ type: 'done', token });
    await answer;
    expect([0, 1, 2].map((place) => client.grid('own')!.rowId(place))).toEqual(['x', 'y', 'z']);
    expect(client.grid('theirs')!.rowId(1)).toBeUndefined();
  });

  it('sends again what was not answered, by the same token, once the socket opens again', async () => {
    const socket = connected();
    const { token, answer } = client.do('tab', [{ op: 'delete', table: 't' }]);
    socket.taken();
    socket.close();
    vi.advanceTimersByTime(500);
    const again = FakeSocket.made.at(-1)!;
    expect(again).not.toBe(socket);
    again.opened();
    expect(again.taken()).toEqual([
      { type: 'watch', tab: 'tab' },
      { type: 'do', token, tab: 'tab', operations: [{ op: 'delete', table: 't' }] },
    ]);
    again.receive({ type: 'done', token });
    await answer;
  });

  it('tries again an edit the server has not caught up with, and fails loudly on a refusal', async () => {
    const socket = connected();
    const behind = client.do('tab', [{ op: 'delete', table: 't' }]);
    socket.taken();
    socket.receive({ type: 'refused', token: behind.token, code: 'behind' });
    vi.advanceTimersByTime(1000);
    expect(socket.taken()).toMatchObject([{ type: 'do', token: behind.token }]);
    socket.receive({ type: 'done', token: behind.token });
    await behind.answer;

    const refused = client.do('tab', [{ op: 'delete', table: 'x' }]);
    socket.receive({ type: 'refused', token: refused.token, code: 'invalid', detail: 'no table' });
    await expect(refused.answer).rejects.toEqual(new Refusal('invalid', 'no table'));
  });

  it('refuses what waits, and what is asked of it, once closed', async () => {
    connected();
    const waiting = client.do('tab', []);
    client.close();
    await expect(waiting.answer).rejects.toEqual(new Refusal('closed', null));
    await expect(client.do('tab', []).answer).rejects.toEqual(new Refusal('closed', null));
  });

  it('asks once whether a table is referred to, again after the socket opens again', async () => {
    const socket = connected();
    const [first, second] = [client.referred('t'), client.referred('t')];
    const asked = { type: 'referred', table: 't' };
    expect(socket.taken()).toEqual([asked]);
    socket.close();
    vi.advanceTimersByTime(500);
    const again = FakeSocket.made.at(-1)!;
    again.opened();
    expect(again.taken()).toEqual([{ type: 'watch', tab: 'tab' }, asked]);
    again.receive({ type: 'referred', table: 't', referred: true });
    expect(await Promise.all([first, second])).toEqual([true, true]);
    await expect(client.referred('x')).rejects.toEqual(new Refusal('no_table', 'x'));
  });

  it('knows the tables of the document by name and by id, and the names in force in a table', () => {
    const socket = connected();
    socket.receive({
      type: 'tables',
      tables: [
        ['t2', 'Cijene', 4, 2, 'tab2'],
        ['t3', 'Ulaz', 1, 1, 'tab3'],
        ['t4', 'Izlaz', 1, 1, 'tab3'],
      ],
    });
    socket.receive({
      type: 'names',
      names: [
        ['Stopa', null],
        ['STOPA', 't'],
        ['Popust', 't2'],
      ],
    });
    expect(client.named('Prices')).toBeNull();
    expect(client.defined('stopa', 't')).toBe('STOPA');
    expect(client.defined('stopa', 't2')).toBe('Stopa');
    expect(client.defined('popust', 't')).toBeNull();
    const named = { table: 't2', name: 'Cijene', rows: 4, cols: 2, tab: 'tab2', only: true };
    expect([client.named('cijene'), client.table('t2'), client.table('t')]).toEqual([
      named,
      named,
      null,
    ]);
    expect(client.table('t3')?.only).toBe(false);
    socket.receive({ type: 'tables', tables: [] });
    expect([client.named('Cijene'), client.table('t2')]).toEqual([null, null]);
  });

  it('asks once where a defined name in force in a table leads', async () => {
    const socket = connected();
    const [first, second] = [client.where('Ukupno', 't'), client.where('UKUPNO', 't')];
    const other = client.where('Ukupno', null);
    expect(socket.taken()).toEqual([
      { type: 'where', name: 'Ukupno', table: 't' },
      { type: 'where', name: 'Ukupno', table: null },
    ]);
    socket.receive({ type: 'where', name: 'Ukupno', table: 't', at: ['t2', 'B2:B9'] });
    socket.receive({ type: 'where', name: 'Ukupno', table: null, at: null });
    const found = { table: 't2', address: 'B2:B9' };
    expect(await Promise.all([first, second, other])).toEqual([found, found, null]);
  });

  it('takes back an edit by its token, after the text it follows', () => {
    const socket = connected();
    const { token, answer } = client.undo('earlier');
    expect(socket.taken()).toEqual([{ type: 'undo', token: 'earlier', as: token }]);
    socket.receive({ type: 'done', token });
    return answer;
  });
});

describe("a grid's patch", () => {
  it('hides columns and shows them again, and forgets a hidden column taken out', () => {
    connected();
    const grid = client.grid('t')!;
    grid.apply({ table: 't', hidden: { cols: { b: true } } });
    expect([...grid.hidden.cols]).toEqual(['b']);
    const change = grid.apply({ table: 't', hidden: { cols: { b: false, a: true } } });
    expect(change.outline).toBe(true);
    expect([...grid.hidden.cols]).toEqual(['a']);
    grid.apply({ table: 't', cols: { out: [0] } });
    expect(grid.hidden.cols.size).toBe(0);
  });

  it('freezes the rows down to the one it names, and frees them', () => {
    const grid = new Grid(OUTLINE, 'tab', new Map());
    expect(grid.frozenRows()).toBe(1);
    const change = grid.apply({ table: 't', frozen: 'r2' });
    expect(change).toEqual({ table: 't', outline: true, rows: null });
    expect(grid.frozenRows()).toBe(2);
    grid.apply({ table: 't', frozen: null });
    expect([grid.frozen, grid.frozenRows()]).toEqual([null, 0]);
  });

  it('takes lines out with their sizes, merges and cells, then reorders and puts lines in', () => {
    const grid = new Grid(OUTLINE, 'tab', new Map());
    grid.held.set('r1', { cells: { a: { text: 'x' } }, values: {} });
    grid.held.set('r2', { cells: {}, values: {} });
    const change = grid.apply({
      table: 't',
      rows: { out: [0], put: [['n', 1, 40, null]] },
      cols: { order: [0, ['b', 'a']], put: [['c', 0, null, null]] },
    });
    expect(change).toEqual({ table: 't', outline: true, rows: null });
    expect([grid.rowCount, [0, 1, 2].map((at) => grid.rowId(at)), grid.cols]).toEqual([
      3,
      ['r2', 'n', 'r3'],
      ['c', 'b', 'a'],
    ]);
    expect([grid.heights.get('n'), grid.heights.get('r2'), grid.merges.size]).toEqual([40, 30, 0]);
    expect([grid.holds('r1'), grid.holds('r2'), grid.rowIndex('n'), grid.colIndex('a')]).toEqual([
      false,
      true,
      1,
      2,
    ]);
  });

  it('moves the rows it knows by where the lines went, as many as there are', () => {
    const at = { r0: 0, r4: 4, r6: 6, r9: 9 };
    const outline = { ...OUTLINE, rows: 10, at, heights: {}, merges: {}, frozen: null };
    const grid = new Grid(outline, 'tab', new Map());
    grid.apply({
      table: 't',
      rows: {
        out: [2, 4],
        order: [3, ['r6', 'x']],
        put: [
          ['n', 0, null, null],
          ['m', 5, null, null],
        ],
      },
    });
    expect(Array.from({ length: 10 }, (_, index) => grid.rowId(index))).toEqual([
      'n',
      'r0',
      undefined,
      undefined,
      'r6',
      'm',
      'x',
      undefined,
      undefined,
      'r9',
    ]);
    expect([grid.rowCount, grid.rowIndex('r4'), grid.rowIndex('x')]).toEqual([10, -1, 6]);
  });

  it('changes only the cells of the rows held, and says which', () => {
    const grid = new Grid(OUTLINE, 'tab', new Map());
    grid.held.set('r1', { cells: { a: { text: 'x' } }, values: {} });
    const change = grid.apply({
      table: 't',
      cells: { r1: { a: null, b: { text: 'y' } }, r3: { a: { text: 'z' } } },
    });
    expect(change).toEqual({ table: 't', outline: false, rows: new Set(['r1']) });
    expect([grid.cell('r1', 'a'), grid.cell('r1', 'b'), grid.cell('r3', 'a')]).toEqual([
      undefined,
      { text: 'y' },
      undefined,
    ]);
  });
});
