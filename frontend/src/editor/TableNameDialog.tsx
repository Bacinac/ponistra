import type { EditorView } from 'prosemirror-view';
import { useEffect, useState, type FormEvent } from 'react';
import { Cancel, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { field, primaryButton } from '../styles';
import { NAME_LENGTH, nameProblem } from './tables';
import { targetOf } from './tablesPlugin';

const PROBLEMS = {
  invalid: 'tableName.invalid',
  taken: 'tableName.taken',
  needed: 'tableName.needed',
} as const;

export function TableNameDialog({ view, onClose }: { view: EditorView; onClose: () => void }) {
  const { t } = useI18n();
  const [target] = useState(() => targetOf(view));
  const [name, setName] = useState(() => target?.table.lines?.name ?? '');
  const written = name.trim();
  const table = target?.table;
  const [referred, setReferred] = useState<boolean | null>(null);
  useEffect(() => {
    if (!table) return;
    let current = true;
    table.referred().then((found) => current && setReferred(found), table.spec.fail);
    return () => {
      current = false;
    };
  }, [table]);
  const problem = !table
    ? null
    : written
      ? nameProblem(table.spec.grids, table.node.attrs.id, written)
      : referred && 'needed';
  const blocked = problem !== null || (!written && referred === null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (blocked) return;
    if (table && !table.gone) table.rename(written);
    onClose();
  }

  return (
    <Modal heading={t('tableName.title')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('tableName.name')}
          <input
            autoFocus
            autoComplete="off"
            maxLength={NAME_LENGTH}
            value={name}
            onChange={(event) => setName(event.target.value)}
            aria-invalid={problem !== null}
            aria-describedby="table-name-note"
            className={field}
          />
        </label>
        <p id="table-name-note" className={`text-sm ${problem ? 'text-danger' : 'text-muted'}`}>
          {t(problem ? PROBLEMS[problem] : 'tableName.hint')}
        </p>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={blocked} className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
