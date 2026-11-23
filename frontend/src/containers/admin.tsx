import { KeyRound, Plus, Server, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { deleteJson, postJson } from '../api';
import { ConfirmDialog, Modal, Picker } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { ActionsMenu, MenuItem, MenuSeparator } from '../menu';
import { button, primaryButton } from '../styles';
import { CopyButton } from '../vault/parts';
import { dockerError, useDockerChange, useDockerHosts, type DockerHost } from './data';

function Added({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const candidates = useDockerHosts().data?.candidates ?? [];
  const [chosen, setChosen] = useState('');
  const location = chosen || candidates[0]?.id || '';
  const made = useDockerChange((given: string) =>
    postJson('/api/containers/hosts', { location: given }),
  );
  return (
    <Modal heading={t('docker.hostNew')} onClose={onClose}>
      {candidates.length === 0 ? (
        <p className="text-sm text-muted">{t('docker.noCandidates')}</p>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            made.mutate(location, { onSuccess: onClose });
          }}
        >
          <Picker
            label={t('docker.location')}
            value={location}
            options={candidates.map((each) => [each.id, each.name] as const)}
            onChange={setChosen}
          />
          {made.error && (
            <p role="alert" className="text-sm whitespace-pre-wrap text-danger">
              {dockerError(made.error, t)}
            </p>
          )}
          <div className="flex justify-end">
            <button type="submit" className={primaryButton} disabled={made.isPending}>
              {t('docker.hostAdd')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

/** The Docker hosts of the installation (D55): an SFTP location made one, and the line its
 * account's `authorized_keys` takes, which lets Ponistra's key do nothing but Docker. */
export function DockerHostsSection() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const hosts = useDockerHosts();
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<DockerHost | null>(null);
  const removal = useDockerChange((host: DockerHost) =>
    deleteJson(`/api/containers/hosts/${host.location}`),
  );
  const failure = hosts.error ?? removal.error;
  return (
    <Headed
      heading={t('docker.hosts')}
      action={
        <button type="button" className={button} onClick={() => setAdding(true)}>
          <Plus size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('docker.hostNew')}</span>
        </button>
      }
    >
      {failure && (
        <p className="text-sm whitespace-pre-wrap text-danger">{dockerError(failure, t)}</p>
      )}
      {hosts.isSuccess &&
        (hosts.data.hosts.length === 0 ? (
          <p className="text-sm text-muted">{t('docker.hostNone')}</p>
        ) : (
          <ul className="divide-y divide-line rounded border border-line">
            {hosts.data.hosts.map((host) => (
              <li key={host.location} className="flex flex-col gap-1 px-3 py-2">
                <div className="flex items-center gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate">{host.name}</p>
                    <p className="truncate text-xs text-muted">{host.address}</p>
                  </div>
                  <ActionsMenu>
                    <MenuItem
                      icon={Server}
                      label={t('docker.hostOpen')}
                      onSelect={() => navigate(`/docker/${host.location}`)}
                    />
                    <MenuSeparator />
                    <MenuItem
                      icon={Trash2}
                      label={t('docker.hostRemove')}
                      onSelect={() => setRemoving(host)}
                    />
                  </ActionsMenu>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <KeyRound size={14} aria-hidden className="shrink-0 text-muted" />
                  <code className="min-w-0 flex-1 truncate font-mono text-xs">
                    {host.authorized}
                  </code>
                  <CopyButton text={host.authorized} label={t('docker.copyAuthorized')} />
                </div>
              </li>
            ))}
          </ul>
        ))}
      {adding && <Added onClose={() => setAdding(false)} />}
      {removing && (
        <ConfirmDialog
          heading={t('docker.hostRemoveTitle')}
          confirmLabel={t('docker.hostRemove')}
          onConfirm={() => removal.mutate(removing, { onSettled: () => setRemoving(null) })}
          onClose={() => setRemoving(null)}
        >
          <strong>{removing.name}</strong> {t('docker.hostRemoveWarning')}
        </ConfirmDialog>
      )}
    </Headed>
  );
}
