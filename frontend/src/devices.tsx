import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { HardDriveDownload, LogOut, WifiOff } from 'lucide-react';
import type { ReactNode } from 'react';
import { deleteJson, getJson } from './api';
import { Close, Modal } from './dialogs';
import { useI18n } from './i18n';
import { useKeepDevice, useKeeping, usePass } from './offline';
import { button, dangerButton, primaryButton } from './styles';
import { errorMessage } from './tree';

interface Device {
  id: string;
  agent: string;
  address: string | null;
  signed_in_at: string;
  seen_at: string;
  current: boolean;
  /** It keeps documents to work without the network (D45). */
  offline: boolean;
}

const BROWSERS: [RegExp, string][] = [
  [/Edg(A|iOS)?\//, 'Edge'],
  [/OPR\//, 'Opera'],
  [/Firefox\/|FxiOS\//, 'Firefox'],
  [/Chrome\/|CriOS\//, 'Chrome'],
  [/Safari\//, 'Safari'],
];

// Android's agent names Linux too, and an iPad's may name a Mac.
const SYSTEMS: [RegExp, string][] = [
  [/Android/, 'Android'],
  [/iPhone|iPad|iOS/, 'iOS'],
  [/Windows/, 'Windows'],
  [/CrOS/, 'ChromeOS'],
  [/Mac OS X|Macintosh/, 'macOS'],
  [/Linux/, 'Linux'],
];

/** The browser and the system a user agent names, as people know them. */
export function deviceName(agent: string): string | null {
  const browser = BROWSERS.find(([pattern]) => pattern.test(agent))?.[1];
  const system = SYSTEMS.find(([pattern]) => pattern.test(agent))?.[1];
  return [browser, system].filter(Boolean).join(' · ') || null;
}

const cell = 'px-2 py-2';

/** Whether this browser keeps documents to work without the network (D45), and taking it on or
    off. */
function ThisDevice() {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const on = useKeeping();
  const pass = usePass();
  const keep = useKeepDevice();
  const change = (next: boolean) =>
    keep.mutate(next, {
      onSettled: () => queryClient.invalidateQueries({ queryKey: ['devices', 'mine'] }),
    });
  let status = t('offline.off');
  if (on && pass.running) status = t('offline.keeping');
  else if (on && pass.failed) status = `${t('offline.failed')} ${pass.failed}`;
  else if (on && pass.at)
    status = `${t('offline.kept')} ${formatDate(new Date(pass.at).toISOString())}`;
  else if (on) status = t('offline.keeping');
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">{t('offline.title')}</h2>
      <p className={`text-sm ${on && pass.failed ? 'text-danger' : ''}`}>{status}</p>
      {keep.error && <p className="text-sm text-danger">{errorMessage(keep.error, t)}</p>}
      <div>
        <button
          type="button"
          disabled={keep.isPending}
          onClick={() => change(!on)}
          className={on ? button : primaryButton}
        >
          {on ? <WifiOff size={16} aria-hidden /> : <HardDriveDownload size={16} aria-hidden />}
          {t(on ? 'offline.disable' : 'offline.enable')}
        </button>
      </div>
    </section>
  );
}

/** The browsers the user is signed in on, or, for an administrator, those of another user. */
/** Where the user is signed in; a page of the settings, and for an administrator the dialog over
    another user's devices. */
export function Devices({
  user,
  footer,
}: {
  user?: { id: number; name: string };
  footer?: ReactNode;
}) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const base = user ? `/api/users/${user.id}/sessions` : '/api/sessions';
  const queryKey = ['devices', user?.id ?? 'mine'];
  const listed = useQuery({
    queryKey,
    queryFn: () => getJson<{ sessions: Device[] }>(base),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey });
  const end = useMutation({
    mutationFn: (device: Device) => deleteJson(`${base}/${device.id}`),
    onSuccess: refresh,
  });
  const endAll = useMutation({ mutationFn: () => deleteJson(base), onSuccess: refresh });
  const failure = listed.error ?? end.error ?? endAll.error;
  const sessions = listed.data?.sessions ?? [];

  return (
    <>
      {!user && <ThisDevice />}
      <p className="text-sm text-muted">{t(user ? 'devices.theirNote' : 'devices.note')}</p>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {listed.isSuccess && sessions.length === 0 && <p className="text-sm">{t('devices.none')}</p>}
      {sessions.length > 0 && (
        <table className="w-full border-collapse">
          <thead className="text-left text-sm text-muted">
            <tr className="border-b border-line">
              <th className="w-full px-2 py-2 font-normal">{t('devices.device')}</th>
              <th className="hidden px-2 py-2 font-normal whitespace-nowrap sm:table-cell">
                {t('devices.signedIn')}
              </th>
              <th className="px-2 py-2 font-normal whitespace-nowrap">{t('devices.seen')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sessions.map((device) => (
              <tr key={device.id} className="border-b border-line">
                <td className={`${cell} max-w-0`}>
                  <p className="flex items-center gap-1.5" title={device.agent}>
                    <span className="truncate">
                      {deviceName(device.agent) ?? t('devices.unknown')}
                    </span>
                    {device.offline && (
                      <span title={t('offline.marked')} className="shrink-0 text-muted">
                        <HardDriveDownload size={14} aria-hidden />
                        <span className="sr-only">{t('offline.marked')}</span>
                      </span>
                    )}
                  </p>
                  <p className="truncate text-xs text-muted">{device.address}</p>
                </td>
                <td className={`${cell} hidden text-sm whitespace-nowrap text-muted sm:table-cell`}>
                  {formatDate(device.signed_in_at)}
                </td>
                <td className={`${cell} text-sm whitespace-nowrap text-muted`}>
                  {formatDate(device.seen_at)}
                </td>
                <td className={`${cell} text-right whitespace-nowrap`}>
                  {device.current ? (
                    <span className="text-sm text-muted">{t('devices.this')}</span>
                  ) : (
                    <button
                      type="button"
                      disabled={end.isPending}
                      onClick={() => end.mutate(device)}
                      className={button}
                    >
                      <LogOut size={16} aria-hidden />
                      {t('devices.end')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(footer || (user && sessions.length > 0)) && (
        <div className="flex justify-end gap-2">
          {user && sessions.length > 0 && (
            <button
              type="button"
              disabled={endAll.isPending}
              onClick={() => endAll.mutate()}
              className={dangerButton}
            >
              {t('devices.endAll')}
            </button>
          )}
          {footer}
        </div>
      )}
    </>
  );
}

export function DevicesDialog({
  user,
  onClose,
}: {
  user: { id: number; name: string };
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <Modal heading={`${t('devices.title')}: ${user.name}`} wide onClose={onClose}>
      <Devices user={user} footer={<Close />} />
    </Modal>
  );
}
