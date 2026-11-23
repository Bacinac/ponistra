import {
  ArrowDownToLine,
  Container as Boxed,
  Download,
  FileText,
  Play,
  RotateCw,
  Server,
  Square,
  SquareTerminal,
  type LucideIcon,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useSession } from '../auth';
import { useI18n } from '../i18n';
import { ActionsMenu, MenuItem, MenuSeparator } from '../menu';
import { button, primaryButton } from '../styles';
import {
  act,
  dockerError,
  useDockerChange,
  useDockerHosts,
  useStack,
  VERBS,
  type Container,
  type Verb,
} from './data';
import { LogsDialog, OutputDialog, ShellDialog } from './panels';

const VERB_ICONS: Record<Verb, LucideIcon> = {
  up: Play,
  pull: Download,
  restart: RotateCw,
  stop: Square,
  down: ArrowDownToLine,
};

export type Open =
  { type: 'verb'; verb: Verb } | { type: 'logs' | 'shell'; container: Container } | null;

/** The state of a container as a word and a colour, the same in every list of Docker. */
export function StateLabel({ container }: { container: Pick<Container, 'state' | 'status'> }) {
  const { t } = useI18n();
  const tone =
    container.state === 'running'
      ? 'text-accent'
      : container.state === 'exited' || container.state === 'created'
        ? 'text-muted'
        : 'text-danger';
  return (
    <span className={`text-sm whitespace-nowrap ${tone}`} title={container.status}>
      {t(`docker.state.${container.state}` as 'docker.state.running')}
    </span>
  );
}

/** What a container does from its row: its log, a shell in it, start, stop, restart. */
export function ContainerMenu({
  location,
  container,
  onOpen,
  onFailed,
}: {
  location: string;
  container: Container;
  onOpen: (open: Open) => void;
  onFailed: (error: Error | null) => void;
}) {
  const { t } = useI18n();
  const acted = useDockerChange((action: string) => {
    onFailed(null);
    return act(location, container.id, action);
  });
  const run = (action: string) => acted.mutate(action, { onError: onFailed });
  const running = container.state === 'running';
  return (
    <ActionsMenu>
      <MenuItem
        icon={FileText}
        label={t('docker.logs')}
        onSelect={() => onOpen({ type: 'logs', container })}
      />
      <MenuItem
        icon={SquareTerminal}
        label={t('docker.shell')}
        disabled={!running}
        onSelect={() => onOpen({ type: 'shell', container })}
      />
      <MenuSeparator />
      {running ? (
        <MenuItem icon={Square} label={t('docker.stop')} onSelect={() => run('stop')} />
      ) : (
        <MenuItem icon={Play} label={t('docker.start')} onSelect={() => run('start')} />
      )}
      <MenuItem icon={RotateCw} label={t('docker.restart')} onSelect={() => run('restart')} />
    </ActionsMenu>
  );
}

export function Opened({
  location,
  path,
  open,
  onClose,
}: {
  location: string;
  path: string;
  open: Open;
  onClose: () => void;
}) {
  if (open === null) return null;
  if (open.type === 'verb')
    return <OutputDialog location={location} path={path} verb={open.verb} onClose={onClose} />;
  const Dialog = open.type === 'logs' ? LogsDialog : ShellDialog;
  return (
    <Dialog
      location={location}
      container={open.container.id}
      name={open.container.name}
      onClose={onClose}
    />
  );
}

/** Beside a folder of a location on a Docker host (D55): the stack its compose file makes, its
 * containers and what compose does with it; at the location's root, the way to the host. Only
 * an administrator sees it, as Docker on a host is root on it. */
export function ContainersAside({ location, path }: { location: string; path: string }) {
  const { t } = useI18n();
  const admin = Boolean(useSession().data?.user?.is_admin);
  const hosts = useDockerHosts(admin);
  const host = hosts.data?.hosts.some((each) => each.location === location) ?? false;
  const stack = useStack(location, path, host);
  const [open, setOpen] = useState<Open>(null);
  const [failed, setFailed] = useState<Error | null>(null);
  const navigate = useNavigate();
  if (!host) return null;
  const toHost = (
    <Link to={`/docker/${location}`} className={button}>
      <Server size={16} aria-hidden />
      {t('docker.host')}
    </Link>
  );
  if (stack.error)
    return (
      <section
        aria-label={t('docker.stack')}
        className="flex flex-col gap-2 border-b border-line pb-3"
      >
        <p className="text-sm whitespace-pre-wrap text-danger">{dockerError(stack.error, t)}</p>
        {path === '' && <div>{toHost}</div>}
      </section>
    );
  if (!stack.data?.file)
    return path === '' && stack.isSuccess ? <div className="pb-2">{toHost}</div> : null;
  const { file, containers, said } = stack.data;
  return (
    <section
      aria-label={t('docker.stack')}
      className="flex flex-col gap-2 border-b border-line pb-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Boxed size={18} aria-hidden className="text-muted" />
        <h2 className="min-w-0 flex-1 truncate font-semibold">
          {t('docker.stack')} <span className="font-normal text-muted">· {file}</span>
        </h2>
        <button
          type="button"
          className={primaryButton}
          onClick={() => setOpen({ type: 'verb', verb: 'up' })}
        >
          <Play size={16} aria-hidden />
          {t('docker.verb.up')}
        </button>
        <ActionsMenu>
          {VERBS.filter((verb) => verb !== 'up').map((verb) => (
            <MenuItem
              key={verb}
              icon={VERB_ICONS[verb]}
              label={t(`docker.verb.${verb}`)}
              onSelect={() => setOpen({ type: 'verb', verb })}
            />
          ))}
          <MenuSeparator />
          <MenuItem
            icon={Server}
            label={t('docker.host')}
            onSelect={() => navigate(`/docker/${location}`)}
          />
        </ActionsMenu>
      </div>
      {failed && (
        <p className="text-sm whitespace-pre-wrap text-danger">{dockerError(failed, t)}</p>
      )}
      {said.length > 0 && (
        <p className="text-xs whitespace-pre-wrap text-muted">{said.join('\n')}</p>
      )}
      {containers.length === 0 ? (
        <p className="text-sm text-muted">{t('docker.stackDown')}</p>
      ) : (
        <ul className="divide-y divide-line rounded border border-line">
          {containers.map((container) => (
            <li key={container.id} className="flex items-center gap-2 px-3 py-1.5">
              <div className="min-w-0 flex-1">
                <p className="truncate">{container.service || container.name}</p>
                <p className="truncate text-xs text-muted">
                  {[container.name, container.status, ...container.ports]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </div>
              <StateLabel container={container} />
              <ContainerMenu
                location={location}
                container={container}
                onOpen={setOpen}
                onFailed={setFailed}
              />
            </li>
          ))}
        </ul>
      )}
      <Opened location={location} path={path} open={open} onClose={() => setOpen(null)} />
    </section>
  );
}
