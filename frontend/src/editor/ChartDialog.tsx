import type { Node } from 'prosemirror-model';
import type { EditorView } from 'prosemirror-view';
import {
  ChartArea,
  ChartBar,
  ChartColumn,
  ChartLine,
  ChartPie,
  ChartScatter,
  Donut,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Cancel, Labelled, Modal, Picker } from '../dialogs';
import { useI18n } from '../i18n';
import { button, field, primaryButton } from '../styles';
import { CHART_LABELS, insertChart, rectOf, selectedChart, seriesWay, updateChart } from './charts';
import { addressOf, rectOfAddress } from './formulas';
import {
  CHART_KINDS,
  CHART_TITLE_LENGTH,
  STACKING,
  chartOf,
  schema,
  type Chart,
  type ChartKind,
} from './schema';
import type { Grid, GridSource } from './grids';
import type { Rect } from './tables';
import { targetOf } from './tablesPlugin';

const ICONS: Record<ChartKind, LucideIcon> = {
  column: ChartColumn,
  bar: ChartBar,
  line: ChartLine,
  area: ChartArea,
  pie: ChartPie,
  doughnut: Donut,
  scatter: ChartScatter,
};

type Header = 'auto' | 'yes' | 'no';

interface Table {
  id: string;
  number: number;
  name: string;
  grid: Grid;
  pos: number;
}

function tablesIn(view: EditorView, grids: GridSource): Table[] {
  const found: Table[] = [];
  view.state.doc.forEach((node: Node, pos) => {
    const grid = node.type === schema.nodes.table ? grids.grid(node.attrs.id) : undefined;
    if (!grid) return;
    found.push({ id: grid.table, number: found.length + 1, name: grid.name, grid, pos });
  });
  return found;
}

function whole(grid: Grid): Rect {
  return { top: 0, left: 0, bottom: grid.rowCount - 1, right: grid.cols.length - 1 };
}

/** The address of the rect laid out in the grid, by its rows' own places. */
function shownAddress(rect: Rect, grid: Grid): string {
  const top = grid.rowNumber(rect.top);
  const bottom = grid.rowNumber(rect.bottom);
  return top === undefined || bottom === undefined ? '' : addressOf({ ...rect, top, bottom });
}

/** What the dialog starts from: the selected chart, to be edited; or a new one over the selected
 * cells or the table the cursor is in, put after it, or over the nearest table before the
 * cursor, put where the cursor is. `writing` is the view the cursor is in, a cell's own. */
function opening(view: EditorView, writing: EditorView, tables: Table[]) {
  const picked = selectedChart(view.state);
  if (picked) {
    const chart = chartOf(picked.node.attrs);
    const table = tables.find(({ id }) => id === chart.range?.table);
    const rect = table && chart.range && rectOf(chart.range, table.grid);
    return { pos: picked.pos, after: false, chart, table: table?.id ?? '', rect: rect ?? null };
  }
  const target = targetOf(writing);
  const at = view.state.selection.from;
  const table = target
    ? tables.find(({ id }) => id === target.table.node.attrs.id)
    : (tables.findLast(({ pos }) => pos < at) ?? tables[0]);
  const rect = table && (target?.range ? target.rect : whole(table.grid));
  const chart = chartOf({ by: rect ? seriesWay(rect) : 'cols' });
  return { pos: null, after: Boolean(target), chart, table: table?.id ?? '', rect: rect ?? null };
}

function header(value: boolean | null): Header {
  return value === null ? 'auto' : value ? 'yes' : 'no';
}

function flag(value: Header): boolean | null {
  return value === 'auto' ? null : value === 'yes';
}

