import { useState } from 'react';
import { Link } from 'react-router';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, primaryButton } from '../styles';
import { guestClass, useGuests, useImage, type Guest } from './api';
import { Isos } from './Isos';
import { NewGuest } from './NewGuest';
import { Loaded, Pill, table, useFormats, type Tone } from './parts';
import { ProxmoxImport } from './ProxmoxImport';
import { Transfer } from './Transfer';

export function statusTone(status: string): Tone {
  if (status === 'Running') return 'ok';
  if (status === 'Error') return 'bad';
  if (status === 'Stopped') return 'quiet';
  return 'quiet';
}

export function Guests() {
  const { t } = useI18n();
  const format = useFormats();
  const guests = useGuests();
  const image = useImage();
  const closed = image.data?.staged_role === 'workstation';
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  return (
    <div className="flex flex-col gap-8">
      <Headed
        heading={t('machine.guests')}
        action={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={button}
              disabled={closed}
              onClick={() => setImporting(true)}
            >
              {t('machine.import')}
            </button>
            <button
              type="button"
              className={primaryButton}
              disabled={closed}
              onClick={() => setCreating(true)}
            >
              {t('machine.guest.new')}
            </button>
          </div>
        }
      >
        {closed && <p className="text-sm text-muted">{t('machine.guests.closed')}</p>}
        <Loaded query={guests}>
          {(data) =>
            data.length === 0 ? (
              <p className="text-sm text-muted">{t('machine.guests.none')}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className={table}>
                  <thead>
                    <tr>
                      <th>{t('machine.guest')}</th>
                      <th>{t('machine.state')}</th>
                      <th>{t('machine.guest.class')}</th>
                      <th>{t('machine.memory')}</th>
                      <th>{t('machine.addresses')}</th>
                      <th>{t('machine.snapshots')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((guest) => (
                      <GuestRow key={guest.name} guest={guest} format={format} />
                    ))}
                  </tbody>
                </table>
              </div>
            )
          }
        </Loaded>
        {creating && <NewGuest onClose={() => setCreating(false)} />}
        {importing && <ProxmoxImport onClose={() => setImporting(false)} />}
      </Headed>
      <Isos />
      <Transfer />
    </div>
  );
}

function GuestRow({ guest, format }: { guest: Guest; format: ReturnType<typeof useFormats> }) {
  const { t } = useI18n();
  const kind = guestClass(guest);
  return (
    <tr>
      <td>
        <Link to={encodeURIComponent(guest.name)} className="font-medium text-link hover:underline">
          {guest.name}
        </Link>
        <span className="block text-xs text-muted">
          {[guest.kind, guest.description || guest.recipe].filter(Boolean).join(' · ')}
        </span>
      </td>
      <td>
        <Pill tone={statusTone(guest.status)}>{guest.status}</Pill>
        {guest.error && <span className="block text-xs text-danger">{guest.error}</span>}
        {guest.replaced_at && (
          <span className="block text-xs text-muted">
            {t('machine.guest.replacedAt')} {format.date(guest.replaced_at)}
          </span>
        )}
      </td>
      <td>{kind ? t(`machine.class.${kind}`) : '—'}</td>
      <td className="tabular-nums">
        {guest.memory ? format.bytes(guest.memory) : '—'}
        {guest.memory_limit && <span className="text-xs text-muted"> / {guest.memory_limit}</span>}
      </td>
      <td className="font-mono text-xs">
        {guest.addresses?.map((each) => each.address).join(', ') || '—'}
      </td>
      <td className="tabular-nums">{format.number(guest.snapshots)}</td>
    </tr>
  );
}
