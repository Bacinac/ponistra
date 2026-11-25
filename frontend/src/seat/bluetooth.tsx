import { useQuery } from '@tanstack/react-query';
import {
  Bluetooth,
  BluetoothSearching,
  Gamepad2,
  Headphones,
  Keyboard,
  Laptop,
  Mouse,
  Power,
  Printer,
  SignalHigh,
  SignalLow,
  SignalMedium,
  Smartphone,
  Speaker,
  Watch,
  type LucideIcon,
} from 'lucide-react';
import { useState } from 'react';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, compactField, primaryButton } from '../styles';
import {
  EVERY,
  read,
  type BluetoothAdapter,
  type BluetoothDevice,
  type BluetoothState,
} from './api';
import { failure } from './failure';
import { ActionButton, Problem, Row, useAction } from './rows';

export const BLUETOOTH = ['seat', 'bluetooth'] as const;

// BlueZ names a device's kind by the freedesktop icon names.
const ICONS: [string, LucideIcon][] = [
  ['audio-headset', Headphones],
  ['audio-headphones', Headphones],
  ['audio-card', Speaker],
  ['input-mouse', Mouse],
  ['input-tablet', Mouse],
  ['input-keyboard', Keyboard],
  ['input-gaming', Gamepad2],
  ['phone', Smartphone],
  ['computer', Laptop],
  ['printer', Printer],
  ['watch', Watch],
];

function iconOf(icon: string | undefined): LucideIcon {
  return ICONS.find(([name]) => icon?.startsWith(name))?.[1] ?? Bluetooth;
}

function strength(rssi: number) {
  if (rssi >= -60) return SignalHigh;
  if (rssi >= -75) return SignalMedium;
  return SignalLow;
}

function Device({
  device,
  open,
  onToggle,
}: {
  device: BluetoothDevice;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  const action = useAction(BLUETOOTH);
  const busy = action.isPending;
  const doing = action.variables?.path;
  const run = (path: string, own?: Parameters<typeof action.mutate>[0]['own']) =>
    action.mutate({ path: `bluetooth/${path}`, body: { device: device.id }, own });
  const Signal = device.rssi ? strength(device.rssi) : null;
  const remove = (
    <ActionButton
      label={t('seat.bluetooth.remove')}
      busy={busy && doing === 'bluetooth/remove' && t('seat.bluetooth.removing')}
      disabled={busy}
      onClick={() => run('remove')}
    />
  );
  return (
    <Row
      icon={iconOf(device.icon)}
      name={device.name || device.address}
      state={
        device.connected
          ? t('seat.bluetooth.connected')
          : device.paired
            ? t('seat.bluetooth.paired')
            : undefined
      }
      marks={
        Signal && (
          <Signal
            size={14}
            aria-label={t('seat.bluetooth.signal')}
            className="shrink-0 text-muted"
          />
        )
      }
      open={open}
      onToggle={onToggle}
    >
      <div className="flex flex-wrap gap-2">
        {!device.paired ? (
          <ActionButton
            look={primaryButton}
            label={t('seat.bluetooth.pair')}
            busy={busy && t('seat.bluetooth.pairing')}
            disabled={busy}
            onClick={() => run('pair', { 400: 'seat.bluetooth.pairRefused' })}
          />
        ) : device.connected ? (
          <>
            <ActionButton
              label={t('seat.bluetooth.disconnect')}
              busy={busy && doing === 'bluetooth/disconnect' && t('seat.bluetooth.disconnecting')}
              disabled={busy}
              onClick={() => run('disconnect')}
            />
            {remove}
          </>
        ) : (
          <>
            <ActionButton
              look={primaryButton}
              label={t('seat.bluetooth.connect')}
              busy={busy && doing === 'bluetooth/connect' && t('seat.bluetooth.connecting')}
              disabled={busy}
              onClick={() => run('connect')}
            />
            {remove}
          </>
        )}
      </div>
      <Problem message={action.message} />
    </Row>
  );
}

function Adapter({ adapter, devices }: { adapter: BluetoothAdapter; devices: BluetoothDevice[] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState<string | null>(null);
  if (!adapter.powered) return <p className="text-sm text-muted">{t('seat.bluetooth.isOff')}</p>;
  return (
    <ul className="flex flex-col gap-2">
      {devices.map((device) => (
        <Device
          key={device.id}
          device={device}
          open={open === device.id}
          onToggle={() => setOpen((shown) => (shown === device.id ? null : device.id))}
        />
      ))}
      {devices.length === 0 && (
        <li className="text-sm text-muted">
          {adapter.discovering ? t('seat.bluetooth.searching') : t('seat.bluetooth.none')}
        </li>
      )}
    </ul>
  );
}

/** The machine's Bluetooth: turned on, searched for devices, which are paired and connected. */
export function BluetoothSection() {
  const { t } = useI18n();
  const state = useQuery({
    queryKey: BLUETOOTH,
    queryFn: () => read<BluetoothState>('bluetooth'),
    refetchInterval: EVERY,
    retry: false,
  });
  const [chosen, setChosen] = useState<string | null>(null);
  const control = useAction(BLUETOOTH);
  const adapters = state.data?.adapters ?? [];
  const adapter = adapters.find((each) => each.id === chosen) ?? adapters[0];

  if (state.error && !state.data) {
    return (
      <Headed heading={t('seat.bluetooth')}>
        <Problem message={failure(state.error, t, { 503: 'seat.bluetooth.down' })} />
      </Headed>
    );
  }
  if (!adapter) return null;
  const switching = control.isPending && control.variables?.path === 'bluetooth/power';
  const searching = control.isPending && control.variables?.path === 'bluetooth/scan';
  return (
    <Headed
      heading={t('seat.bluetooth')}
      action={
        <div className="flex flex-wrap items-center gap-2">
          {adapters.length > 1 && (
            <select
              aria-label={t('seat.bluetooth.adapter')}
              className={compactField}
              value={adapter.id}
              onChange={(event) => setChosen(event.target.value)}
            >
              {adapters.map((each) => (
                <option key={each.id} value={each.id}>
                  {each.address}
                </option>
              ))}
            </select>
          )}
          {adapter.powered && (
            <button
              type="button"
              className={button}
              aria-pressed={adapter.discovering}
              disabled={searching}
              onClick={() =>
                control.mutate({
                  path: 'bluetooth/scan',
                  body: { adapter: adapter.id, on: !adapter.discovering },
                })
              }
            >
              <BluetoothSearching
                size={16}
                aria-hidden
                className={adapter.discovering ? 'animate-pulse' : ''}
              />
              {t(adapter.discovering ? 'seat.bluetooth.stop' : 'seat.bluetooth.search')}
            </button>
          )}
          <button
            type="button"
            className={adapter.powered ? button : primaryButton}
            disabled={switching}
            onClick={() =>
              control.mutate({
                path: 'bluetooth/power',
                body: { adapter: adapter.id, on: !adapter.powered },
              })
            }
          >
            <Power size={16} aria-hidden />
            {t(adapter.powered ? 'seat.bluetooth.turnOff' : 'seat.bluetooth.turnOn')}
          </button>
        </div>
      }
    >
      <Problem message={control.message} />
      <Adapter key={adapter.id} adapter={adapter} devices={state.data?.devices ?? []} />
    </Headed>
  );
}
