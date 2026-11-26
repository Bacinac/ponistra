import { useEffect, useState, type FormEvent } from 'react';
import { Cancel, Labelled, Modal, Picker } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, field, iconButton, primaryButton } from '../styles';
import {
  useMachineWrite,
  useNetwork,
  type NetworkAddress,
  type NetworkConfig,
  type NetworkLink,
  type NetworkState,
} from './api';
import { card, Fact, Facts, Failure, Loaded, Pill, table } from './parts';

/** The machine's own network: what it is, and a change put on trial that undoes itself unless it
 * is confirmed from where the machine is reachable after it. */
export function Network() {
  const network = useNetwork();
  const [editing, setEditing] = useState(false);
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-6">
      {network.data?.pending ? (
        <Trial state={network.data} />
      ) : (
        network.error && <Failure error={network.error} />
      )}
      <Headed
        heading={t('machine.network.machine')}
        action={
          <button
            type="button"
            className={button}
            disabled={!network.data || !!network.data.pending}
            onClick={() => setEditing(true)}
          >
            {t('machine.network.change')}
          </button>
        }
      >
        <Loaded query={network}>{(state) => <Summary state={state} />}</Loaded>
      </Headed>
      {editing && network.data && (
        <NetworkForm state={network.data} onClose={() => setEditing(false)} />
      )}
    </div>
  );
}

function useCountdown(deadline: string): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return Math.max(0, Math.ceil((Date.parse(deadline) - now) / 1000));
}

