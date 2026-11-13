import type { EChartsCoreOption, EChartsType } from 'echarts/core';
import type { Node } from 'prosemirror-model';
import { NodeSelection, type EditorState } from 'prosemirror-state';
import type { EditorView, NodeView } from 'prosemirror-view';
import * as Y from 'yjs';
import type { MessageKey } from '../i18n/hr';
import { chartLook, onScheme, type ChartLook } from '../theme';
import type { DocumentLocale } from '../tree';
import { chartAttrs, chartOf, schema, type Chart, type ChartKind, type ChartRange } from './schema';
import { chartsOf, type Drawn, type Undrawn } from './tab';
import { rowAt, type Lines, type Rect } from './tables';

const { chart: chartType, table: tableType, paragraph: paragraphType } = schema.nodes;

/** Office's chart, five by three. */
const ASPECT = 5 / 3;
const BAR_WIDTH = 24;
const TALL = 10_000;
const MARGIN = ['5%', '5%'];

type Label = (key: MessageKey) => string;

export const CHART_LABELS: Record<ChartKind, MessageKey> = {
  column: 'chart.column',
  bar: 'chart.bar',
  line: 'chart.line',
  area: 'chart.area',
  pie: 'chart.pie',
  doughnut: 'chart.doughnut',
  scatter: 'chart.scatter',
};

export function selectedChart(state: EditorState): { node: Node; pos: number } | null {
  const { selection } = state;
  return selection instanceof NodeSelection && selection.node.type === chartType
    ? { node: selection.node, pos: selection.from }
    : null;
}

/** Where a range lies in the table, null where a line of it is gone or the browser does not
 * know where its row stands. */
export function rectOf(range: ChartRange, lines: Lines): Rect | null {
  const ends = [
    lines.rowIndex(range.from.row),
    lines.colIndex(range.from.col),
    lines.rowIndex(range.to.row),
    lines.colIndex(range.to.col),
  ];
  if (ends.some((end) => end < 0)) return null;
  const [top, left, bottom, right] = ends;
  return {
    top: Math.min(top, bottom),
    left: Math.min(left, right),
    bottom: Math.max(top, bottom),
    right: Math.max(left, right),
  };
}

/** The range over the rect, whose corner rows the browser knows. */
export function rangeOf(table: string, lines: Lines, rect: Rect): ChartRange {
  return {
    table,
    from: { row: rowAt(lines, rect.top), col: lines.cols[rect.left] },
    to: { row: rowAt(lines, rect.bottom), col: lines.cols[rect.right] },
  };
}

/** Which way a range's series run unless one says otherwise: down the columns, as Excel takes
 * them, unless the range is wider than it is tall. */
export function seriesWay(rect: Rect): 'rows' | 'cols' {
  return rect.right - rect.left > rect.bottom - rect.top ? 'rows' : 'cols';
}

/** Puts a new chart after its table, or in place of the selection, and selects it. */
export function insertChart(view: EditorView, chart: Chart, afterTable: boolean): void {
  const { state } = view;
  const node = chartType.create(chartAttrs(chart));
  let after: number | null = null;
  if (afterTable) {
    state.doc.forEach((child, offset) => {
      if (child.type === tableType && child.attrs.id === chart.range?.table) {
        after = offset + child.nodeSize;
      }
    });
  }
  const tr = after === null ? state.tr.replaceSelectionWith(node) : state.tr.insert(after, node);
  if (!tr.doc.lastChild!.isTextblock) tr.insert(tr.doc.content.size, paragraphType.create());
  tr.doc.forEach((child, offset) => {
    if (child === node) tr.setSelection(NodeSelection.create(tr.doc, offset));
  });
  view.dispatch(tr.scrollIntoView());
}

export function updateChart(view: EditorView, pos: number, chart: Chart): void {
  const node = view.state.doc.nodeAt(pos);
  if (node?.type !== chartType) return;
  const tr = view.state.tr.setNodeMarkup(pos, null, { ...chartAttrs(chart), id: node.attrs.id });
  view.dispatch(tr.setSelection(NodeSelection.create(tr.doc, pos)));
}

function numbers(locale: DocumentLocale) {
  const plain = new Intl.NumberFormat(locale, { maximumFractionDigits: 2 });
  const compact = new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 });
  return (value: number) => (Math.abs(value) >= TALL ? compact : plain).format(value);
}

interface Hovered {
  seriesIndex: number;
  dataIndex: number;
  color: string;
  name: string;
  data: unknown;
}

/** The cell a hovered mark stands for: a pie's slices and a scatter's points skip the cells
 * that hold no number, so they carry its index. */
function indexOf(hovered: Hovered): number {
  const { data } = hovered;
  if (Array.isArray(data)) return Number(data[2]);
  if (typeof data === 'object' && data !== null && 'index' in data) return Number(data.index);
  return hovered.dataIndex;
}

