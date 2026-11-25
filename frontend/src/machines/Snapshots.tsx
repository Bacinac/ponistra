import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import { Cancel, ConfirmDialog, Labelled, Modal } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, field, iconButton, primaryButton } from '../styles';
import {
  GUEST_NAME,
  snapshotPath,
  guestPath,
  useMachineWrite,
  useSnapshots,
  type Guest,
  type Snapshot,
} from './api';
import { Failure, Loaded, table, useFormats } from './parts';

type Asked = { snapshot: Snapshot; what: 'restore' | 'delete' | 'copy' };

export function Snapshots({ guest }: { guest: Guest }) {
  const { t } = useI18n();
  const format = useFormats();
  const snapshots = useSnapshots(guest.name);
  const [making, setMaking] = useState(false);
  const [asked, setAsked] = useState<Asked | null>(null);
  const navigate = useNavigate();
  const restore = useMachineWrite((api, snapshot: string) =>
    api.send('POST', `${snapshotPath(guest.name, snapshot)}/restore`),
  );
  const remove = useMachineWrite((api, snapshot: string) =>
    api.send('DELETE', snapshotPath(guest.name, snapshot)),
  );
  return (
    <Headed
      heading={t('machine.snapshots')}
      action={
        <button type="button" className={button} onClick={() => setMaking(true)}>
          {t('machine.snapshot.new')}
        </button>
      }
    >
      {restore.isPending && (
        <p role="status" className="text-sm text-muted">
          {t('machine.snapshot.restoring')}
        </p>
      )}
      <Failure error={restore.error} />
      <Failure error={remove.error} />
      <Loaded query={snapshots}>
        {(data) =>
          data.length === 0 ? (
            <p className="text-sm text-muted">{t('machine.snapshots.none')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className={table}>
                <thead>
                  <tr>
                    <th>{t('machine.snapshot')}</th>
                    <th>{t('machine.snapshot.createdAt')}</th>
                    <th>{t('machine.snapshot.expiresAt')}</th>
                    <th>{t('machine.size')}</th>
                    <th>
                      <span className="sr-only">{t('machine.actions')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[...data]
                    .sort((a, b) => b.created_at.localeCompare(a.created_at))
                    .map((snapshot) => (
                      <tr key={snapshot.name}>
                        <td>
                          {guest.kind === 'lxc' ? (
                            <Link
                              to={`snapshots/${encodeURIComponent(snapshot.name)}`}
                              className="text-link hover:underline"
                            >
                              {snapshot.name}
                            </Link>
                          ) : (
                            snapshot.name
                          )}
                          {snapshot.stateful && (
                            <span className="ml-2 text-xs text-muted">
                              {t('machine.snapshot.stateful')}
                            </span>
                          )}
                        </td>
                        <td>{format.date(snapshot.created_at)}</td>
                        <td>{format.date(snapshot.expires_at)}</td>
                        <td className="tabular-nums">{format.bytes(snapshot.size)}</td>
                        <td>
                          <div className="flex justify-end gap-1">
                            <button
                              type="button"
                              className={iconButton}
                              disabled={restore.isPending}
                              onClick={() => setAsked({ snapshot, what: 'restore' })}
                            >
                              {t('machine.snapshot.restore')}
                            </button>
                            <button
                              type="button"
                              className={iconButton}
                              onClick={() => setAsked({ snapshot, what: 'copy' })}
                            >
                              {t('machine.snapshot.copy')}
                            </button>
                            <button
                              type="button"
                              className={iconButton}
                              disabled={remove.isPending}
                              onClick={() => setAsked({ snapshot, what: 'delete' })}
                            >
                              {t('machine.snapshot.delete')}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Loaded>
      {making && <NewSnapshot guest={guest.name} onClose={() => setMaking(false)} />}
      {asked?.what === 'restore' && (
        <ConfirmDialog
          heading={t('machine.snapshot.restoreHeading')}
          confirmLabel={t('machine.snapshot.restore')}
          onConfirm={() => restore.mutate(asked.snapshot.name)}
          onClose={() => setAsked(null)}
        >
          {t('machine.snapshot.restoreText')
            .replace('{guest}', guest.name)
            .replace('{snapshot}', asked.snapshot.name)}
        </ConfirmDialog>
      )}
      {asked?.what === 'delete' && (
        <ConfirmDialog
          heading={t('machine.snapshot.deleteHeading')}
          confirmLabel={t('machine.snapshot.delete')}
          onConfirm={() => remove.mutate(asked.snapshot.name)}
          onClose={() => setAsked(null)}
        >
          {t('machine.snapshot.deleteText').replace('{snapshot}', asked.snapshot.name)}
        </ConfirmDialog>
      )}
      {asked?.what === 'copy' && (
        <CopySnapshot
          guest={guest.name}
          snapshot={asked.snapshot.name}
          onClose={() => setAsked(null)}
          copied={(name) => navigate(`../${encodeURIComponent(name)}`, { relative: 'path' })}
        />
      )}
    </Headed>
  );
}

function NewSnapshot({ guest, onClose }: { guest: string; onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState('');
  const [expires, setExpires] = useState('');
  const make = useMachineWrite(
    (api, body: object) => api.send('POST', `${guestPath(guest)}/snapshots`, body),
    onClose,
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    make.mutate({
      ...(name.trim() && { name: name.trim() }),
      ...(expires && { expires_at: new Date(expires).toISOString() }),
    });
  };
  return (
    <Modal heading={t('machine.snapshot.new')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('machine.snapshot.name')}>
          {(id) => (
            <input
              id={id}
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              autoComplete="off"
              spellCheck={false}
              className={field}
            />
          )}
        </Labelled>
        <Labelled label={t('machine.snapshot.expiresAt')}>
          {(id) => (
            <input
              id={id}
              type="datetime-local"
              value={expires}
              onChange={(event) => setExpires(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <Failure error={make.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={make.isPending}>
            {t('machine.snapshot.make')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** `copied` hears the new guest's name, once the agent has made it. */
export function CopySnapshot({
  guest,
  snapshot,
  onClose,
  copied,
}: {
  guest: string;
  snapshot: string;
  onClose: () => void;
  copied: (name: string) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState('');
  const copy = useMachineWrite((api, given: string) =>
    api.send('POST', `${snapshotPath(guest, snapshot)}/copy`, { name: given }),
  );
  const valid = GUEST_NAME.test(name);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    copy.mutate(name, { onSuccess: () => copied(name) });
  };
  return (
    <Modal heading={t('machine.snapshot.copyHeading')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <p className="text-sm">{t('machine.snapshot.copyText').replace('{snapshot}', snapshot)}</p>
        <Labelled label={t('machine.guest.name')}>
          {(id) => (
            <input
              id={id}
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
              autoComplete="off"
              spellCheck={false}
              maxLength={63}
              aria-invalid={name !== '' && !GUEST_NAME.test(name)}
              className={field}
            />
          )}
        </Labelled>
        {name !== '' && !valid && (
          <p className="-mt-2 text-xs text-muted">{t('machine.guest.nameRule')}</p>
        )}
        {copy.isPending && (
          <p role="status" className="text-sm text-muted">
            {t('machine.snapshot.copying')}
          </p>
        )}
        <Failure error={copy.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={!valid || copy.isPending}>
            {t('machine.snapshot.copy')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
