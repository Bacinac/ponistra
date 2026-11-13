import { Fragment } from 'prosemirror-model';
import type { EditorView } from 'prosemirror-view';
import { useEffect, useState } from 'react';
import { Cancel, Labelled, Modal, Picker } from '../dialogs';
import { useI18n } from '../i18n';
import { button, field, primaryButton } from '../styles';
import {
  FORMS,
  kindOfLevel,
  standard,
  type ListFormat,
  type ListLevel,
  type ListStore,
  type Marked,
} from './forms';
import { formatList, levelsAt, markers } from './lists';
import { numeral } from './numerals';
import { INDENT_STEP, schema } from './schema';
import { AFFIX_MAX, NUMBERINGS } from './styling';

const NUMBERED = NUMBERINGS.filter((numbering) => numbering !== '');
const SYMBOLS = Object.values(FORMS.bullet).map((form) => form.prefix);
const SHOWN = 'shown';

/** The marker each level shows on its first item, an item at every level one below the other. */
function markersOf(format: ListFormat): string[] {
  const items = format.map((level, at) =>
    schema.nodes.paragraph.create({
      list: kindOfLevel(level),
      indent: at * INDENT_STEP,
      format: SHOWN,
    }),
  );
  let offset = 0;
  const offsets = items.map((item) => (offset += item.nodeSize) - item.nodeSize);
  const shown = markers(Fragment.from(items), new Map([[SHOWN, format]]));
  return offsets.map((at) => shown.get(at) ?? '');
}

/** What the level keeps once saved: the words after a number only with a number, and the numbers
 * of the levels above only below the first. */
function settled(level: ListLevel, at: number): ListLevel {
  return level.numbering
    ? { ...level, nested: at > 0 && level.nested }
    : { ...level, suffix: '', nested: false };
}

function LevelFields({
  level,
  at,
  onChange,
}: {
  level: ListLevel;
  at: number;
  onChange: (level: ListLevel) => void;
}) {
  const { t } = useI18n();
  const kind = kindOfLevel(level);
  const change = (patch: Partial<ListLevel>) => onChange({ ...level, ...patch });
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <Picker
        label={t('listFormat.kind')}
        value={kind}
        options={[
          ['number', t('listFormat.number')],
          ['bullet', t('listFormat.bullet')],
        ]}
        onChange={(chosen: Marked) => onChange(standard(chosen, at))}
      />
      {kind === 'number' ? (
        <>
          <Picker
            label={t('listFormat.numbering')}
            value={level.numbering}
            options={NUMBERED.map(
              (numbering) =>
                [
                  numbering,
                  [1, 2, 3].map((count) => numeral(count, numbering)).join(', '),
                ] as const,
            )}
            onChange={(numbering) => change({ numbering })}
          />
          {(['prefix', 'suffix'] as const).map((affix) => (
            <Labelled key={affix} label={t(`listFormat.${affix}`)}>
              {(id) => (
                <input
                  id={id}
                  value={level[affix]}
                  maxLength={AFFIX_MAX}
                  onChange={(event) => change({ [affix]: event.target.value })}
                  className={field}
                />
              )}
            </Labelled>
          ))}
          <label className="col-span-full flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={at > 0 && level.nested}
              disabled={at === 0}
              onChange={(event) => change({ nested: event.target.checked })}
            />
            {t('listFormat.nested')}
          </label>
        </>
      ) : (
        <>
          <Labelled label={t('listFormat.symbol')}>
            {(id) => (
              <input
                id={id}
                value={level.prefix}
                maxLength={AFFIX_MAX}
                onChange={(event) => change({ prefix: event.target.value })}
                className={field}
              />
            )}
          </Labelled>
          <div
            role="group"
            aria-label={t('listFormat.symbols')}
            className="col-span-full flex flex-wrap gap-1"
          >
            {SYMBOLS.map((symbol) => (
              <button
                key={symbol}
                type="button"
                aria-pressed={level.prefix === symbol}
                onClick={() => change({ prefix: symbol })}
                className={`${button} min-w-9 justify-center aria-pressed:bg-selected`}
              >
                {symbol}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/** The list at the cursor's look at each of its levels, given to the whole list at once. */
export function ListFormatDialog({
  view,
  lists,
  onClose,
}: {
  view: EditorView;
  lists: ListStore;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const [levels, setLevels] = useState(() => levelsAt(view.state, lists.get()));
  const [selected, setSelected] = useState(0);
  useEffect(() => {
    if (!levels) onClose();
  }, [levels, onClose]);
  if (!levels) return null;
  const format = levels.map(settled);
  const shown = markersOf(format);
  const unmarked = format.some((level) => !level.numbering && !level.prefix.trim());
  const label = (at: number) => `${t('listFormat.level')} ${formatNumber(at + 1)}`;

  function apply() {
    formatList(lists, format)(view.state, view.dispatch);
    onClose();
  }

  return (
    <Modal heading={t('listFormat.title')} wide onClose={onClose}>
      <div className="flex flex-col gap-4 sm:flex-row">
        <nav aria-label={t('listFormat.levels')} className="shrink-0 sm:w-44">
          <ul className="flex flex-col gap-0.5">
            {format.map((_, at) => (
              <li key={at}>
                <button
                  type="button"
                  aria-pressed={at === selected}
                  onClick={() => setSelected(at)}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-hover aria-pressed:bg-selected aria-pressed:font-semibold"
                >
                  <span className="flex-1">{label(at)}</span>
                  <span aria-hidden className="truncate text-muted">
                    {shown[at]}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          <LevelFields
            key={selected}
            level={format[selected]}
            at={selected}
            onChange={(level) =>
              setLevels(format.map((each, at) => (at === selected ? level : each)))
            }
          />
          <figure className="flex flex-col gap-1 text-sm">
            <figcaption className="text-muted">{t('listFormat.preview')}</figcaption>
            <ol aria-label={t('listFormat.preview')} className="rounded border border-line p-4">
              {shown.map((marker, at) => (
                <li
                  key={at}
                  aria-current={at === selected || undefined}
                  style={{ paddingLeft: `${at * INDENT_STEP}rem` }}
                  className="flex gap-2 rounded aria-current:bg-selected"
                >
                  <span className="min-w-8">{marker}</span>
                  {label(at)}
                </li>
              ))}
            </ol>
          </figure>
        </div>
      </div>
      {unmarked && <p className="text-sm text-danger">{t('listFormat.symbolNeeded')}</p>}
      <div className="flex justify-end gap-2">
        <Cancel />
        <button type="button" disabled={unmarked} onClick={apply} className={primaryButton}>
          {t('styles.apply')}
        </button>
      </div>
    </Modal>
  );
}