function line(color: string): HTMLElement {
  const key = document.createElement('span');
  key.style.cssText = `display:inline-block;width:12px;height:2px;margin-inline-end:6px;vertical-align:middle;background:${color}`;
  return key;
}

function row(color: string, value: string, name: string, look: ChartLook): HTMLElement {
  const shown = document.createElement('div');
  const strong = document.createElement('strong');
  strong.textContent = value;
  const quiet = document.createElement('span');
  quiet.textContent = ` ${name}`;
  quiet.style.color = look.muted;
  shown.append(line(color), strong, quiet);
  return shown;
}

/** What ECharts draws for a chart: its series in the theme's colours, its text in the
 * document's font, each value in a tooltip as its cell shows it. */
export function chartOption(
  chart: Chart,
  drawn: Drawn,
  look: ChartLook,
  t: Label,
  locale: DocumentLocale,
): EChartsCoreOption {
  const { kind, stacked } = chart;
  const count = Math.max(0, ...drawn.series.map((each) => each.values.length));
  const names = drawn.series.map((each, index) => each.name || `${t('chart.series')} ${index + 1}`);
  const format = numbers(locale);
  const labels = drawn.labels ?? Array.from({ length: count }, (_, index) => format(index + 1));
  const textOf = (series: number, index: number) => drawn.series[series]?.texts[index] ?? '';
  const round = kind === 'pie' || kind === 'doughnut';
  const tooltip = {
    trigger: kind === 'line' || kind === 'area' ? 'axis' : 'item',
    confine: true,
    backgroundColor: look.raised,
    borderColor: look.line,
    textStyle: { color: look.ink, fontFamily: look.font },
    axisPointer: { type: 'line', lineStyle: { color: look.muted, width: 1 } },
    formatter: (given: Hovered | Hovered[]) => {
      const hovered = Array.isArray(given) ? given : [given];
      const box = document.createElement('div');
      const first = hovered[0];
      if (!first) return box;
      if (round) {
        box.append(row(first.color, textOf(first.seriesIndex, indexOf(first)), first.name, look));
        return box;
      }
      const heading = document.createElement('div');
      heading.textContent = labels[indexOf(first)] ?? '';
      box.append(heading);
      for (const each of hovered) {
        const value = textOf(each.seriesIndex, indexOf(each));
        box.append(row(each.color, value, names[each.seriesIndex], look));
      }
      return box;
    },
  };
  const base = {
    animation: false,
    color: look.colors,
    textStyle: { fontFamily: look.font, color: look.ink },
    title: {
      show: Boolean(chart.title),
      text: chart.title,
      left: 'center',
      textStyle: { color: look.ink, fontFamily: look.font, fontSize: 15, fontWeight: 600 },
    },
    legend: {
      show: chart.legend,
      bottom: 0,
      icon: kind === 'line' || kind === 'scatter' ? undefined : 'roundRect',
      itemWidth: 14,
      itemHeight: kind === 'line' ? 2 : 10,
      textStyle: { color: look.ink, fontFamily: look.font },
      inactiveColor: look.line,
    },
    tooltip,
  };
  const top = chart.title ? 40 : 12;
  const bottom = chart.legend ? 36 : 8;
  if (round) {
    const shown = kind === 'pie' ? drawn.series.slice(0, 1) : drawn.series;
    const inner = kind === 'pie' ? 0 : 35;
    const outer = 70;
    const width = (outer - inner) / Math.max(1, shown.length);
    return {
      ...base,
      series: shown.map((each, series) => ({
        type: 'pie',
        name: names[series],
        center: ['50%', `${50 + (top - bottom) / 8}%`],
        radius: [`${inner + width * series}%`, `${inner + width * (series + 1)}%`],
        itemStyle: { borderColor: look.surface, borderWidth: 2 },
        label: { show: series === shown.length - 1, color: look.ink, fontFamily: look.font },
        labelLine: { lineStyle: { color: look.muted } },
        data: each.values.flatMap((value, index) =>
          value === null ? [] : [{ name: labels[index], value, index }],
        ),
      })),
    };
  }
  const axis = {
    axisLine: { lineStyle: { color: look.line } },
    axisTick: { show: false },
    axisLabel: { color: look.muted, fontFamily: look.font },
    splitLine: { lineStyle: { color: look.line, width: 1, type: 'solid' } },
  };
  const valued = { ...axis, type: 'value', axisLabel: { ...axis.axisLabel, formatter: format } };
  const grid = {
    left: 8,
    right: 16,
    top,
    bottom,
    outerBoundsMode: 'same',
    outerBoundsContain: 'axisLabel',
  };
  if (kind === 'scatter') {
    const xs = drawn.x ?? Array.from({ length: count }, (_, index) => index + 1);
    return {
      ...base,
      grid,
      xAxis: {
        ...valued,
        scale: true,
        boundaryGap: MARGIN,
        splitLine: { show: false },
        ...(drawn.x ? {} : { minInterval: 1 }),
      },
      yAxis: { ...valued, scale: true, boundaryGap: MARGIN },
      series: drawn.series.map((each, series) => ({
        type: 'scatter',
        name: names[series],
        symbolSize: 8,
        itemStyle: { borderColor: look.surface, borderWidth: 2 },
        data: each.values.flatMap((value, index) =>
          value === null || xs[index] === null ? [] : [[xs[index], value, index]],
        ),
      })),
    };
  }
  const categories = { ...axis, type: 'category', data: labels, splitLine: { show: false } };
  const flat = kind === 'bar';
  return {
    ...base,
    grid,
    xAxis: flat ? valued : { ...categories, boundaryGap: kind === 'column' },
    yAxis: flat ? { ...categories, inverse: true } : valued,
    series: drawn.series.map((each, series) => {
      const common = {
        name: names[series],
        data: each.values,
        ...(stacked ? { stack: 'total' } : {}),
      };
      if (kind === 'column' || kind === 'bar') {
        return {
          ...common,
          type: 'bar',
          barMaxWidth: BAR_WIDTH,
          itemStyle: stacked
            ? { borderColor: look.surface, borderWidth: 2 }
            : { borderRadius: flat ? [0, 4, 4, 0] : [4, 4, 0, 0] },
        };
      }
      return {
        ...common,
        type: 'line',
        lineStyle: { width: 2, cap: 'round', join: 'round' },
        symbolSize: 8,
        showSymbol: kind === 'line',
        itemStyle: { borderColor: look.surface, borderWidth: 2 },
        ...(kind === 'area' ? { areaStyle: { opacity: stacked ? 0.6 : 0.1 } } : {}),
      };
    }),
  };
}

