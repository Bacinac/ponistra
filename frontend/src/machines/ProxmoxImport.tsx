import { useState, type FormEvent, type ReactNode } from 'react';
import { Cancel, Labelled, Modal, Picker } from '../dialogs';
import { useI18n } from '../i18n';
import { button, field, iconButton, primaryButton } from '../styles';
import {
  CLASSES,
  GUEST_NAME,
  useImportKey,
  useMachineWrite,
  useNetworks,
  type GuestClass,
} from './api';
import { Failure } from './parts';

type Pair = { from: string; to: string };

const filled = (pairs: Pair[]) =>
  Object.fromEntries(
    pairs
      .filter((pair) => pair.from.trim() && pair.to.trim())
      .map((pair) => [pair.from.trim(), pair.to.trim()]),
  );

/** A Proxmox container brought over as a guest: the agent signs in to the Proxmox host as root
 * with its own key, which the form shows for that host's authorized_keys. */
export function ProxmoxImport({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const key = useImportKey();
  const networks = useNetworks();
  const [host, setHost] = useState('');
  const [vmid, setVmid] = useState('');
  const [name, setName] = useState('');
  const [kind, setKind] = useState<GuestClass>('production');
  const [bridges, setBridges] = useState<Pair[]>([{ from: 'vmbr0', to: '' }]);
  const [binds, setBinds] = useState<Pair[]>([]);
  const [dropFirewall, setDropFirewall] = useState(false);
  const [start, setStart] = useState(false);
  const [copied, setCopied] = useState(false);
  const bring = useMachineWrite(
    (api, body: object) => api.send('POST', '/v1/imports/proxmox', body),
    onClose,
  );
  const valid = host.trim() !== '' && /^[1-9]\d*$/.test(vmid) && GUEST_NAME.test(name);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    const mapped = filled(bridges);
    const bound = filled(binds);
    bring.mutate({
      host: host.trim(),
      vmid: Number(vmid),
      name,
      class: kind,
      ...(Object.keys(mapped).length > 0 && { networks: mapped }),
      ...(Object.keys(bound).length > 0 && { binds: bound }),
      ...(dropFirewall && { drop_firewall: true }),
      ...(start && { start: true }),
    });
  };

  const pairs = (
    label: string,
    list: Pair[],
    set: (list: Pair[]) => void,
    target: (pair: Pair, index: number) => ReactNode,
  ) => (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm text-muted">{label}</legend>
      {list.map((pair, index) => (
        <div key={index} className="grid grid-cols-[1fr_1fr_auto] items-center gap-2">
          <input
            aria-label={`${label} ${index + 1}`}
            value={pair.from}
            onChange={(event) =>
              set(
                list.map((each, at) =>
                  at === index ? { ...each, from: event.target.value } : each,
                ),
              )
            }
            spellCheck={false}
            className={field}
          />
          {target(pair, index)}
          <button
            type="button"
            className={iconButton}
            onClick={() => set(list.filter((_, at) => at !== index))}
          >
            {t('machine.import.remove')}
          </button>
        </div>
      ))}
      <div>
        <button
          type="button"
          className={button}
          onClick={() => set([...list, { from: '', to: '' }])}
        >
          {t('machine.import.add')}
        </button>
      </div>
    </fieldset>
  );

  return (
    <Modal wide heading={t('machine.import.heading')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('machine.import.key')}</span>
          {key.data ? (
            <div className="flex items-start gap-2">
              <code className="min-w-0 flex-1 rounded border border-line bg-panel px-2 py-1.5 font-mono text-xs break-all">
                {key.data.public_key}
              </code>
              <button
                type="button"
                className={button}
                onClick={() =>
                  navigator.clipboard.writeText(key.data.public_key).then(() => setCopied(true))
                }
              >
                {t(copied ? 'machine.import.copied' : 'machine.import.copy')}
              </button>
            </div>
          ) : (
            <Failure error={key.error} />
          )}
        </div>
        <div className="grid grid-cols-[1fr_8rem] gap-2">
          <Labelled label={t('machine.import.host')}>
            {(id) => (
              <input
                id={id}
                value={host}
                onChange={(event) => setHost(event.target.value)}
                autoFocus
                spellCheck={false}
                className={field}
              />
            )}
          </Labelled>
          <Labelled label={t('machine.import.vmid')}>
            {(id) => (
              <input
                id={id}
                value={vmid}
                inputMode="numeric"
                onChange={(event) => setVmid(event.target.value)}
                className={field}
              />
            )}
          </Labelled>
        </div>
        <Labelled label={t('machine.guest.name')}>
          {(id) => (
            <input
              id={id}
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              maxLength={63}
              aria-invalid={name !== '' && !GUEST_NAME.test(name)}
              className={field}
            />
          )}
        </Labelled>
        {name !== '' && !GUEST_NAME.test(name) && (
          <p className="-mt-2 text-xs text-muted">{t('machine.guest.nameRule')}</p>
        )}
        <Picker
          label={t('machine.guest.class')}
          value={kind}
          options={CLASSES.map((each) => [each, t(`machine.class.${each}`)] as const)}
          onChange={setKind}
        />
        {pairs(t('machine.import.bridges'), bridges, setBridges, (pair, index) => (
          <select
            aria-label={`${t('machine.network')} ${index + 1}`}
            value={pair.to}
            onChange={(event) =>
              setBridges(
                bridges.map((each, at) =>
                  at === index ? { ...each, to: event.target.value } : each,
                ),
              )
            }
            className={field}
          >
            <option value="">{t('machine.network.nat')}</option>
            {networks.data?.map((each) => (
              <option key={each.name} value={each.name}>
                {each.name} ({each.type})
              </option>
            ))}
          </select>
        ))}
        <Failure error={networks.error} />
        {pairs(t('machine.import.binds'), binds, setBinds, (pair, index) => (
          <input
            aria-label={`${t('machine.import.hostPath')} ${index + 1}`}
            value={pair.to}
            placeholder="/"
            onChange={(event) =>
              setBinds(
                binds.map((each, at) =>
                  at === index ? { ...each, to: event.target.value } : each,
                ),
              )
            }
            spellCheck={false}
            className={field}
          />
        ))}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={dropFirewall}
            onChange={(event) => setDropFirewall(event.target.checked)}
          />
          {t('machine.import.dropFirewall')}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={start}
            onChange={(event) => setStart(event.target.checked)}
          />
          {t('machine.import.start')}
        </label>
        <Failure error={bring.error} />
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={!valid || bring.isPending}>
            {t('machine.import.submit')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
