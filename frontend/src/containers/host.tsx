import { Eraser, Trash2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Navigate, useParams } from 'react-router';
import { useSession } from '../auth';
import { ConfirmDialog } from '../dialogs';
import { formatSize } from '../explorer';
import { Frame, Loading } from '../frame';
import { useI18n } from '../i18n';
import { ActionsMenu, MenuItem } from '../menu';
import { button } from '../styles';
import { ContainerMenu, Opened, StateLabel, type Open } from './aside';
import {
  dockerError,
  KINDS,
  prune,
  removeHeld,
  useDockerChange,
  useHeld,
  useReached,
  type Container,
  type Image,
  type Kind,
  type Network,
  type Pruned,
  type Volume,
} from './data';

type Removing = { kind: Kind; ref: string; name: string } | null;

function Rows({ children }: { children: ReactNode }) {
  return <ul className="divide-y divide-line rounded border border-line">{children}</ul>;
}

function Row({ title, detail, children }: { title: string; detail: string; children?: ReactNode }) {
  return (
    <li className="flex items-center gap-2 px-3 py-1.5">
      <div className="min-w-0 flex-1">
        <p className="truncate">{title}</p>
        <p className="truncate text-xs text-muted">{detail}</p>
      </div>
      {children}
    </li>
  );
}

function Unused({ used }: { used: boolean }) {
  const { t } = useI18n();
  return used ? null : <span className="text-sm text-muted">{t('docker.unused')}</span>;
}

function Removal({ label, onSelect }: { label: string; onSelect: () => void }) {
  return (
    <ActionsMenu>
      <MenuItem icon={Trash2} label={label} onSelect={onSelect} />
    </ActionsMenu>
  );
}

function Listed({
  location,
  kind,
  onOpen,
  onRemove,
  onFailed,
}: {
  location: string;
  kind: Kind;
  onOpen: (open: Open) => void;
  onRemove: (removing: Removing) => void;
  onFailed: (error: Error | null) => void;
}) {
  const { t, formatDate, formatNumber } = useI18n();
  const held = useHeld(location, kind);
  if (held.isPending) return <Loading />;
  if (held.isError)
    return <p className="text-sm whitespace-pre-wrap text-danger">{dockerError(held.error, t)}</p>;
  const when = (iso: string | null | undefined) => (iso ? formatDate(iso) : '');
  const remove = (ref: string, name: string) => () => onRemove({ kind, ref, name });
  const removeLabel = t('docker.remove');
  if (kind === 'containers') {
    const shown = (held.data as { containers: Container[] }).containers;
    return (
      <Rows>
        {shown.map((each) => (
          <Row
            key={each.id}
            title={each.name}
            detail={[each.project, each.image, each.status, ...each.ports]
              .filter(Boolean)
              .join(' · ')}
          >
            <StateLabel container={each} />
            <ContainerMenu
              location={location}
              container={each}
              onOpen={onOpen}
              onFailed={onFailed}
            />
            {each.state !== 'running' && (
              <Removal label={removeLabel} onSelect={remove(each.id, each.name)} />
            )}
          </Row>
        ))}
      </Rows>
    );
  }
  if (kind === 'images') {
    const shown = (held.data as { images: Image[] }).images;
    return (
      <Rows>
        {shown.map((each) => {
          const name = each.tags.join(', ') || each.id.replace('sha256:', '').slice(0, 12);
          const size = each.size === null ? '' : formatSize(each.size, formatNumber);
          return (
            <Row
              key={each.id}
              title={name}
              detail={[size, when(each.created)].filter(Boolean).join(' · ')}
            >
              <Unused used={each.used} />
              {!each.used && <Removal label={removeLabel} onSelect={remove(each.id, name)} />}
            </Row>
          );
        })}
      </Rows>
    );
  }
  if (kind === 'volumes') {
    const shown = (held.data as { volumes: Volume[] }).volumes;
    return (
      <Rows>
        {shown.map((each) => (
          <Row
            key={each.id}
            title={each.name}
            detail={[each.project, each.driver, when(each.created)].filter(Boolean).join(' · ')}
          >
            <Unused used={each.used} />
            {!each.used && <Removal label={removeLabel} onSelect={remove(each.name, each.name)} />}
          </Row>
        ))}
      </Rows>
    );
  }
  const shown = (held.data as { networks: Network[] }).networks;
  return (
    <Rows>
      {shown.map((each) => (
        <Row
          key={each.id}
          title={each.name}
          detail={[each.project, each.driver, each.scope].filter(Boolean).join(' · ')}
        >
          <Unused used={each.used || each.built_in} />
          {!each.used && !each.built_in && (
            <Removal label={removeLabel} onSelect={remove(each.id, each.name)} />
          )}
        </Row>
      ))}
    </Rows>
  );
}

