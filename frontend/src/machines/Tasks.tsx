import { Headed } from '../headed';
import { isMessageKey, useI18n } from '../i18n';
import { useTasks, type Task } from './api';
import { Loaded, Pill, table, useFormats, type Tone } from './parts';

const TONES: Record<Task['status'], Tone> = { running: 'quiet', ok: 'ok', error: 'bad' };

/** What was done on the machine in the last 30 days, or to one guest. */
export function Tasks({ target }: { target?: string }) {
  const { t } = useI18n();
  const format = useFormats();
  const tasks = useTasks(target);
  return (
    <Headed heading={t('machine.tasks')}>
      <Loaded query={tasks}>
        {(data) =>
          data.length === 0 ? (
            <p className="text-sm text-muted">{t('machine.tasks.none')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className={table}>
                <thead>
                  <tr>
                    <th>{t('machine.task')}</th>
                    {!target && <th>{t('machine.task.target')}</th>}
                    <th>{t('machine.task.by')}</th>
                    <th>{t('machine.task.started')}</th>
                    <th>{t('machine.task.finished')}</th>
                    <th>{t('machine.state')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((task) => {
                    const action = `machine.task.${task.action}`;
                    return (
                      <tr key={task.id}>
                        <td>{isMessageKey(action) ? t(action) : task.action}</td>
                        {!target && <td className="font-mono text-xs">{task.target || '—'}</td>}
                        <td>
                          {task.by}
                          <span className="ml-2 text-xs text-muted">
                            {t(`machine.task.via.${task.via}`)}
                          </span>
                        </td>
                        <td>{format.date(task.started_at)}</td>
                        <td>{format.date(task.finished_at)}</td>
                        <td>
                          <Pill tone={TONES[task.status]}>{t(`machine.job.${task.status}`)}</Pill>
                          {task.error && (
                            <span className="block text-xs text-danger">{task.error}</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        }
      </Loaded>
    </Headed>
  );
}
