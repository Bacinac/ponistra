import type { MessageKey } from './i18n/hr';

type Translate = (key: MessageKey) => string;

/** What a problem the installation's watch raised says, by its key: `service:<name>`,
    `queue:<name>`, `disk:<holds joined by +>`, `snapshots`, `archive` or `offsite`. */
export function problemText(key: string, t: Translate): string {
  const [kind, name = ''] = key.split(':');
  switch (kind) {
    case 'service':
      return `${t(`health.service.${name}` as MessageKey)}: ${t('health.silent')}`;
    case 'queue':
      return `${t(`health.queue.${name}` as MessageKey)}: ${t('health.problem.queue')}`;
    case 'disk':
      return `${t(name.includes('+') ? 'health.disk.both' : (`health.disk.${name}` as MessageKey))}: ${t('health.problem.disk')}`;
    case 'snapshots':
      return t('health.problem.snapshots');
    case 'archive':
      return t('health.problem.archive');
    case 'offsite':
      return t('health.problem.offsite');
    case 'source':
      return `${t('health.problem.source')}: ${key.slice(kind.length + 1)}`;
    default:
      throw new Error(`Unknown problem ${key}`);
  }
}
