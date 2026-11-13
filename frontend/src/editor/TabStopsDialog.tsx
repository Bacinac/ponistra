import type { EditorView } from 'prosemirror-view';
import { useState, type FormEvent } from 'react';
import { Cancel, Labelled, Modal, Picker } from '../dialogs';
import { useI18n } from '../i18n';
import { button, field, primaryButton } from '../styles';
import { textblocks } from './blocks';
import { LEADERS, stopsOf, TAB_KINDS, type Leader, type TabKind, type TabStop } from './schema';
import { near, retab } from './stops';

/** Word's Tabs dialog: the first selected paragraph's stops, set and cleared by their position,
 * then done to every selected paragraph. */
export function TabStopsDialog({
  view,
  width,
  onClose,
}: {
  view: EditorView;
  /** How wide the text's lines are, in cm: how far from the margin a stop may stand. */
  width: number;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const [before] = useState(() => stopsOf(textblocks(view.state)[0]?.node.attrs.tabs));
  const [stops, setStops] = useState<TabStop[]>(before);
  const [position, setPosition] = useState(before.length ? String(before[0].at) : '');
  const [kind, setKind] = useState<TabKind>(before[0]?.kind ?? 'left');
  const [leader, setLeader] = useState<Leader | 'none'>(before[0]?.leader ?? 'none');
  const at = Math.round(Number(position) * 100) / 100;
  const typed = position.trim() !== '';
  const valid = typed && at >= 0 && at <= width;
  const chosen = typed ? stops.find((stop) => near(stop, at)) : undefined;
  const widest = Math.floor(width * 100) / 100;

  function choose(stop: TabStop) {
    setPosition(String(stop.at));
    setKind(stop.kind);
    setLeader(stop.leader ?? 'none');
  }

  function withTyped(): TabStop[] {
    const stop = { at, kind, ...(leader !== 'none' && { leader }) };
    return stopsOf([...stops.filter((each) => !near(each, at)), stop]);
  }

  function clear(left: TabStop[]) {
    setStops(left);
    setPosition('');
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (typed && !valid) return;
    retab(before, valid ? withTyped() : stops)(view.state, view.dispatch);
    onClose();
  }

  const described = (stop: TabStop) =>
    [
      `${formatNumber(stop.at)} cm`,
      t(`ruler.tab.${stop.kind}`),
      ...(stop.leader ? [t(`ruler.leader.${stop.leader}`)] : []),
    ].join(' · ');

  return (
    <Modal heading={t('tabStops.title')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <Labelled label={t('tabStops.position')}>
            {(id) => (
              <input
                id={id}
                autoFocus
                type="number"
                inputMode="decimal"
                min={0}
                max={widest}
                step={0.01}
                value={position}
                onChange={(event) => setPosition(event.target.value)}
                aria-invalid={typed && !valid}
                aria-describedby="tab-stops-note"
                className={field}
              />
            )}
          </Labelled>
          <p
            id="tab-stops-note"
            className={`text-sm ${typed && !valid ? 'text-danger' : 'text-muted'}`}
          >
            {`${t('tabStops.within')} ${formatNumber(widest)} cm`}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Picker
            label={t('ruler.tabKind')}
            value={kind}
            options={TAB_KINDS.map((each) => [each, t(`ruler.tab.${each}`)] as const)}
            onChange={setKind}
          />
          <Picker
            label={t('ruler.leader')}
            value={leader}
            options={(['none', ...LEADERS] as const).map(
              (each) => [each, t(`ruler.leader.${each}`)] as const,
            )}
            onChange={setLeader}
          />
        </div>
        {stops.length ? (
          <div className="flex flex-col gap-1 text-sm">
            <span id="tab-stops-list" className="text-muted">
              {t('tabStops.list')}
            </span>
            <ul
              aria-labelledby="tab-stops-list"
              className="flex flex-col gap-0.5 rounded border border-line p-1"
            >
              {stops.map((stop) => (
                <li key={stop.at}>
                  <button
                    type="button"
                    aria-pressed={stop === chosen}
                    onClick={() => choose(stop)}
                    className="flex w-full rounded px-2 py-1.5 text-left text-sm hover:bg-hover aria-pressed:bg-selected aria-pressed:font-semibold"
                  >
                    {described(stop)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-muted">{t('tabStops.none')}</p>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!valid}
            onClick={() => setStops(withTyped())}
            className={button}
          >
            {t('tabStops.set')}
          </button>
          <button
            type="button"
            disabled={!chosen}
            onClick={() => clear(stops.filter((stop) => stop !== chosen))}
            className={button}
          >
            {t('tabStops.clear')}
          </button>
          <button
            type="button"
            disabled={!stops.length}
            onClick={() => clear([])}
            className={button}
          >
            {t('tabStops.clearAll')}
          </button>
        </div>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={typed && !valid} className={primaryButton}>
            {t('styles.apply')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
