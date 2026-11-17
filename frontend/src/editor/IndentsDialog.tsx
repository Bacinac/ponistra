import type { EditorView } from 'prosemirror-view';
import { useState, type FormEvent } from 'react';
import { Cancel, Labelled, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { field, primaryButton } from '../styles';
import { textblocks } from './blocks';
import { indentsOf, LEAST_LINE, placedOf, setPlaced, type Placed } from './rulers';

const FIELDS: readonly (readonly [keyof Placed, MessageKey])[] = [
  ['first', 'ruler.first'],
  ['lines', 'ruler.hanging'],
  ['right', 'ruler.indentRight'],
];

/** The ruler's indents as lengths: the first selected paragraph's, then those changed done to
 * every selected paragraph. */
export function IndentsDialog({
  view,
  width,
  onClose,
}: {
  view: EditorView;
  /** How wide the text's lines are, in cm. */
  width: number;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [before] = useState(() => placedOf(indentsOf(textblocks(view.state)[0]?.node.attrs ?? {})));
  const [typed, setTyped] = useState(
    () =>
      Object.fromEntries(FIELDS.map(([key]) => [key, String(before[key])])) as Record<
        keyof Placed,
        string
      >,
  );
  const most = Math.floor((width - LEAST_LINE) * 100) / 100;
  const valueOf = (key: keyof Placed) => Math.round(Number(typed[key]) * 100) / 100;
  const valid = (key: keyof Placed) =>
    typed[key].trim() !== '' && valueOf(key) >= 0 && valueOf(key) <= most;
  const ready = FIELDS.every(([key]) => valid(key));

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    const changed = Object.fromEntries(
      FIELDS.filter(([key]) => valueOf(key) !== before[key]).map(([key]) => [key, valueOf(key)]),
    );
    if (Object.keys(changed).length) setPlaced(changed, width)(view.state, view.dispatch);
    onClose();
  }

  return (
    <Modal heading={t('indents.title')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {FIELDS.map(([key, label], index) => (
          <Labelled key={key} label={`${t(label)} (cm)`}>
            {(id) => (
              <input
                id={id}
                autoFocus={index === 0}
                type="number"
                inputMode="decimal"
                min={0}
                max={most}
                step={0.01}
                value={typed[key]}
                onChange={(event) => setTyped({ ...typed, [key]: event.target.value })}
                aria-invalid={!valid(key)}
                className={field}
              />
            )}
          </Labelled>
        ))}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={!ready} className={primaryButton}>
            {t('styles.apply')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