const PRUNES: Record<Kind, Pruned[]> = {
  containers: ['containers'],
  images: ['images', 'builder'],
  volumes: ['volumes'],
  networks: ['networks'],
};

/** A Docker host as a whole (D55): its containers, images, volumes and networks, what nothing
 * uses removed one by one or pruned at once. Only for an administrator. */
export function DockerHostPage() {
  const { t, formatNumber } = useI18n();
  const { location = '' } = useParams();
  const admin = useSession().data?.user?.is_admin;
  const reached = useReached(location);
  const [kind, setKind] = useState<Kind>('containers');
  const [open, setOpen] = useState<Open>(null);
  const [removing, setRemoving] = useState<Removing>(null);
  const [pruning, setPruning] = useState<Pruned | null>(null);
  const [pruned, setPruned] = useState<string | null>(null);
  const [failed, setFailed] = useState<Error | null>(null);
  const removal = useDockerChange((given: NonNullable<Removing>) =>
    removeHeld(location, given.kind, given.ref),
  );
  const cleared = useDockerChange((given: Pruned) => prune(location, given));
  if (admin === false) return <Navigate to="/files" replace />;
  const host = reached.data;
  const failure = reached.error ?? removal.error ?? cleared.error ?? failed;
  const facts = host && [
    `Docker ${host.version}`,
    host.os,
    host.arch,
    host.cpus && `${formatNumber(host.cpus)} CPU`,
    host.memory && formatSize(host.memory, formatNumber),
  ];
  return (
    <Frame title={host?.name ?? t('docker.host')}>
      <div className="flex w-full max-w-5xl flex-col gap-3">
        {host && (
          <p className="text-sm text-muted">
            {[host.address, ...(facts ?? [])].filter(Boolean).join(' · ')}
          </p>
        )}
        {failure && (
          <p className="text-sm whitespace-pre-wrap text-danger">{dockerError(failure, t)}</p>
        )}
        {pruned && (
          <p role="status" className="text-sm text-muted">
            {pruned}
          </p>
        )}
        {(host || !reached.isError) && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <div
                role="tablist"
                aria-label={t('docker.host')}
                className="flex min-w-0 flex-1 gap-1 overflow-x-auto"
              >
                {KINDS.map((each) => (
                  <button
                    key={each}
                    type="button"
                    role="tab"
                    aria-selected={each === kind}
                    onClick={() => setKind(each)}
                    className="rounded-lg px-2 py-1 text-sm aria-selected:bg-selected"
                  >
                    {t(`docker.kind.${each}`)}
                  </button>
                ))}
              </div>
              {PRUNES[kind].map((each) => (
                <button
                  key={each}
                  type="button"
                  className={button}
                  onClick={() => setPruning(each)}
                >
                  <Eraser size={16} aria-hidden />
                  {t(`docker.prune.${each}`)}
                </button>
              ))}
            </div>
            <Listed
              location={location}
              kind={kind}
              onOpen={setOpen}
              onRemove={setRemoving}
              onFailed={setFailed}
            />
          </>
        )}
      </div>
      <Opened location={location} path="" open={open} onClose={() => setOpen(null)} />
      {removing && (
        <ConfirmDialog
          heading={t('docker.removeTitle')}
          confirmLabel={t('docker.remove')}
          onConfirm={() => removal.mutate(removing, { onSettled: () => setRemoving(null) })}
          onClose={() => setRemoving(null)}
        >
          <strong>{removing.name}</strong>
        </ConfirmDialog>
      )}
      {pruning && (
        <ConfirmDialog
          heading={t(`docker.prune.${pruning}`)}
          confirmLabel={t('docker.pruneConfirm')}
          onConfirm={() =>
            cleared.mutate(pruning, {
              onSuccess: (result) =>
                setPruned(
                  t('docker.pruned')
                    .replace('{count}', formatNumber(result.removed))
                    .replace('{size}', formatSize(result.reclaimed, formatNumber)),
                ),
              onSettled: () => setPruning(null),
            })
          }
          onClose={() => setPruning(null)}
        >
          {t(`docker.pruneWarning.${pruning}`)}
        </ConfirmDialog>
      )}
    </Frame>
  );
}
