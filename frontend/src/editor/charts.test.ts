// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { ChartLook } from '../theme';
import { chartOption, rangeOf, rectOf, seriesWay } from './charts';
import { chartAttrs, chartOf, schema } from './schema';
import type { Drawn } from './tab';
import { partLines, type Lines } from './tables';

const LOOK: ChartLook = {
  colors: ['first', 'second'],
  ink: 'ink',
  muted: 'muted',
  line: 'line',
  surface: 'surface',
  raised: 'raised',
  font: 'Inter',
};
const DRAWN: Drawn = {
  series: [
    { name: 'Prihod', values: [1, null, 3], texts: ['1,00', 'x', '3,00'] },
    { name: null, values: [4, 5, 6], texts: ['4', '5', '6'] },
  ],
  labels: ['Sij', 'Velj', 'Ožu'],
};

function lines(rows: string[], cols: string[] = ['a', 'b', 'c']): Lines {
  return partLines(schema.nodes.table.create({ grid: { rows, cols } }))!;
}

function option(attrs: Record<string, unknown>, drawn: Drawn = DRAWN) {
  return chartOption(chartOf(attrs), drawn, LOOK, (key) => key, 'hr') as Record<string, any>;
}

describe('chartOf', () => {
  it('keeps what is valid and takes the defaults for the rest', () => {
    const range = { table: 't', from: { row: 'r1', col: 'a' }, to: { row: 'r3', col: 'c' } };
    expect(chartOf({ range, kind: 'pie', stacked: true, by: 'rows', names: false })).toEqual({
      range,
      kind: 'pie',
      stacked: false,
      by: 'rows',
      names: false,
      labels: null,
      title: '',
      legend: true,
    });
    expect(chartOf({ range: { table: 't' }, kind: 'radar', title: 7 })).toMatchObject({
      range: null,
      kind: 'column',
      title: '',
    });
    expect(chartAttrs(chartOf({ title: '  ' })).title).toBeNull();
  });
});

describe('a chart range', () => {
  it('lies where its lines are and is gone with one of them', () => {
    const range = rangeOf('t', lines(['r1', 'r2', 'r3']), { top: 0, left: 1, bottom: 2, right: 2 });
    expect(range).toEqual({
      table: 't',
      from: { row: 'r1', col: 'b' },
      to: { row: 'r3', col: 'c' },
    });
    expect(rectOf(range, lines(['r3', 'r2', 'r1']))).toEqual({
      top: 0,
      left: 1,
      bottom: 2,
      right: 2,
    });
    expect(rectOf(range, lines(['r1', 'r2', 'r3'], ['a', 'b']))).toBeNull();
  });

  it('runs its series down the columns unless it is wider than tall', () => {
    expect(seriesWay({ top: 0, left: 0, bottom: 4, right: 2 })).toBe('cols');
    expect(seriesWay({ top: 0, left: 0, bottom: 1, right: 5 })).toBe('rows');
  });
});

describe('chartOption', () => {
  it('draws columns over the categories, a series without a name numbered', () => {
    const drawn = option({ kind: 'column', stacked: true, title: 'Prihodi' });
    expect(drawn.xAxis.data).toEqual(['Sij', 'Velj', 'Ožu']);
    expect(drawn.yAxis.type).toBe('value');
    expect(drawn.series.map((each: any) => [each.type, each.name, each.stack])).toEqual([
      ['bar', 'Prihod', 'total'],
      ['bar', 'chart.series 2', 'total'],
    ]);
    expect(drawn.series[0].data).toEqual([1, null, 3]);
    expect(drawn.title).toMatchObject({ show: true, text: 'Prihodi' });
    expect(drawn.color).toEqual(['first', 'second']);
  });

  it('lays bars on their side, the first category on top', () => {
    const drawn = option({ kind: 'bar' });
    expect(drawn.xAxis.type).toBe('value');
    expect(drawn.yAxis).toMatchObject({ type: 'category', inverse: true });
    expect(drawn.series[0].stack).toBeUndefined();
  });

  it('draws a pie of the first series and a doughnut of each as a ring', () => {
    const pie = option({ kind: 'pie' });
    expect(pie.series).toHaveLength(1);
    expect(pie.series[0].data).toEqual([
      { name: 'Sij', value: 1, index: 0 },
      { name: 'Ožu', value: 3, index: 2 },
    ]);
    const doughnut = option({ kind: 'doughnut' });
    expect(doughnut.series.map((each: any) => each.radius)).toEqual([
      ['35%', '52.5%'],
      ['52.5%', '70%'],
    ]);
  });

  it('places a scatter at its x values, numbering the points without them', () => {
    const drawn = option({ kind: 'scatter' }, { ...DRAWN, x: [10, 20, null] });
    expect(drawn.series[0].data).toEqual([[10, 1, 0]]);
    expect(drawn.series[1].data).toEqual([
      [10, 4, 0],
      [20, 5, 1],
    ]);
    const numbered = option({ kind: 'scatter' }, { ...DRAWN, labels: null });
    expect(numbered.series[1].data.map((point: number[]) => point[0])).toEqual([1, 2, 3]);
  });

  it('shows the values in a tooltip as their cells show them', () => {
    const drawn = option({ kind: 'line' });
    const shown: HTMLElement = drawn.tooltip.formatter([
      { seriesIndex: 0, dataIndex: 1, color: 'first', name: 'Velj', data: null },
    ]);
    expect(shown.textContent).toBe('Veljx Prihod');
  });
});
