import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileUp, Pencil, Plus, Power, PowerOff, Trash2 } from 'lucide-react';
import { useId, useRef, useState, type FormEvent } from 'react';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { Cancel, ConfirmDialog, Modal, Picker } from './dialogs';
import { Headed } from './headed';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { ActionsMenu, MenuItem, MenuSeparator } from './menu';
import { button, field, primaryButton } from './styles';
import { errorMessage } from './tree';

const KINDS = ['wireguard', 'softether'] as const;
type Kind = (typeof KINDS)[number];
type State = 'connecting' | 'up' | 'failed' | 'off' | 'unreached';

/** A VPN tunnel of the installation as the backend shows it: never what lets it in. */
export interface Tunnel {
  id: number;
  name: string;
  kind: Kind;
  enabled: boolean;
  shown: {
    address?: string;
    endpoint?: string;
    server?: string;
    port?: number;
    hub?: string;
    username?: string;
  };
  state: State;
  error: string;
  detail: string;
  address: string;
  since: string | null;
}

export const TUNNELS = ['network', 'tunnels'];
const ERRORS = ['no_answer', 'refused', 'no_hub', 'no_device', 'dhcp', 'resolve', 'sealed'];

function useTunnelChange<V>(mutationFn: (variables: V) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TUNNELS }),
  });
}