function Trial({ state }: { state: NetworkState }) {
  const { t } = useI18n();
  const pending = state.pending!;
  const left = useCountdown(pending.deadline);
  const confirm = useMachineWrite((api) => api.send('POST', '/v1/network/confirm'));
  const revert = useMachineWrite((api) => api.send('POST', '/v1/network/revert'));
  const busy = confirm.isPending || revert.isPending;
  const clock = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
  const here = !pending.reach || window.location.hostname === pending.reach;
  return (
    <section role="status" aria-label={t('machine.network.trial')} className={card}>
      <h2 className="text-base font-semibold">{t('machine.network.trial')}</h2>
      <p className="text-sm">{t('machine.network.trialText').replace('{time}', clock)}</p>
      {!here && (
        <p className="text-sm">
          {t('machine.network.reach')}{' '}
          <a
            href={`https://${pending.reach}/network`}
            className="font-medium text-link hover:underline"
          >
            {pending.reach}
          </a>
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={primaryButton}
          disabled={busy}
          onClick={() => confirm.mutate(undefined)}
        >
          {t('machine.network.confirm')}
        </button>
        <button
          type="button"
          className={button}
          disabled={busy}
          onClick={() => revert.mutate(undefined)}
        >
          {t('machine.network.revert')}
        </button>
      </div>
      <Failure error={confirm.error ?? revert.error} />
    </section>
  );
}

function useAddressText() {
  const { t } = useI18n();
  return (address: NetworkAddress) =>
    address.mode === 'static'
      ? [address.address, address.gateway && `→ ${address.gateway}`].filter(Boolean).join(' ')
      : t(`machine.network.mode.${address.mode}`);
}

function Summary({ state }: { state: NetworkState }) {
  const { t } = useI18n();
  const addressText = useAddressText();
  const { config } = state;
  const links = state.links ?? [];
  const named = (mac: string) => links.find((link) => link.mac === mac)?.name ?? mac;
  const guestPorts = config.guest_ports ?? [];
  const vlans = config.vlans ?? [];
  return (
    <>
      <Facts>
        <Fact label="machine.network.uplink">
          {config.uplink ? named(config.uplink) : t('machine.network.everyPort')}
        </Fact>
        <Fact label="machine.network.address">
          <span className={config.address.mode === 'static' ? 'font-mono text-xs' : undefined}>
            {addressText(config.address)}
          </span>
        </Fact>
        {config.address.mode === 'static' && !!config.address.dns?.length && (
          <Fact label="machine.network.dns">
            <span className="font-mono text-xs">{config.address.dns.join(', ')}</span>
          </Fact>
        )}
        <Fact label="machine.network.bridge">{config.bridge ? 'br0' : t('machine.no')}</Fact>
        <Fact label="machine.network.vlans">
          {vlans.length
            ? vlans
                .map(
                  (vlan) =>
                    `${vlan.id}${vlan.bridge ? ` (br${vlan.id})` : ''}: ${addressText(vlan.address)}`,
                )
                .join(' · ')
            : '—'}
        </Fact>
        <Fact label="machine.network.guestPorts">
          {guestPorts.length ? guestPorts.map(named).join(', ') : '—'}
        </Fact>
      </Facts>
      {links.length > 0 && (
        <div className="overflow-x-auto">
          <table className={table}>
            <thead>
              <tr>
                <th>{t('machine.network.link')}</th>
                <th>{t('machine.network.kind')}</th>
                <th>MAC</th>
                <th>{t('machine.state')}</th>
                <th>{t('machine.addresses')}</th>
              </tr>
            </thead>
            <tbody>
              {links.map((link) => (
                <tr key={link.name}>
                  <td className="font-medium">
                    {link.name}
                    {link.mac === config.uplink && link.kind === 'port' && (
                      <span className="block text-xs text-muted">
                        {t('machine.network.uplink')}
                      </span>
                    )}
                    {guestPorts.includes(link.mac) && (
                      <span className="block text-xs text-muted">
                        {t('machine.network.guestPort')}
                      </span>
                    )}
                  </td>
                  <td>{t(`machine.network.kind.${link.kind}`)}</td>
                  <td className="font-mono text-xs">{link.mac}</td>
                  <td>
                    <Pill tone={link.carrier ? 'ok' : 'quiet'}>
                      {t(link.carrier ? 'machine.network.carrier' : 'machine.network.noCarrier')}
                    </Pill>
                  </td>
                  <td className="font-mono text-xs">{link.addresses?.join(', ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

interface AddressDraft {
  mode: NetworkAddress['mode'];
  address: string;
  gateway: string;
  dns: string;
}

const drafted = (address: NetworkAddress): AddressDraft => ({
  mode: address.mode,
  address: address.address ?? '',
  gateway: address.gateway ?? '',
  dns: (address.dns ?? []).join(', '),
});

function addressOf(draft: AddressDraft, machine: boolean): NetworkAddress {
  if (draft.mode !== 'static') return { mode: draft.mode };
  const dns = draft.dns
    .split(/[\s,]+/)
    .map((each) => each.trim())
    .filter(Boolean);
  return {
    mode: 'static',
    address: draft.address.trim(),
    ...(machine && draft.gateway.trim() && { gateway: draft.gateway.trim() }),
    ...(machine && dns.length > 0 && { dns }),
  };
}

const VLAN_ID = /^\d+$/;
const validVlan = (id: string) => VLAN_ID.test(id) && Number(id) >= 1 && Number(id) <= 4094;

function NetworkForm({ state, onClose }: { state: NetworkState; onClose: () => void }) {
  const { t } = useI18n();
  const ports = (state.links ?? []).filter((link) => link.kind === 'port');
  const [uplink, setUplink] = useState(state.config.uplink);
  const [address, setAddress] = useState(() => drafted(state.config.address));
  const [bridge, setBridge] = useState(state.config.bridge);
  const [vlans, setVlans] = useState(() =>
    (state.config.vlans ?? []).map((vlan) => ({
      id: String(vlan.id),
      bridge: vlan.bridge,
      address: drafted(vlan.address),
    })),
  );
  const [guestPorts, setGuestPorts] = useState(state.config.guest_ports ?? []);
  const change = useMachineWrite(
    (api, config: NetworkConfig) => api.send('PUT', '/v1/network', config),
    onClose,
  );
  const ids = vlans.map((vlan) => vlan.id);
  const valid =
    vlans.every((vlan) => validVlan(vlan.id)) &&
    new Set(ids).size === ids.length &&
    (address.mode !== 'static' || address.address.trim() !== '') &&
    vlans.every((vlan) => vlan.address.mode !== 'static' || vlan.address.address.trim() !== '');

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    change.mutate({
      uplink,
      bridge: uplink !== '' && bridge,
      address: addressOf(address, true),
      vlans:
        uplink === ''
          ? []
          : vlans.map((vlan) => ({
              id: Number(vlan.id),
              bridge: vlan.bridge,
              address: addressOf(vlan.address, false),
            })),
      guest_ports: guestPorts.filter((mac) => mac !== uplink),
    });
  };

  const portLabel = (link: NetworkLink) =>
    `${link.name} (${link.mac})${link.carrier ? '' : ` · ${t('machine.network.noCarrier')}`}`;

  return (
    <Modal wide heading={t('machine.network.change')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <p className="text-sm text-muted">{t('machine.network.trialRule')}</p>
        <Picker
          label={t('machine.network.uplink')}
          value={uplink}
          options={[
            ['', t('machine.network.everyPort')] as const,
            ...ports.map((link) => [link.mac, portLabel(link)] as const),
          ]}
          onChange={setUplink}
        />
        <AddressFields
          draft={address}
          set={setAddress}
          modes={['dhcp', 'static']}
          machine
          label={t('machine.network.address')}
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={uplink !== '' && bridge}
            disabled={uplink === ''}
            onChange={(event) => setBridge(event.target.checked)}
          />
          {t('machine.network.bridgeText')}
        </label>
        <fieldset className="flex flex-col gap-2" disabled={uplink === ''}>
          <legend className="mb-1 text-sm font-medium">{t('machine.network.vlans')}</legend>
          {vlans.map((vlan, index) => {
            const set = (next: Partial<(typeof vlans)[number]>) =>
              setVlans(vlans.map((each, at) => (at === index ? { ...each, ...next } : each)));
            return (
              <div
                key={index}
                className="flex flex-wrap items-end gap-2 rounded border border-line p-2"
              >
                <div className="w-24">
                  <Labelled label={t('machine.network.vlan')}>
                    {(id) => (
                      <input
                        id={id}
                        value={vlan.id}
                        inputMode="numeric"
                        onChange={(event) => set({ id: event.target.value })}
                        aria-invalid={vlan.id !== '' && !validVlan(vlan.id)}
                        className={field}
                      />
                    )}
                  </Labelled>
                </div>
                <div className="min-w-64 flex-1">
                  <AddressFields
                    draft={vlan.address}
                    set={(next) => set({ address: next })}
                    modes={['none', 'dhcp', 'static']}
                    label={t('machine.network.address')}
                  />
                </div>
                <label className="flex items-center gap-2 pb-2 text-sm">
                  <input
                    type="checkbox"
                    checked={vlan.bridge}
                    onChange={(event) => set({ bridge: event.target.checked })}
                  />
                  {t('machine.network.vlanBridge')}
                </label>
                <button
                  type="button"
                  className={iconButton}
                  onClick={() => setVlans(vlans.filter((_, at) => at !== index))}
                >
                  {t('machine.network.vlanRemove')}
                </button>
              </div>
            );
          })}
          <div>
            <button
              type="button"
              className={button}
              onClick={() =>
                setVlans([...vlans, { id: '', bridge: true, address: drafted({ mode: 'none' }) }])
              }
            >
              {t('machine.network.vlanAdd')}
            </button>
          </div>
        </fieldset>
        {ports.some((link) => link.mac !== uplink) && (
          <fieldset className="flex flex-col gap-1">
            <legend className="mb-1 text-sm font-medium">{t('machine.network.guestPorts')}</legend>
            {ports
              .filter((link) => link.mac !== uplink)
              .map((link) => (
                <label key={link.mac} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={guestPorts.includes(link.mac)}
                    onChange={(event) =>
                      setGuestPorts(
                        event.target.checked
                          ? [...guestPorts, link.mac]
                          : guestPorts.filter((mac) => mac !== link.mac),
                      )
                    }
                  />
                  {portLabel(link)}
                </label>
              ))}
          </fieldset>
        )}
        <Failure error={change.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={!valid || change.isPending}>
            {t('machine.network.apply')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function AddressFields({
  draft,
  set,
  modes,
  machine,
  label,
}: {
  draft: AddressDraft;
  set: (draft: AddressDraft) => void;
  modes: AddressDraft['mode'][];
  machine?: boolean;
  label: string;
}) {
  const { t } = useI18n();
  const text = (name: string, value: string, key: keyof AddressDraft, placeholder: string) => (
    <Labelled label={name}>
      {(id) => (
        <input
          id={id}
          value={value}
          placeholder={placeholder}
          onChange={(event) => set({ ...draft, [key]: event.target.value })}
          spellCheck={false}
          autoComplete="off"
          className={`${field} font-mono`}
        />
      )}
    </Labelled>
  );
  return (
    <div className="flex flex-col gap-2">
      <Picker
        label={label}
        value={draft.mode}
        options={modes.map((mode) => [mode, t(`machine.network.mode.${mode}`)] as const)}
        onChange={(mode) => set({ ...draft, mode })}
      />
      {draft.mode === 'static' && (
        <div className={`grid gap-2 ${machine ? 'sm:grid-cols-3' : ''}`}>
          {text(t('machine.network.cidr'), draft.address, 'address', '192.0.2.20/24')}
          {machine && text(t('machine.network.gateway'), draft.gateway, 'gateway', '192.0.2.1')}
          {machine && text(t('machine.network.dns'), draft.dns, 'dns', '192.0.2.1, 9.9.9.9')}
        </div>
      )}
    </div>
  );
}
