import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Cancel, Modal, Picker } from '../dialogs';
import { useI18n } from '../i18n';
import { button, field, primaryButton, smallField } from '../styles';
import { columnName } from './formulas';
import { CONDITION_LABELS } from './conditions';
import type { Condition, ConditionOp, GridSource, Offered } from './grids';

type Way = 'values' | 'condition';

/** The user's filter of the table's column: the texts its cells show that the rows kept show,
 * or a condition on them; the other columns' conditions stay as they are. */
export function FilterDialog({
  grids,
  table,
  col,
  onClose,
}: {
  grids: GridSource;
  table: string;
  col: string;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const [start] = useState(() => {
    const grid = grids.grid(table);
    if (!grid || !grid.cols.includes(col)) return null;
    return {
      table,
      grids,
      col,
      name: columnName(grid.cols.indexOf(col)),
      others: grid.filter.filter((each) => each.col !== col),
      own: grid.filter.find((each) => each.col === col),
    };
  });
  const own = start?.own;
  const [way, setWay] = useState<Way>(own && 'op' in own ? 'condition' : 'values');
  const [offered, setOffered] = useState<Offered | null>(null);
  const [chosen, setChosen] = useState<Set<string> | null>(() =>
    own && 'values' in own ? new Set(own.values.map((value) => value.toLowerCase())) : null,
  );
  const [sought, setSought] = useState('');
  const [op, setOp] = useState<ConditionOp>(own && 'op' in own ? own.op : 'contains');
  const [value, setValue] = useState(own && 'op' in own ? own.value : '');
  const [refused, setRefused] = useState(false);

  useEffect(() => {
    if (!start) return;
    let current = true;
    start.grids.offered(start.table, start.col).then(
      (found) => current && setOffered(found),
      () => current && setOffered({ values: [], more: false }),
    );
    return () => {
      current = false;
    };
  }, [start]);

  const shown = useMemo(() => {
    const folded = sought.trim().toLowerCase();
    const all = offered?.values ?? [];
    return folded ? all.filter(([text]) => text.toLowerCase().includes(folded)) : all;
  }, [offered, sought]);

  if (!start) return null;
  const isChosen = (text: string) => chosen === null || chosen.has(text.toLowerCase());
  const everyShown = shown.every(([text]) => isChosen(text));

  function toggle(text: string) {
    const next = new Set(chosen ?? (offered?.values ?? []).map(([each]) => each.toLowerCase()));
    const folded = text.toLowerCase();
    if (next.has(folded)) next.delete(folded);
    else next.add(folded);
    setChosen(next);
  }

  function toggleShown() {
    const next = new Set(chosen ?? (offered?.values ?? []).map(([each]) => each.toLowerCase()));
    for (const [text] of shown) {
      if (everyShown) next.delete(text.toLowerCase());
      else next.add(text.toLowerCase());
    }
    setChosen(next);
  }

  function condition(): Condition | null | 'none' {
    if (way === 'condition') return value.trim() ? { col: start!.col, op, value } : null;
    if (chosen === null || !offered) return null;
    const all = offered.values.map(([text]) => text);
    if (!offered.more && all.every((text) => chosen.has(text.toLowerCase()))) return null;
    const values = all.filter((text) => chosen.has(text.toLowerCase()));
    return values.length ? { col: start!.col, values } : 'none';
  }

  const made = condition();

  function keep(own: Condition | null) {
    const conditions = own ? [...start!.others, own] : start!.others;
    start!.grids.filter(start!.table, conditions).then(onClose, () => setRefused(true));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (made !== 'none') keep(made);
  }

  const ways: readonly (readonly [Way, string])[] = [
    ['values', t('filter.values')],
    ['condition', t('filter.condition')],
  ];

  return (
    <Modal heading={t('filter.title').replace('{col}', start.name)} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div role="group" aria-label={t('filter.way')} className="flex gap-1">
          {ways.map(([each, label]) => (
            <button
              key={each}
              type="button"
              aria-pressed={each === way}
              onClick={() => setWay(each)}
              className={`${button} aria-pressed:bg-selected`}
            >
              {label}
            </button>
          ))}
        </div>
        {way === 'values' ? (
          <div className="flex flex-col gap-2 text-sm">
            <input
              type="search"
              autoFocus
              autoComplete="off"
              aria-label={t('filter.search')}
              placeholder={t('filter.search')}
              value={sought}
              onChange={(event) => setSought(event.target.value)}
              className={smallField}
            />
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={shown.length > 0 && everyShown}
                disabled={!shown.length}
                onChange={toggleShown}
              />
              {t('filter.all')}
            </label>
            <ul
              aria-label={t('filter.values')}
              aria-busy={offered === null}
              className="flex max-h-64 flex-col gap-1 overflow-y-auto"
            >
              {shown.map(([text, count]) => (
                <li key={text.toLowerCase()}>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={isChosen(text)} onChange={() => toggle(text)} />
                    <span className={`min-w-0 flex-1 truncate ${text ? '' : 'text-muted'}`}>
                      {text || t('filter.empty')}
                    </span>
                    <span className="text-muted">{formatNumber(count)}</span>
                  </label>
                </li>
              ))}
            </ul>
            {offered?.more && (
              <p className="text-muted">
                {t('filter.more').replace('{count}', formatNumber(offered.values.length))}
              </p>
            )}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Picker
              label={t('filter.op')}
              value={op}
              options={(Object.keys(CONDITION_LABELS) as ConditionOp[]).map(
                (each) => [each, t(CONDITION_LABELS[each])] as const,
              )}
              onChange={(next) => {
                setOp(next);
                setRefused(false);
              }}
            />
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted">{t('filter.value')}</span>
              <input
                autoFocus
                autoComplete="off"
                value={value}
                aria-invalid={refused}
                onChange={(event) => {
                  setValue(event.target.value);
                  setRefused(false);
                }}
                className={field}
              />
            </label>
          </div>
        )}
        {refused && <p className="text-sm text-danger">{t('filter.refused')}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          {own && (
            <button type="button" onClick={() => keep(null)} className={`${button} mr-auto`}>
              {t('filter.clear')}
            </button>
          )}
          <Cancel />
          <button type="submit" disabled={made === 'none'} className={primaryButton}>
            {t('filter.apply')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