function TunnelDialog({ tunnel, onClose }: { tunnel?: Tunnel; onClose: () => void }) {
  const { t } = useI18n();
  const [kind, setKind] = useState<Kind>(tunnel?.kind ?? 'wireguard');
  const [name, setName] = useState(tunnel?.name ?? '');
  const [configuration, setConfiguration] = useState('');
  const [server, setServer] = useState(tunnel?.shown.server ?? '');
  const [port, setPort] = useState(String(tunnel?.shown.port ?? 443));
  const [hub, setHub] = useState(tunnel?.shown.hub ?? '');
  const [username, setUsername] = useState(tunnel?.shown.username ?? '');
  const [password, setPassword] = useState('');
  const [enabled, setEnabled] = useState(tunnel?.enabled ?? true);
  const picker = useRef<HTMLInputElement>(null);
  const configured = useId();
  const save = useTunnelChange(() => {
    const given =
      kind === 'wireguard'
        ? { configuration }
        : {
            server: server.trim(),
            port: Number(port),
            hub: hub.trim(),
            username: username.trim(),
            password,
          };
    const body = { ...given, kind, name: name.trim(), enabled };
    return tunnel
      ? patchJson<Tunnel>(`/api/network/tunnels/${tunnel.id}`, body)
      : postJson<Tunnel>('/api/network/tunnels', body);
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: onClose });
  };
  const text = (label: MessageKey, value: string, onChange: (value: string) => void, max = 200) => (
    <label className="flex flex-col gap-1 text-sm">
      {t(label)}
      <input
        type="text"
        required
        maxLength={max}
        spellCheck={false}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={field}
      />
    </label>
  );

  return (
    <Modal heading={t(tunnel ? 'network.tunnelEdit' : 'network.tunnelNew')} onClose={onClose} wide>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {text('network.tunnelName', name, setName, 150)}
        {!tunnel && (
          <Picker
            label={t('network.tunnelKind')}
            value={kind}
            options={KINDS.map((each) => [each, t(`network.kind.${each}`)] as const)}
            onChange={setKind}
          />
        )}
        {kind === 'wireguard' ? (
          <div className="flex flex-col gap-1 text-sm">
            <div className="flex items-center justify-between gap-2">
              <label htmlFor={configured}>{t('network.configuration')}</label>
              <button type="button" className={button} onClick={() => picker.current?.click()}>
                <FileUp size={16} aria-hidden />
                {t('network.configurationFile')}
              </button>
            </div>
            <textarea
              id={configured}
              rows={8}
              required={!tunnel}
              spellCheck={false}
              value={configuration}
              placeholder={tunnel ? t('network.configurationReplace') : '[Interface]\n…\n[Peer]\n…'}
              onChange={(event) => setConfiguration(event.target.value)}
              className={`${field} font-mono`}
            />
            <input
              ref={picker}
              type="file"
              accept=".conf,text/plain"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = '';
                if (file) void file.text().then(setConfiguration);
              }}
            />
          </div>
        ) : (
          <>
            <div className="flex gap-3">
              <div className="flex-1">{text('network.server', server, setServer)}</div>
              <label className="flex w-24 flex-col gap-1 text-sm">
                {t('network.port')}
                <input
                  type="number"
                  required
                  min={1}
                  max={65535}
                  value={port}
                  onChange={(event) => setPort(event.target.value)}
                  className={field}
                />
              </label>
            </div>
            {text('network.hub', hub, setHub)}
            {text('network.username', username, setUsername)}
            <label className="flex flex-col gap-1 text-sm">
              {t('network.password')}
              <input
                type="password"
                autoComplete="new-password"
                required={!tunnel}
                value={password}
                placeholder={tunnel ? t('network.passwordReplace') : undefined}
                onChange={(event) => setPassword(event.target.value)}
                className={field}
              />
            </label>
          </>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          {t('network.tunnelEnabled')}
        </label>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t(tunnel ? 'tree.save' : 'tree.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Problem({ tunnel }: { tunnel: Tunnel }) {
  const { t } = useI18n();
  if (!tunnel.error && tunnel.state !== 'failed') return null;
  const said = ERRORS.includes(tunnel.error)
    ? t(`network.tunnelError.${tunnel.error}` as MessageKey)
    : t('network.tunnelError.failed');
  return (
    <p className="text-xs break-words text-danger">
      {said}
      {tunnel.detail && `: ${tunnel.detail}`}
    </p>
  );
}

type Dialog = { type: 'edit'; tunnel?: Tunnel } | { type: 'delete'; tunnel: Tunnel };

/** The installation's VPN tunnels, through which its locations reach other networks (D54). */
export function TunnelsSection() {
  const { t, formatDate } = useI18n();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const tunnels = useQuery({
    queryKey: TUNNELS,
    queryFn: () => getJson<{ tunnels: Tunnel[] }>('/api/network/tunnels'),
  });
  const switched = useTunnelChange((tunnel: Tunnel) =>
    patchJson(`/api/network/tunnels/${tunnel.id}`, { enabled: !tunnel.enabled }),
  );
  const remove = useTunnelChange((tunnel: Tunnel) =>
    deleteJson(`/api/network/tunnels/${tunnel.id}`),
  );
  const failure = tunnels.error ?? switched.error ?? remove.error;
  const close = () => setDialog(null);

  return (
    <Headed
      heading={t('network.tunnels')}
      action={
        <button type="button" className={button} onClick={() => setDialog({ type: 'edit' })}>
          <Plus size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('network.tunnelNew')}</span>
        </button>
      }
    >
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {tunnels.isSuccess &&
        (tunnels.data.tunnels.length === 0 ? (
          <p className="text-sm text-muted">{t('network.tunnelNone')}</p>
        ) : (
          <ul className="divide-y divide-line rounded border border-line">
            {tunnels.data.tunnels.map((tunnel) => (
              <li key={tunnel.id} className="flex items-center gap-2 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className={`truncate ${tunnel.enabled ? '' : 'text-muted'}`}>{tunnel.name}</p>
                  <p className="truncate text-xs text-muted">
                    {[
                      t(`network.kind.${tunnel.kind}`),
                      tunnel.shown.endpoint ??
                        (tunnel.shown.server && `${tunnel.shown.server}:${tunnel.shown.port}`),
                      tunnel.state === 'up' && tunnel.address,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  <Problem tunnel={tunnel} />
                </div>
                <span
                  className={`text-sm whitespace-nowrap ${
                    tunnel.state === 'up'
                      ? 'text-accent'
                      : tunnel.state === 'off'
                        ? 'text-muted'
                        : 'text-danger'
                  }`}
                  title={tunnel.since ? formatDate(tunnel.since) : undefined}
                >
                  {t(`network.state.${tunnel.state}`)}
                </span>
                <ActionsMenu>
                  <MenuItem
                    icon={Pencil}
                    label={t('network.tunnelEdit')}
                    onSelect={() => setDialog({ type: 'edit', tunnel })}
                  />
                  <MenuItem
                    icon={tunnel.enabled ? PowerOff : Power}
                    label={t(tunnel.enabled ? 'network.tunnelOff' : 'network.tunnelOn')}
                    onSelect={() => switched.mutate(tunnel)}
                  />
                  <MenuSeparator />
                  <MenuItem
                    icon={Trash2}
                    label={t('network.tunnelDelete')}
                    onSelect={() => setDialog({ type: 'delete', tunnel })}
                  />
                </ActionsMenu>
              </li>
            ))}
          </ul>
        ))}
      {dialog?.type === 'edit' && <TunnelDialog tunnel={dialog.tunnel} onClose={close} />}
      {dialog?.type === 'delete' && (
        <ConfirmDialog
          heading={t('network.tunnelDeleteTitle')}
          confirmLabel={t('network.tunnelDelete')}
          onConfirm={() => remove.mutate(dialog.tunnel, { onSuccess: close })}
          onClose={close}
        >
          <strong>{dialog.tunnel.name}</strong> {t('network.tunnelDeleteWarning')}
        </ConfirmDialog>
      )}
    </Headed>
  );
}