let loading: Promise<typeof import('./echarts')> | null = null;

function echarts() {
  loading ??= import('./echarts');
  return loading;
}

/** A chart in the editor: drawn from what the server computed for it, again as that or the
 * theme changes, and sized to the column at Office's proportions. */
export class ChartView implements NodeView {
  readonly dom = document.createElement('figure');
  private readonly plot = document.createElement('div');
  private readonly note = document.createElement('p');
  private drawn: EChartsType | null = null;
  private destroyed = false;
  private readonly sized = new ResizeObserver(() => this.drawn?.resize());
  private unscheme = () => {};
  private readonly redraw = () => void this.render();
  private readonly observed = (event: Y.YMapEvent<Drawn | Undrawn>) => {
    if (event.keysChanged.has(this.node.attrs.id)) void this.render();
  };

  constructor(
    private node: Node,
    private readonly doc: Y.Doc,
    private readonly options: {
      label: () => Label;
      locale: () => DocumentLocale;
      edit?: () => void;
    },
  ) {
    this.dom.className = 'ponistra-chart';
    this.dom.contentEditable = 'false';
    this.dom.setAttribute('role', 'img');
    this.plot.className = 'ponistra-chart-plot';
    this.plot.style.aspectRatio = String(ASPECT);
    this.note.className = 'ponistra-chart-note';
    this.dom.append(this.plot, this.note);
    if (options.edit) this.dom.addEventListener('dblclick', options.edit);
    chartsOf(doc).observe(this.observed);
    this.unscheme = onScheme(this.redraw);
    this.sized.observe(this.plot);
    void this.render();
  }

  update(node: Node): boolean {
    if (node.type !== this.node.type) return false;
    const changed = node.attrs !== this.node.attrs;
    this.node = node;
    if (changed) void this.render();
    return true;
  }

  ignoreMutation(): boolean {
    return true;
  }

  stopEvent(event: Event): boolean {
    return event.type === 'dblclick';
  }

  private async render() {
    const t = this.options.label();
    const chart = chartOf(this.node.attrs);
    const shown = chartsOf(this.doc).get(this.node.attrs.id);
    this.dom.dataset.chart = chart.kind;
    this.dom.setAttribute('aria-label', chart.title || t(CHART_LABELS[chart.kind]));
    const problem =
      shown && 'missing' in shown
        ? 'chart.missing'
        : shown && 'failed' in shown
          ? 'chart.failed'
          : shown && !shown.series.length
            ? 'chart.empty'
            : null;
    this.note.textContent = problem ? t(problem) : '';
    this.note.hidden = !problem;
    this.plot.hidden = Boolean(problem);
    if (problem) {
      this.drawn?.dispose();
      this.drawn = null;
      return;
    }
    if (!shown || !('series' in shown)) return;
    const { init } = await echarts();
    if (this.destroyed) return;
    this.drawn ??= init(this.plot, null, { renderer: 'svg' });
    const look = chartLook(this.dom);
    this.drawn.setOption(chartOption(chart, shown, look, t, this.options.locale()), true);
  }

  destroy() {
    this.destroyed = true;
    chartsOf(this.doc).unobserve(this.observed);
    this.unscheme();
    this.sized.disconnect();
    this.drawn?.dispose();
  }
}
