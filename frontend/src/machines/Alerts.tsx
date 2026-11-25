import { useI18n } from '../i18n';
import { useAlerts, type Alert } from './api';
import { card, Loaded, Pill, useFormats } from './parts';

/** What needs the machine's manager now, then what stopped needing them in the last 30 days. */
export function Alerts() {
  const { t } = useI18n();
  const alerts = useAlerts();
  return (
    <Loaded query={alerts}>
      {(data) => {
        const raised = data
          .filter((alert) => !alert.cleared_at)
          .sort(
            (a, b) =>
              Number(b.severity === 'critical') - Number(a.severity === 'critical') ||
              b.raised_at.localeCompare(a.raised_at),
          );
        const cleared = data
          .filter((alert) => alert.cleared_at)
          .sort((a, b) => b.cleared_at!.localeCompare(a.cleared_at!));
        return (
          <section className={card} aria-label={t('machine.alerts')}>
            <h2 className="text-base font-semibold">{t('machine.alerts')}</h2>
            {raised.length === 0 ? (
              <p className="text-sm text-muted">{t('machine.alerts.none')}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {raised.map((alert) => (
                  <AlertRow key={alert.id} alert={alert} />
                ))}
              </ul>
            )}
            {cleared.length > 0 && (
              <details className="text-sm">
                <summary className="cursor-pointer text-muted">
                  {t('machine.alerts.cleared')} ({cleared.length})
                </summary>
                <ul className="mt-2 flex flex-col gap-2">
                  {cleared.map((alert) => (
                    <AlertRow key={`${alert.id}-${alert.raised_at}`} alert={alert} />
                  ))}
                </ul>
              </details>
            )}
          </section>
        );
      }}
    </Loaded>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  const { t } = useI18n();
  const format = useFormats();
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
      <Pill tone={alert.cleared_at ? 'quiet' : alert.severity === 'critical' ? 'bad' : 'quiet'}>
        {t(`machine.alert.${alert.severity}`)}
      </Pill>
      <span className={alert.cleared_at ? 'text-muted' : ''}>{alert.text}</span>
      <span className="text-xs text-muted">
        {format.date(alert.raised_at)}
        {alert.cleared_at && ` – ${format.date(alert.cleared_at)}`}
      </span>
    </li>
  );
}
