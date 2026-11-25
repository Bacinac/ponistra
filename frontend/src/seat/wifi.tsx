import { useQuery } from '@tanstack/react-query';
import { Lock, RefreshCw, Wifi, WifiHigh, WifiLow, WifiPen, WifiZero } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, compactField, primaryButton } from '../styles';
import { EVERY, read, type WifiDevice, type WifiNetwork } from './api';
import { failure } from './failure';
import { ActionButton, Problem, Row, useAction } from './rows';

export const WIFI = ['seat', 'wifi'] as const;

function strength(dbm: number) {
  if (dbm >= -55) return Wifi;
  if (dbm >= -67) return WifiHigh;
  if (dbm >= -78) return WifiLow;
  return WifiZero;
}

function Network({
  device,
  network,
  open,
  onToggle,
}: {
  device: string;
  network: WifiNetwork;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const [passphrase, setPassphrase] = useState('');
  const action = useAction(WIFI, () => setPassphrase(''));
  const asks = !network.known && (network.security === 'psk' || network.security === 'wep');
  // The screen has no way to give an enterprise sign-in; one the machine was given still joins.
  const enterprise = !network.known && network.security === '8021x';
  const busy = action.isPending;
  const doing = action.variables?.path;

  const connect = (event: FormEvent) => {
    event.preventDefault();
    action.mutate({
      path: 'wifi/connect',
      body: asks ? { network: network.id, passphrase } : { network: network.id },
      own: { 400: 'seat.wifi.wrongPassphrase' },
    });
  };
  const forget = (
    <ActionButton
      label={t('seat.wifi.forget')}
      busy={busy && doing === 'wifi/forget' && t('seat.wifi.forgetting')}
      disabled={busy}
      onClick={() => action.mutate({ path: 'wifi/forget', body: { network: network.id } })}
    />
  );

  return (
    <Row
      icon={strength(network.signal)}
      name={network.name}
      state={
        network.connected
          ? t('seat.wifi.connected')
          : network.known
            ? t('seat.wifi.known')
            : undefined
      }
      marks={
        network.security !== 'open' && (
          <Lock size={14} aria-label={t('seat.wifi.secured')} className="shrink-0 text-muted" />
        )
      }
      open={open}
      onToggle={onToggle}
    >
      {network.connected ? (
        <div className="flex flex-wrap gap-2">
          <ActionButton
            label={t('seat.wifi.disconnect')}
            busy={busy && doing === 'wifi/disconnect' && t('seat.wifi.disconnecting')}
            disabled={busy}
            onClick={() => action.mutate({ path: 'wifi/disconnect', body: { device } })}
          />
          {forget}
        </div>
      ) : enterprise ? (
        <p className="text-sm text-muted">{t('seat.wifi.enterprise')}</p>
      ) : (
        <form className="flex flex-wrap items-end gap-2" onSubmit={connect}>
          {asks && (
            <label className="flex min-w-48 flex-1 flex-col gap-1 text-sm">
              {t('seat.wifi.passphrase')}
              <input
                type="password"
                className={compactField}
                value={passphrase}
                onChange={(event) => setPassphrase(event.target.value)}
                autoComplete="off"
                autoFocus
                required
                disabled={busy}
              />
            </label>
          )}
          <ActionButton
            type="submit"
            look={primaryButton}
            label={t('seat.wifi.connect')}
            busy={busy && doing === 'wifi/connect' && t('seat.wifi.connecting')}
            disabled={busy}
          />
          {network.known && forget}
        </form>
      )}
      <Problem message={action.message} />
    </Row>
  );
}

function Hidden({
  device,
  open,
  onToggle,
}: {
  device: string;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState('');
  const [passphrase, setPassphrase] = useState('');
  const action = useAction(WIFI, () => {
    setName('');
    setPassphrase('');
  });
  const join = (event: FormEvent) => {
    event.preventDefault();
    action.mutate({
      path: 'wifi/hidden',
      body: { device, name, passphrase },
      own: { 400: 'seat.wifi.wrongPassphrase', 404: 'seat.wifi.hiddenMissing' },
    });
  };
  return (
    <Row icon={WifiPen} name={t('seat.wifi.hidden')} open={open} onToggle={onToggle}>
      <form className="flex flex-wrap items-end gap-2" onSubmit={join}>
        <label className="flex min-w-40 flex-1 flex-col gap-1 text-sm">
          {t('seat.wifi.name')}
          <input
            className={compactField}
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
            autoFocus
            required
            disabled={action.isPending}
          />
        </label>
        <label className="flex min-w-40 flex-1 flex-col gap-1 text-sm">
          {t('seat.wifi.passphrase')}
          <input
            type="password"
            className={compactField}
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            autoComplete="off"
            disabled={action.isPending}
          />
        </label>
        <ActionButton
          type="submit"
          look={primaryButton}
          label={t('seat.wifi.connect')}
          busy={action.isPending && t('seat.wifi.connecting')}
          disabled={action.isPending}
        />
      </form>
      <Problem message={action.message} />
    </Row>
  );
}

function Device({ device }: { device: WifiDevice }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<string | null>(null);
  const toggle = (id: string) => () => setOpen((shown) => (shown === id ? null : id));
  if (device.state === 'off' || !device.powered) {
    return <p className="text-sm text-muted">{t('seat.wifi.off')}</p>;
  }
  const networks = device.networks ?? [];
  return (
    <ul className="flex flex-col gap-2">
      {networks.map((network) => (
        <Network
          key={network.id}
          device={device.name}
          network={network}
          open={open === network.id}
          onToggle={toggle(network.id)}
        />
      ))}
      {networks.length === 0 && (
        <li className="text-sm text-muted">
          {device.scanning ? t('seat.wifi.scanning') : t('seat.wifi.none')}
        </li>
      )}
      <Hidden device={device.name} open={open === ''} onToggle={toggle('')} />
    </ul>
  );
}

/** The Wi-Fi networks each of the machine's wireless devices sees, to join one. */
export function WifiSection() {
  const { t } = useI18n();
  const devices = useQuery({
    queryKey: WIFI,
    queryFn: () => read<WifiDevice[] | null>('wifi'),
    refetchInterval: EVERY,
    retry: false,
  });
  const [chosen, setChosen] = useState<string | null>(null);
  const scan = useAction(WIFI);
  const all = devices.data ?? [];
  const device = all.find((each) => each.name === chosen) ?? all[0];

  if (devices.error && !devices.data) {
    return (
      <Headed heading={t('seat.wifi')}>
        <Problem message={failure(devices.error, t, { 503: 'seat.wifi.down' })} />
      </Headed>
    );
  }
  if (!device) return null;
  const scanning = device.scanning || scan.isPending;
  return (
    <Headed
      heading={t('seat.wifi')}
      action={
        <div className="flex flex-wrap items-center gap-2">
          {all.length > 1 && (
            <select
              aria-label={t('seat.wifi.device')}
              className={compactField}
              value={device.name}
              onChange={(event) => setChosen(event.target.value)}
            >
              {all.map((each) => (
                <option key={each.name} value={each.name}>
                  {each.name}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            className={button}
            disabled={scanning || !device.powered}
            onClick={() => scan.mutate({ path: 'wifi/scan', body: { device: device.name } })}
          >
            <RefreshCw size={16} aria-hidden className={scanning ? 'animate-spin' : ''} />
            {t('seat.wifi.scan')}
          </button>
        </div>
      }
    >
      <Problem message={scan.message} />
      <Device key={device.name} device={device} />
    </Headed>
  );
}
