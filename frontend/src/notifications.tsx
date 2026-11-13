import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BellOff, BellRing, Download, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { deleteJson, getJson, patchJson } from './api';
import { useSession } from './auth';
import { deviceName } from './devices';
import { useI18n } from './i18n';
import {
  askToInstall,
  current,
  onIos,
  pushWorks,
  renew,
  subscribe,
  unsubscribe,
  useInstall,
  type PushState,
  type Subscribed,
} from './push';
import { button, primaryButton } from './styles';
import { errorMessage } from './tree';

interface Setting {
  on: boolean;
  changed_by: { id: number; name: string } | null;
  changed_at: string | null;
}

const PUSH = ['push'];
const SETTING = ['push', 'setting'];
const cell = 'px-2 py-2';

function permissionNow(): NotificationPermission {
  return pushWorks ? Notification.permission : 'denied';
}

/** Notifications of mail, messages and rings for the browsers the user chooses, this one first;
    a page of the settings, with the installation's switch for an administrator. */
export function Notifications() {
  const { t, language, formatDate } = useI18n();
  const admin = useSession().data?.user?.is_admin;
  const queryClient = useQueryClient();
  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [permission, setPermission] = useState(permissionNow);
  const install = useInstall();

  useEffect(() => {
    void current().then((found) => setEndpoint(found?.endpoint ?? null));
  }, []);

  const state = useQuery({
    queryKey: [...PUSH, endpoint],
    queryFn: () => getJson<PushState>(`/api/push?endpoint=${encodeURIComponent(endpoint ?? '')}`),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: PUSH });
  const turnOn = useMutation({
    mutationFn: async () => {
      const given = await subscribe(state.data!.key, language);
      setPermission(given);
      setEndpoint((await current())?.endpoint ?? null);
    },
    onSuccess: refresh,
  });
  const turnOff = useMutation({
    mutationFn: async () => {
      await unsubscribe();
      setEndpoint(null);
    },
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (browser: Subscribed) => deleteJson(`/api/push/subscriptions/${browser.id}`),
    onSuccess: refresh,
  });
  const failure = state.error ?? turnOn.error ?? turnOff.error ?? remove.error;
  const browsers = state.data?.subscriptions ?? [];
  const mine = browsers.find((each) => each.current);
  const on = Boolean(endpoint && mine);
  const busy = turnOn.isPending || turnOff.isPending;

  let status: string;
  if (!pushWorks) status = t('notifications.unsupported');
  else if (state.data && !state.data.on) status = t('notifications.offInstallation');
  else if (permission === 'denied') status = t('notifications.blocked');
  else if (onIos && !install.installed) status = t('notifications.ios');
  else status = t(on ? 'notifications.on' : 'notifications.off');
  const offered = pushWorks && state.data?.on && permission !== 'denied';

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-muted">{t('notifications.note')}</p>
      <section className="flex flex-col gap-2">
        <h2 className="font-semibold">{t('notifications.thisBrowser')}</h2>
        <p className="text-sm">{status}</p>
        {offered && (
          <div>
            {on ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => turnOff.mutate()}
                className={button}
              >
                <BellOff size={16} aria-hidden />
                {t('notifications.disable')}
              </button>
            ) : (
              <button
                type="button"
                disabled={busy || !state.isSuccess}
                onClick={() => turnOn.mutate()}
                className={primaryButton}
              >
                <BellRing size={16} aria-hidden />
                {t('notifications.enable')}
              </button>
            )}
          </div>
        )}
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-semibold">{t('notifications.installTitle')}</h2>
        <p className="text-sm">
          {t(install.installed ? 'notifications.installed' : 'notifications.installNote')}
        </p>
        {install.offered && (
          <div>
            <button type="button" onClick={() => void askToInstall()} className={primaryButton}>
              <Download size={16} aria-hidden />
              {t('notifications.install')}
            </button>
          </div>
        )}
        {!install.installed && !install.offered && (
          <p className="text-sm text-muted">{t('notifications.installHint')}</p>
        )}
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="font-semibold">{t('notifications.browsers')}</h2>
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        {state.isSuccess && browsers.length === 0 && (
          <p className="text-sm">{t('notifications.none')}</p>
        )}
        {browsers.length > 0 && (
          <table className="w-full border-collapse">
            <thead className="text-left text-sm text-muted">
              <tr className="border-b border-line">
                <th className="w-full px-2 py-2 font-normal">{t('notifications.browser')}</th>
                <th className="hidden px-2 py-2 font-normal whitespace-nowrap sm:table-cell">
                  {t('notifications.since')}
                </th>
                <th className="px-2 py-2 font-normal whitespace-nowrap">
                  {t('notifications.last')}
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {browsers.map((browser) => (
                <tr key={browser.id} className="border-b border-line">
                  <td className={`${cell} max-w-0`}>
                    <p className="truncate" title={browser.agent}>
                      {deviceName(browser.agent) ?? t('devices.unknown')}
                    </p>
                    {browser.current && (
                      <p className="text-xs text-muted">{t('notifications.this')}</p>
                    )}
                  </td>
                  <td
                    className={`${cell} hidden text-sm whitespace-nowrap text-muted sm:table-cell`}
                  >
                    {formatDate(browser.created_at)}
                  </td>
                  <td className={`${cell} text-sm whitespace-nowrap text-muted`}>
                    {browser.used_at ? formatDate(browser.used_at) : t('notifications.never')}
                  </td>
                  <td className={`${cell} text-right whitespace-nowrap`}>
                    {!browser.current && (
                      <button
                        type="button"
                        disabled={remove.isPending}
                        onClick={() => remove.mutate(browser)}
                        className={button}
                      >
                        <Trash2 size={16} aria-hidden />
                        {t('notifications.remove')}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {admin && <InstallationSetting />}
    </div>
  );
}

function InstallationSetting() {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const setting = useQuery({
    queryKey: SETTING,
    queryFn: () => getJson<Setting>('/api/push/setting'),
  });
  const change = useMutation({
    mutationFn: (on: boolean) => patchJson<Setting>('/api/push/setting', { on }),
    onSuccess: (changed) => {
      queryClient.setQueryData(SETTING, changed);
      void queryClient.invalidateQueries({ queryKey: PUSH });
    },
  });
  const failure = setting.error ?? change.error;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">{t('notifications.setting')}</h2>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={setting.data?.on ?? false}
          disabled={!setting.isSuccess || change.isPending}
          onChange={(event) => change.mutate(event.target.checked)}
        />
        {t('notifications.settingOn')}
      </label>
      <p className="text-sm text-muted">{t('notifications.settingNote')}</p>
      {setting.data?.changed_by && setting.data.changed_at && (
        <p className="text-sm text-muted">
          {t('notifications.settingChanged')}: {setting.data.changed_by.name},{' '}
          {formatDate(setting.data.changed_at)}
        </p>
      )}
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
    </section>
  );
}

/** Keeps this browser's subscription current and opens what a notification leads to. */
export function usePushBridge(navigate: (url: string) => void): void {
  const { language } = useI18n();
  useEffect(() => {
    void renew(language).catch((error: unknown) => {
      console.error('The notification subscription was not renewed', error);
    });
  }, [language]);
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;
    const opened = (event: MessageEvent<{ type?: string; url?: string }>) => {
      if (event.data?.type === 'open' && typeof event.data.url === 'string') {
        navigate(event.data.url);
      }
    };
    navigator.serviceWorker.addEventListener('message', opened);
    return () => navigator.serviceWorker.removeEventListener('message', opened);
  }, [navigate]);
}
