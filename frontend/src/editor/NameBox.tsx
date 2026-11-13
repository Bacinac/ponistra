import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Cancel, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { cellQuery } from '../tabs';
import { field, primaryButton, smallField } from '../styles';
import type { Context } from './command';
import { refocus } from './commands';
import { addressOf, placeText, pointedAt, rectOfAddress } from './formulas';
import { cellOf, tableIn } from './tableBase';
import type { TableView } from './tableView';
import { targetOf, type Target } from './tablesPlugin';
import type { Rect } from './tables';

const PROBLEMS = { unknown: 'nameBox.unknown', outside: 'nameBox.outside' } as const;

type Problem = keyof typeof PROBLEMS;

/** Where what the name box was given leads: the tab and the query of the cells' address. */
export type Going = { tab: string; query: string } | { problem: Problem };

/** The selected cells: a cell written in by its own, however many it spans, else the cells
 * chosen, else the whole table chosen; `cells` where it is not the table. */
function selectedOf(context: Context): { target: Target; rect: Rect; cells: boolean } | null {
  const target = targetOf(context.view);
  if (!target) return null;
  const one = !target.range && cellOf(context.view) !== null;
  const cells = one || target.range;
  const laid = one
    ? { ...target.rect, bottom: target.rect.top, right: target.rect.left }
    : target.rect;
  return { target, rect: target.table.numbered(laid) ?? laid, cells };
}

function shownOf(context: Context): string {
  const selected = selectedOf(context);
  return selected ? placeText(selected.target.table.lines?.name || null, selected.rect) : '';
}

/** The query of the address of cells of a table of the tab the editor shows. */
function queryIn(here: TableView, table: string, name: string | null, rect: Rect): string {
  const first = tableIn(here.outer.state.doc, here.spec.grids, null, null) === table;
  return cellQuery(addressOf(rect), { id: table, name, first });
}

/** The query that leads to the selected cells, null where no cells are selected. */
export function selectedQuery(context: Context): string | null {
  const selected = selectedOf(context);
  if (!selected?.cells) return null;
  const { table } = selected.target;
  return queryIn(table, table.node.attrs.id, table.lines?.name || null, selected.rect);
}

/** Where the address, the table's name and address, or the defined name written leads from the
 * table of `target`, in the tab `tab` is. */
export async function goingTo(target: Target, tab: string | null, written: string): Promise<Going> {
  const here = target.table;
  const { grids } = here.spec;
  const own = here.node.attrs.id as string;
  const pointed = pointedAt(written);
  if (!pointed || tab === null) return { problem: 'unknown' };
  let table = own;
  let rect: Rect | null = null;
  if ('name' in pointed) {
    const where = await grids.where(pointed.name, own);
    if (!where) return { problem: 'unknown' };
    [table, rect] = [where.table, rectOfAddress(where.address)];
  } else if (pointed.table !== null) {
    const named = grids.named(pointed.table);
    if (!named) return { problem: 'unknown' };
    [table, rect] = [named.table, pointed.rect];
  } else rect = pointed.rect;
  const found = grids.table(table);
  const size = table === own ? here.layout : found;
  if (!rect || !size) return { problem: 'unknown' };
  const plain = (table === own ? here.lines : grids.grid(table))?.plain ?? true;
  if ((plain && rect.bottom >= size.rows) || rect.right >= size.cols) return { problem: 'outside' };
  const name = (table === own ? here.lines?.name : found?.name) || null;
  if (table === own || found?.tab === tab) return { tab, query: queryIn(here, table, name, rect) };
  if (!found?.tab) return { problem: 'unknown' };
  const query = cellQuery(addressOf(rect), { id: table, name, first: found.only });
  return { tab: found.tab, query };
}

/** Leads to what the name box was given, or tells why it cannot. */
function useGoing(context: Context) {
  const [problem, setProblem] = useState<Problem | null>(null);
  async function go(target: Target | null, written: string): Promise<boolean> {
    const going = target ? await goingTo(target, context.place.tab, written) : null;
    const done = going !== null && 'tab' in going && context.visitTab(going.tab, going.query);
    setProblem(done ? null : going && 'problem' in going ? going.problem : 'unknown');
    return done;
  }
  return { problem, setProblem, go };
}

let box: HTMLInputElement | null = null;

/** The name box focused where the toolbar shows it; false where the toolbar has no room for it. */
export function focusNameBox(): boolean {
  if (!box?.checkVisibility({ visibilityProperty: true })) return false;
  box.focus();
  return true;
}

export function NameBox({ context }: { context: Context }) {
  const { t } = useI18n();
  const shown = shownOf(context);
  const [text, setText] = useState<string | null>(null);
  const target = useRef<Target | null>(null);
  const { problem, setProblem, go } = useGoing(context);

  function reset() {
    setText(null);
    setProblem(null);
  }

  function key(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      event.preventDefault();
      reset();
      refocus(context);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      go(target.current, event.currentTarget.value).then(
        (done) => done && setText(null),
        context.fail,
      );
    }
  }

  return (
    <div className="relative">
      <input
        ref={(element) => {
          box = element;
          return () => {
            if (box === element) box = null;
          };
        }}
        aria-label={t('nameBox.label')}
        title={t('nameBox.hint')}
        autoComplete="off"
        spellCheck={false}
        value={text ?? shown}
        onFocus={(event) => {
          target.current = targetOf(context.view);
          setText(shown);
          event.currentTarget.select();
        }}
        onBlur={reset}
        onChange={(event) => {
          setText(event.target.value);
          setProblem(null);
        }}
        onKeyDown={key}
        aria-invalid={problem !== null}
        aria-describedby={problem ? 'name-box-problem' : undefined}
        className={`${smallField} w-36`}
      />
      {problem && (
        <p
          id="name-box-problem"
          role="alert"
          className="absolute top-full left-0 z-50 mt-1 w-max max-w-72 rounded border border-line bg-raised px-2 py-1 text-sm text-danger shadow-lg"
        >
          {t(PROBLEMS[problem])}
        </p>
      )}
    </div>
  );
}

export function GoToDialog({ context, onClose }: { context: Context; onClose: () => void }) {
  const { t } = useI18n();
  const [target] = useState(() => targetOf(context.view));
  const [text, setText] = useState(() => shownOf(context));
  const { problem, setProblem, go } = useGoing(context);

  function submit(event: FormEvent) {
    event.preventDefault();
    go(target, text).then((done) => done && onClose(), context.fail);
  }

  return (
    <Modal heading={t('nameBox.title')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('nameBox.label')}
          <input
            autoFocus
            autoComplete="off"
            spellCheck={false}
            value={text}
            onFocus={(event) => event.currentTarget.select()}
            onChange={(event) => {
              setText(event.target.value);
              setProblem(null);
            }}
            aria-invalid={problem !== null}
            aria-describedby="go-to-note"
            className={field}
          />
        </label>
        <p id="go-to-note" className={`text-sm ${problem ? 'text-danger' : 'text-muted'}`}>
          {t(problem ? PROBLEMS[problem] : 'nameBox.hint')}
        </p>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={!text.trim()} className={primaryButton}>
            {t('nameBox.go')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