export function ChartDialog({
  view,
  writing,
  grids,
  onClose,
}: {
  view: EditorView;
  writing: EditorView;
  grids: GridSource;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const [tables] = useState(() => tablesIn(view, grids));
  const [start] = useState(() => opening(view, writing, tables));
  const [kind, setKind] = useState(start.chart.kind);
  const [stacked, setStacked] = useState(start.chart.stacked);
  const [by, setBy] = useState(start.chart.by);
  const [names, setNames] = useState(header(start.chart.names));
  const [labels, setLabels] = useState(header(start.chart.labels));
  const [title, setTitle] = useState(start.chart.title);
  const [legend, setLegend] = useState(start.chart.legend);
  const [table, setTable] = useState(start.table);
  const [address, setAddress] = useState(() => {
    const grid = tables.find(({ id }) => id === start.table)?.grid;
    return start.rect && grid ? shownAddress(start.rect, grid) : '';
  });
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    const range = start.chart.range;
    const picked = tables.find(({ id }) => id === start.table);
    if (start.rect || !range || !picked) return;
    let open = true;
    void grids.rowPlaces(picked.id, [range.from.row, range.to.row]).then(() => {
      const rect = rectOf(range, picked.grid);
      if (open && rect) setAddress(shownAddress(rect, picked.grid));
    });
    return () => {
      open = false;
    };
  }, [grids, start, tables]);
  const grid = tables.find(({ id }) => id === table)?.grid;
  const rect = rectOfAddress(address);
  const fits =
    grid && rect && (!grid.plain || rect.bottom < grid.rowCount) && rect.right < grid.cols.length;
  const problem = !tables.length ? 'chart.noTables' : !fits || missing ? 'chart.badRange' : null;
  const across = by === 'cols' ? 'chart.firstColumn' : 'chart.firstRow';
  const along = by === 'cols' ? 'chart.firstRow' : 'chart.firstColumn';

  function pickTable(id: string) {
    setTable(id);
    const picked = tables.find((each) => each.id === id);
    if (picked) setAddress(shownAddress(whole(picked.grid), picked.grid));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (problem || !grid || !rect) return;
    const [from, to] = await grids.numberedRows(table, [rect.top, rect.bottom]);
    if (from === null || to === null) return setMissing(true);
    const chart: Chart = {
      range: {
        table,
        from: { row: from, col: grid.cols[rect.left] },
        to: { row: to, col: grid.cols[rect.right] },
      },
      kind,
      stacked: STACKING.includes(kind) && stacked,
      by,
      names: flag(names),
      labels: flag(labels),
      title: title.trim(),
      legend,
    };
    if (start.pos !== null) updateChart(view, start.pos, chart);
    else insertChart(view, chart, start.after);
    onClose();
  }

  return (
    <Modal heading={t(start.pos === null ? 'chart.insert' : 'chart.edit')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div role="group" aria-label={t('chart.kind')} className="flex flex-wrap gap-1">
          {CHART_KINDS.map((each) => {
            const Icon = ICONS[each];
            return (
              <button
                key={each}
                type="button"
                aria-pressed={each === kind}
                title={t(CHART_LABELS[each])}
                onClick={() => setKind(each)}
                className={`${button} aria-pressed:bg-selected`}
              >
                <Icon size={16} aria-hidden />
                {t(CHART_LABELS[each])}
              </button>
            );
          })}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Picker
            label={t('chart.table')}
            value={table}
            options={tables.map(({ id, number, name }) => [
              id,
              name || `${t('search.table')} ${formatNumber(number)}`,
            ])}
            onChange={pickTable}
          />
          <Labelled label={t('chart.range')}>
            {(id) => (
              <input
                id={id}
                autoComplete="off"
                spellCheck={false}
                value={address}
                onChange={(event) => {
                  setAddress(event.target.value);
                  setMissing(false);
                }}
                aria-invalid={problem === 'chart.badRange'}
                className={field}
              />
            )}
          </Labelled>
          <Picker
            label={t('chart.seriesIn')}
            value={by}
            options={[
              ['cols', t('chart.byColumns')],
              ['rows', t('chart.byRows')],
            ]}
            onChange={setBy}
          />
          <div />
          <Picker
            label={t('chart.names')}
            value={names}
            options={[
              ['auto', t('chart.automatic')],
              ['yes', t(along)],
              ['no', t('chart.none')],
            ]}
            onChange={setNames}
          />
          <Picker
            label={t(kind === 'scatter' ? 'chart.xValues' : 'chart.labels')}
            value={labels}
            options={[
              ['auto', t('chart.automatic')],
              ['yes', t(across)],
              ['no', t('chart.none')],
            ]}
            onChange={setLabels}
          />
        </div>
        <Labelled label={t('chart.title')}>
          {(id) => (
            <input
              id={id}
              autoComplete="off"
              maxLength={CHART_TITLE_LENGTH}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={STACKING.includes(kind) && stacked}
              disabled={!STACKING.includes(kind)}
              onChange={(event) => setStacked(event.target.checked)}
            />
            {t('chart.stacked')}
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={legend}
              onChange={(event) => setLegend(event.target.checked)}
            />
            {t('chart.legend')}
          </label>
        </div>
        <p className={`text-sm ${problem ? 'text-danger' : 'text-muted'}`}>
          {t(problem ?? 'chart.hint')}
        </p>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={problem !== null} className={primaryButton}>
            {t(start.pos === null ? 'chart.insertButton' : 'tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
