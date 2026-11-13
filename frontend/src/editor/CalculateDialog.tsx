import type { Node } from 'prosemirror-model';
import type { EditorView } from 'prosemirror-view';
import {
  ArrowDownToLine,
  ArrowUpToLine,
  Divide,
  Minus,
  Plus,
  Scale,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Cancel, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { button, primaryButton } from '../styles';
import { numberColumn, type Parameters } from './actions';
import { columnOf } from './command';
import { columnName } from './formulas';
import { schema } from './schema';
import { targetOf } from './tablesPlugin';
import type { TableView } from './tableView';

const OPERATIONS = ['sum', 'difference', 'product', 'quotient', 'average', 'min', 'max'] as const;
type Operation = (typeof OPERATIONS)[number];
/** The operations over exactly two columns, in their order. */
const PAIRS: readonly Operation[] = ['difference', 'quotient'];
const ICONS: Record<Operation, LucideIcon> = {
  sum: Plus,
  difference: Minus,
  product: X,
  quotient: Divide,
  average: Scale,
  min: ArrowDownToLine,
  max: ArrowUpToLine,
};
const SIGNS: Partial<Record<Operation, string>> = {
  sum: ' + ',
  difference: ' − ',
  product: ' × ',
  quotient: ' ÷ ',
};

interface Column {
  id: string;
  header: string;
  numbers: boolean;
}

/** The column the cursor is in and the table's other columns, each by the text of its first
 * row, or its letter where that is empty. */
function opening(view: EditorView): { col: string; columns: Column[]; table: TableView } {
  const target = targetOf(view);
  const lines = target?.table.lines;
  if (!target || !lines) throw new Error('The calculated column needs the cursor in a table');
  const col = columnOf(view, target);
  const first = lines.rowId(0);
  const texts = new Map<string, string>();
  view.state.doc.descendants((node: Node) => {
    if (node.type === schema.nodes.table && node.attrs.id === lines.table) {
      node.forEach((cell) => {
        if (cell.attrs.row === first) texts.set(cell.attrs.col, cell.textContent);
      });
      return false;
    }
    return node.type !== schema.nodes.table;
  });
  const header = (id: string, index: number): string =>
    (texts.get(id) ?? (first === undefined ? '' : lines.cell(first, id)?.text) ?? '').trim() ||
    columnName(index);
  const columns = lines.cols.map((id, index) => ({
    id,
    header: header(id, index),
    numbers: numberColumn(lines, id),
  }));
  return { col, columns, table: target.table };
}

function numbered(table: TableView): Set<string> {
  const lines = table.lines;
  return new Set(lines ? lines.cols.filter((id) => numberColumn(lines, id)) : []);
}

/** Asks which operation the column the cursor is in holds over which other columns, and shows
 * the formula in the headers' words as they are picked. */
export function CalculateDialog({
  view,
  onCalculate,
  onClose,
}: {
  view: EditorView;
  onCalculate: (parameters: Parameters) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [start] = useState(() => opening(view));
  const [operation, setOperation] = useState<Operation>('product');
  const [columns, setColumns] = useState<string[]>([]);
  // A cell just written has no value until the server answers, so which columns hold numbers is
  // read again as the answers come.
  const [numbers, setNumbers] = useState(() => numbered(start.table));
  useEffect(() => {
    const { table } = start;
    return table.spec.grids.subscribe(table.lines!.table, () => setNumbers(numbered(table)));
  }, [start]);
  const own = start.columns.find((each) => each.id === start.col)!;
  const others = start.columns
    .filter((each) => each.id !== start.col)
    .map((each) => ({ ...each, numbers: numbers.has(each.id) }));
  const pair = PAIRS.includes(operation);
  const ready = pair ? columns.length === 2 : columns.length >= 2;
  const label = (each: Operation): MessageKey => `action.tableCalculate.${each}`;
  const headerOf = (id: string) => others.find((each) => each.id === id)!.header;
  const sign = SIGNS[operation];
  const formula = sign
    ? columns.map(headerOf).join(sign)
    : `${t(label(operation))}(${columns.map(headerOf).join(', ')})`;

  function toggle(id: string) {
    setColumns((picked) =>
      picked.includes(id) ? picked.filter((each) => each !== id) : [...picked, id],
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    onCalculate({ operation, columns });
    onClose();
  }

  return (
    <Modal heading={t('action.tableCalculate')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <p className="text-sm">
          <span className="font-semibold">{own.header}</span>
          {' = '}
          {columns.length ? formula : <span className="text-muted">{t('calculate.pick')}</span>}
        </p>
        <div role="group" aria-label={t('calculate.operation')} className="flex flex-wrap gap-1">
          {OPERATIONS.map((each) => {
            const Icon = ICONS[each];
            return (
              <button
                key={each}
                type="button"
                aria-pressed={each === operation}
                onClick={() => setOperation(each)}
                className={`${button} aria-pressed:bg-selected`}
              >
                <Icon size={16} aria-hidden />
                {t(label(each))}
              </button>
            );
          })}
        </div>
        <div role="group" aria-label={t('calculate.columns')} className="flex flex-wrap gap-1">
          {others.map((each) => {
            const at = columns.indexOf(each.id);
            return (
              <button
                key={each.id}
                type="button"
                aria-pressed={at >= 0}
                disabled={!each.numbers || (pair && at < 0 && columns.length >= 2)}
                onClick={() => toggle(each.id)}
                className={`${button} aria-pressed:bg-selected`}
              >
                {pair && at >= 0 && <span className="text-muted">{at + 1}.</span>}
                {each.header}
              </button>
            );
          })}
        </div>
        <p className="text-sm text-muted">{t(pair ? 'calculate.pairNote' : 'calculate.note')}</p>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={!ready} className={primaryButton}>
            {t('calculate.run')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
