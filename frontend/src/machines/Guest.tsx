import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { ConfirmDialog } from '../dialogs';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { button, dangerButton } from '../styles';
import {
  guestClass,
  guestPath,
  MachineError,
  underway,
  useGuest,
  useMachineWrite,
  type Guest as GuestData,
  type GuestAction,
} from './api';
import { Firewall } from './Firewall';
import { statusTone } from './Guests';
import { card, Fact, Facts, Failure, Loaded, Pill, useFormats } from './parts';
import { PressureHistory } from './Pressure';
import { Snapshots } from './Snapshots';
import { Tasks } from './Tasks';

const BUSY: Record<GuestAction, MessageKey> = {
  start: 'machine.guest.starting',
  stop: 'machine.guest.stopping',
  restart: 'machine.guest.restarting',
};

export function Guest() {
  const { name = '' } = useParams();
  const guest = useGuest(name);
  return (
    <div className="flex flex-col gap-6">
      <Link to=".." relative="path" className="text-sm text-link hover:underline">
        ← {useI18n().t('machine.guests')}
      </Link>
      <Loaded query={guest}>{(data) => <GuestParts guest={data} />}</Loaded>
    </div>
  );
}

function GuestParts({ guest }: { guest: GuestData }) {
  const { t } = useI18n();
  const format = useFormats();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const act = useMachineWrite((api, { action, force }: { action: GuestAction; force: boolean }) =>
    api.send('POST', `${guestPath(guest.name)}/${action}`, force ? { force } : {}),
  );
  const remove = useMachineWrite(
    (api) => api.send('DELETE', guestPath(guest.name)),
    () => navigate('..', { relative: 'path' }),
  );
  const running = guest.status === 'Running';
  const busy = act.isPending || remove.isPending || underway(guest);
  const failed = act.error instanceof MachineError && act.variables?.action !== 'start';
  const kind = guestClass(guest);
  const disks = Object.entries(guest.disk ?? {});

  return (
    <>
      <section className={card} aria-label={guest.name}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            {guest.name}
            <Pill tone={statusTone(guest.status)}>{guest.status}</Pill>
          </h2>
          <div className="flex flex-wrap gap-2">
            {running &&
              (guest.kind === 'vm' ? (['vga', 'console'] as const) : (['console'] as const)).map(
                (type) => (
                  <Link key={type} to={`console?type=${type}`} className={button}>
                    {t(
                      type === 'vga'
                        ? 'machine.console.screen'
                        : guest.kind === 'vm'
                          ? 'machine.console.serial'
                          : 'machine.console.text',
                    )}
                  </Link>
                ),
              )}
            {!underway(guest) && guest.status !== 'Error' && (
              <>
                <button
                  type="button"
                  className={button}
                  disabled={busy || running}
                  onClick={() => act.mutate({ action: 'start', force: false })}
                >
                  {t('machine.guest.start')}
                </button>
                <button
                  type="button"
                  className={button}
                  disabled={busy || !running}
                  onClick={() => act.mutate({ action: 'restart', force: false })}
                >
                  {t('machine.guest.restart')}
                </button>
                <button
                  type="button"
                  className={button}
                  disabled={busy || !running}
                  onClick={() => act.mutate({ action: 'stop', force: false })}
                >
                  {t('machine.guest.stop')}
                </button>
              </>
            )}
            <button
              type="button"
              className={dangerButton}
              disabled={act.isPending || remove.isPending || underway(guest)}
              onClick={() => setDeleting(true)}
            >
              {t('machine.guest.delete')}
            </button>
          </div>
        </div>
        {guest.error && <p className="text-sm text-danger">{guest.error}</p>}
        {guest.result && <p className="text-sm break-words whitespace-pre-wrap">{guest.result}</p>}
        {act.isPending && (
          <p role="status" className="text-sm text-muted">
            {t(BUSY[act.variables.action])}
          </p>
        )}
        <Failure error={act.error} />
        {failed && act.variables && !act.variables.force && (
          <div>
            <button
              type="button"
              className={dangerButton}
              onClick={() => act.mutate({ action: act.variables!.action, force: true })}
            >
              {t(
                act.variables.action === 'stop'
                  ? 'machine.guest.forceStop'
                  : 'machine.guest.forceRestart',
              )}
            </button>
          </div>
        )}
        <Failure error={remove.error} />
        {guest.previous && (
          <p className="text-sm">
            {t('machine.guest.restoredFrom')}{' '}
            <span className="font-medium">{guest.restored_from}</span>.{' '}
            {t('machine.guest.previousKept')}{' '}
            <Link
              to={`../${encodeURIComponent(guest.previous)}`}
              relative="path"
              className="font-medium text-link hover:underline"
            >
              {guest.previous}
            </Link>
            .
          </p>
        )}
        {!guest.previous && guest.restored_from && (
          <p className="text-sm">
            {t('machine.guest.restoredFrom')}{' '}
            <span className="font-medium">{guest.restored_from}</span>
          </p>
        )}
        {guest.replaced_at && (
          <p className="text-sm">
            {t('machine.guest.replaced')} {format.date(guest.replaced_at)}.{' '}
            {t('machine.guest.replacedDelete')}
          </p>
        )}
        <Facts>
          <Fact label="machine.guest.kind">{guest.kind}</Fact>
          {guest.description && <Fact label="machine.guest.template">{guest.description}</Fact>}
          <Fact label="machine.guest.class">{kind ? t(`machine.class.${kind}`) : '—'}</Fact>
          <Fact label="machine.guest.autostart">
            {t(guest.autostart ? 'machine.yes' : 'machine.no')}
          </Fact>
          <Fact label="machine.memory">
            {guest.memory ? format.bytes(guest.memory) : '—'}
            {guest.memory_peak > 0 && (
              <span className="text-xs text-muted">
                {' '}
                · {t('machine.guest.peak')} {format.bytes(guest.memory_peak)}
              </span>
            )}
          </Fact>
          <Fact label="machine.limits">
            {[guest.cpu_limit && `${guest.cpu_limit} ${t('machine.cpus')}`, guest.memory_limit]
              .filter(Boolean)
              .join(' · ') || '—'}
          </Fact>
          {disks.length > 0 && (
            <Fact label="machine.disk">
              {disks.map(([device, size]) => `${device} ${format.bytes(size)}`).join(' · ')}
            </Fact>
          )}
          <Fact label="machine.addresses">
            <span className="font-mono text-xs">
              {guest.addresses?.map((each) => `${each.address} (${each.interface})`).join(', ') ||
                '—'}
            </span>
          </Fact>
          {running && <Fact label="machine.guest.processes">{format.number(guest.processes)}</Fact>}
          <Fact label="machine.guest.snapshotPolicy">{guest.snapshot_policy || '—'}</Fact>
          <Fact label="machine.guest.createdAt">{format.date(guest.created_at)}</Fact>
          <Fact label="machine.guest.lastUsedAt">{format.date(guest.last_used_at)}</Fact>
        </Facts>
      </section>
      {!underway(guest) && guest.status !== 'Error' && (
        <>
          <Snapshots guest={guest} />
          <Firewall guest={guest.name} />
          <PressureHistory guest={guest.name} />
        </>
      )}
      <Tasks target={guest.name} />
      {deleting && (
        <ConfirmDialog
          heading={t('machine.guest.deleteHeading')}
          confirmLabel={t('machine.guest.delete')}
          onConfirm={() => remove.mutate(undefined)}
          onClose={() => setDeleting(false)}
        >
          {t(
            guest.status === 'Error'
              ? 'machine.guest.deleteFailed'
              : guest.replaced_at
                ? 'machine.guest.deleteReplaced'
                : 'machine.guest.deleteText',
          )}
        </ConfirmDialog>
      )}
    </>
  );
}
