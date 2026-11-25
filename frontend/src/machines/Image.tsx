import { useState, type FormEvent } from 'react';
import { Cancel, Labelled, Modal } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { button, field, primaryButton } from '../styles';
import {
  useImage,
  useMachineWrite,
  type Deployment,
  type ImageAction,
  type ImageStatus,
  type Role,
} from './api';
import { card, Failure, Loaded, Pill, useFormats } from './parts';

export function Image() {
  const image = useImage();
  return <Loaded query={image}>{(data) => <ImageParts image={data} />}</Loaded>;
}

const ACTIONS: { action: Exclude<ImageAction, 'role'>; label: MessageKey }[] = [
  { action: 'check', label: 'machine.image.check' },
  { action: 'update', label: 'machine.image.update' },
  { action: 'rollback', label: 'machine.image.rollback' },
];

function ImageParts({ image }: { image: ImageStatus }) {
  const { t } = useI18n();
  const format = useFormats();
  const start = useMachineWrite((api, action: ImageAction) =>
    api.send('POST', `/v1/image/${action}`),
  );
  const [switching, setSwitching] = useState(false);
  const { job } = image;
  const running = !!job && !job.finished_at;
  const newer =
    !!image.available && image.available.digest !== (image.staged ?? image.booted)?.digest;
  return (
    <div className="flex flex-col gap-6">
      <section className={card} aria-label={t('machine.image')}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold">{t('machine.image')}</h2>
          <div className="flex flex-wrap gap-2">
            {ACTIONS.map(({ action, label }) => (
              <button
                key={action}
                type="button"
                className={action === 'update' && newer ? primaryButton : button}
                disabled={running || start.isPending || (action === 'rollback' && !image.rollback)}
                onClick={() => start.mutate(action)}
              >
                {t(label)}
              </button>
            ))}
          </div>
        </div>
        <p className="text-sm text-muted">{t('machine.image.nextRestart')}</p>
        <Failure error={start.error} />
        {job && (
          <p className="flex flex-wrap items-center gap-2 text-sm" role="status">
            <Pill tone={job.error ? 'bad' : running ? 'quiet' : 'ok'}>
              {t(
                running
                  ? 'machine.job.running'
                  : job.error
                    ? 'machine.job.error'
                    : 'machine.job.ok',
              )}
            </Pill>
            <span>
              {t(`machine.image.job.${job.action}`)}
              {job.target && <span className="font-mono text-xs"> {job.target}</span>}
            </span>
            <span className="text-muted">
              {format.date(job.started_at)}
              {job.finished_at && ` – ${format.date(job.finished_at)}`}
            </span>
            {job.error && <span className="text-danger">{job.error}</span>}
          </p>
        )}
        {image.rollback_queued && (
          <p className="text-sm font-medium">{t('machine.image.rollbackQueued')}</p>
        )}
      </section>
      <Headed
        heading={t('machine.role')}
        action={
          <button
            type="button"
            className={button}
            disabled={running || start.isPending}
            onClick={() => setSwitching(true)}
          >
            {t(image.role === 'server' ? 'machine.role.toWorkstation' : 'machine.role.toServer')}
          </button>
        }
      >
        <p className="text-sm">
          {t(`machine.role.${image.role}`)}
          {image.staged_role && image.staged_role !== image.role && (
            <span className="font-medium">
              {' '}
              ·{' '}
              {t('machine.role.staged').replace(
                '{role}',
                t(`machine.role.name.${image.staged_role}`),
              )}
            </span>
          )}
        </p>
      </Headed>
      {switching && (
        <RoleSwitch
          role={image.role === 'server' ? 'workstation' : 'server'}
          onClose={() => setSwitching(false)}
        />
      )}
      <Headed heading={t('machine.image.deployments')}>
        <p className="text-sm">
          <span className="text-muted">{t('machine.image.follows')} </span>
          <span className="font-mono text-xs break-all">{image.follows}</span>
        </p>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <DeploymentCard label="machine.image.booted" deployment={image.booted} />
          <DeploymentCard label="machine.image.staged" deployment={image.staged} />
          <DeploymentCard label="machine.image.available" deployment={image.available} />
          <DeploymentCard label="machine.image.previous" deployment={image.rollback} />
        </div>
      </Headed>
    </div>
  );
}

function DeploymentCard({
  label,
  deployment,
}: {
  label: MessageKey;
  deployment: Deployment | null;
}) {
  const { t } = useI18n();
  const format = useFormats();
  return (
    <section
      aria-label={t(label)}
      className="flex flex-col gap-1 rounded border border-line p-3 text-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium">{t(label)}</h3>
        {deployment?.pinned && <Pill tone="quiet">{t('machine.image.pinned')}</Pill>}
      </div>
      {deployment ? (
        <>
          <span className="text-base font-medium">{deployment.version || '—'}</span>
          <span className="text-xs text-muted">{format.date(deployment.timestamp || null)}</span>
          <span className="font-mono text-xs break-all text-muted" title={deployment.digest}>
            {deployment.digest.replace(/^sha256:/, '').slice(0, 12)}
          </span>
        </>
      ) : (
        <span className="text-muted">—</span>
      )}
    </section>
  );
}

/** The other role's image staged: the hypervisor and the desktop are one machine's two roles. */
function RoleSwitch({ role, onClose }: { role: Role; onClose: () => void }) {
  const { t } = useI18n();
  const [url, setUrl] = useState('');
  const change = useMachineWrite(
    (api, body: object) => api.send('POST', '/v1/image/role', body),
    onClose,
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    change.mutate({ role, ...(url.trim() && { ponistra_url: url.trim() }) });
  };
  return (
    <Modal
      heading={t(role === 'workstation' ? 'machine.role.toWorkstation' : 'machine.role.toServer')}
      onClose={onClose}
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        <p className="text-sm">
          {t(role === 'workstation' ? 'machine.role.workstationText' : 'machine.role.serverText')}
        </p>
        {role === 'workstation' && (
          <Labelled label={t('machine.role.ponistraUrl')}>
            {(id) => (
              <input
                id={id}
                type="url"
                value={url}
                placeholder="https://"
                onChange={(event) => setUrl(event.target.value)}
                spellCheck={false}
                className={field}
              />
            )}
          </Labelled>
        )}
        <Failure error={change.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={change.isPending}>
            {t('machine.role.stage')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
