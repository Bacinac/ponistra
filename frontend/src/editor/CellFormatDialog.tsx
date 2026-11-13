import type { EditorView } from 'prosemirror-view';
import { useState, type FormEvent } from 'react';
import { Cancel, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { field, primaryButton } from '../styles';
import { dateCode, localCode, presetCode, storedCode } from './formats';
import { targetOf } from './tablesPlugin';

export function CellFormatDialog({ view, onClose }: { view: EditorView; onClose: () => void }) {
  const { t } = useI18n();
  const [target] = useState(() => targetOf(view));
  const [locale] = useState(() => target?.table.spec.locale() ?? 'hr');
  const [code, setCode] = useState(() => {
    const first = target?.table.layout.cellsIn(target.rect).next().value;
    const stored = first && target.table.formatOf(first.key);
    return stored ? localCode(stored, locale) : '';
  });
  const examples = [
    ...(['number', 'percent'] as const).map((preset) =>
      localCode(presetCode(preset, locale), locale),
    ),
    dateCode(locale),
  ];

  function submit(event: FormEvent) {
    event.preventDefault();
    const written = code.trim();
    if (target && !target.table.gone) {
      target.table.setFormat(target.rect, written ? storedCode(written, locale) : null);
    }
    onClose();
  }

  return (
    <Modal heading={t('cellFormat.title')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('cellFormat.code')}
          <input
            autoFocus
            spellCheck={false}
            autoComplete="off"
            maxLength={255}
            value={code}
            onChange={(event) => setCode(event.target.value)}
            className={`${field} font-mono`}
          />
        </label>
        <p className="text-sm text-muted">
          {t('cellFormat.hint')} {t('cellFormat.examples')}{' '}
          <span className="font-mono">{examples.join(' · ')}</span>
        </p>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
