import { QueryClientProvider } from '@tanstack/react-query';
import { Circle, Plus, Trash2 } from 'lucide-react';
import { useMemo, useState, type FormEvent } from 'react';
import { Navigate, NavLink, Route, Routes, useNavigate, useParams, useRoutes } from 'react-router';
import { ConfirmDialog, Labelled, Modal } from '../dialogs';
import { formatSize } from '../explorer';
import { Frame, useWide } from '../frame';
import { Headed, inline, inlineField } from '../headed';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { MachineContext, newMachineQueryClient, useMachine } from '../machines/api';
import { MACHINE_PAGES, MACHINE_ROUTES } from '../machines/routes';
import { usePeople } from '../people';
import { button, dangerButton, field, iconButton, primaryButton, sideRow } from '../styles';
import {
  computerApi,
  refusalText,
  useCodeDeleted,
  useComputer,
  useComputers,
  useInstall,
  useManagerAdded,
  useManagerRemoved,
  useRemoved,
  useSecretOpened,
  useSticks,
  useTakenOver,
  type Answers,
  type Computer,
  type Detail,
  type Listed,
  type Made,
  type Secret,
} from './data';

const tab =
  'rounded px-3 py-1.5 text-sm hover:bg-hover aria-[current=page]:bg-selected aria-[current=page]:font-semibold aria-[current=page]:text-accent';

function raised(computer: Computer) {
  return computer.alerts.filter((alert) => !alert.cleared_at);
}

/** Računala (C4): the computers the person manages, each with its machine's own pages run
 * through Ponistra and what Ponistra keeps of it. */
export function ComputersPage() {
  const { t } = useI18n();
  const listed = useComputers();
  const [adding, setAdding] = useState(false);
  const data = listed.data;
  return (
    <Frame
      title={t('computers.title')}
      folders={false}
      side={data && <Side listed={data} />}
      primary={
        data?.can_add && (
          <button type="button" className={primaryButton} onClick={() => setAdding(true)}>
            <Plus size={16} aria-hidden className="mr-1 inline" />
            {t('computers.add')}
          </button>
        )
      }
    >
      {listed.error && (
        <p role="alert" className="text-sm text-danger">
          {refusalText(listed.error, t)}
        </p>
      )}
      {data && (
        <Routes>
          <Route index element={<First listed={data} />} />
          <Route path=":id/*" element={<Opened />} />
        </Routes>
      )}
      {adding && <AddDialog onClose={() => setAdding(false)} />}
    </Frame>
  );
}

function First({ listed }: { listed: Listed }) {
  const { t } = useI18n();
  const wide = useWide();
  const first = listed.computers[0];
  if (first && wide) return <Navigate to={first.id} replace />;
  if (first) return null;
  return <p className="text-sm text-muted">{t('computers.none')}</p>;
}

function Side({ listed }: { listed: Listed }) {
  const { t, formatDate } = useI18n();
  const deleted = useCodeDeleted();
  const taken = useTakenOver();
  const navigate = useNavigate();
  return (
    <nav aria-label={t('computers.title')} className="flex flex-col gap-4">
      <section className="flex flex-col gap-0.5">
        {listed.computers.map((computer) => (
          <NavLink key={computer.id} to={`/computers/${computer.id}`} className={sideRow}>
            <Circle
              size={8}
              aria-label={t(computer.connected ? 'computers.connected' : 'computers.offline')}
              className={computer.connected ? 'fill-accent text-accent' : 'text-muted'}
            />
            <span className="flex-1 truncate">{computer.name}</span>
            {raised(computer).length > 0 && (
              <span className="text-xs text-danger">{raised(computer).length}</span>
            )}
          </NavLink>
        ))}
      </section>
      {listed.codes.length > 0 && (
        <section aria-label={t('computers.codes')} className="flex flex-col gap-0.5">
          <h2 className="px-2 text-xs font-semibold text-muted uppercase">
            {t('computers.codes')}
          </h2>
          {listed.codes.map((code) => (
            <div key={code.id} className="flex items-center gap-2 px-2 py-1 text-sm">
              <span className="flex-1 truncate font-mono">…{code.hint}</span>
              <span className="text-xs text-muted">{formatDate(code.expires_at)}</span>
              <button
                type="button"
                className={iconButton}
                aria-label={t('computers.code.delete')}
                title={t('computers.code.delete')}
                onClick={() => deleted.mutate(code.id)}
              >
                <Trash2 size={14} aria-hidden />
              </button>
            </div>
          ))}
        </section>
      )}
      {listed.orphaned.length > 0 && (
        <section aria-label={t('computers.orphaned')} className="flex flex-col gap-0.5">
          <h2 className="px-2 text-xs font-semibold text-muted uppercase">
            {t('computers.orphaned')}
          </h2>
          {listed.orphaned.map((computer) => (
            <div key={computer.id} className="flex items-center gap-2 px-2 py-1 text-sm">
              <span className="flex-1 truncate">{computer.name}</span>
              <button
                type="button"
                className={button}
                disabled={taken.isPending}
                onClick={() =>
                  taken.mutate(computer.id, {
                    onSuccess: () => navigate(`/computers/${computer.id}/manage`),
                  })
                }
              >
                {t('computers.takeOver')}
              </button>
            </div>
          ))}
          {taken.error && (
            <p role="alert" className="px-2 text-sm text-danger">
              {refusalText(taken.error, t)}
            </p>
          )}
        </section>
      )}
    </nav>
  );
}

function Opened() {
  const { id } = useParams();
  return <ComputerView key={id} id={id!} />;
}

function ComputerView({ id }: { id: string }) {
  const { t } = useI18n();
  const [client] = useState(newMachineQueryClient);
  const api = useMemo(() => computerApi(id, t), [id, t]);
  const detail = useComputer(id);
  if (detail.error) {
    return (
      <p role="alert" className="text-sm text-danger">
        {refusalText(detail.error, t)}
      </p>
    );
  }
  if (!detail.data) return <p className="text-sm text-muted">{t('computers.loading')}</p>;
  return (
    <QueryClientProvider client={client}>
      <MachineContext value={api}>
        <Pages detail={detail.data} />
      </MachineContext>
    </QueryClientProvider>
  );
}

function Pages({ detail }: { detail: Detail }) {
  const { t, formatDate } = useI18n();
  const base = useMachine().data?.os.variant === 'base';
  const pages = useRoutes([
    ...MACHINE_ROUTES,
    { path: 'manage', element: <Manage detail={detail} /> },
  ]);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <h1 className="text-lg font-semibold">{detail.name}</h1>
        <span className={`text-sm ${detail.connected ? 'text-accent' : 'text-muted'}`}>
          {detail.connected
            ? t('computers.connected')
            : detail.seen_at
              ? `${t('computers.offline')} · ${t('computers.seen')} ${formatDate(detail.seen_at)}`
              : t('computers.offline')}
        </span>
      </div>
      <nav
        aria-label={t('machine.pages')}
        className="flex flex-wrap gap-1 border-b border-line pb-2"
      >
        {MACHINE_PAGES.filter((page) => !page.base || base).map((page) => (
          <NavLink key={page.path} to={page.path || '.'} end={page.path === ''} className={tab}>
            {t(page.label)}
          </NavLink>
        ))}
        <NavLink to="manage" className={tab}>
          {t('computers.manage')}
        </NavLink>
      </nav>
      {pages}
    </div>
  );
}

function Manage({ detail }: { detail: Detail }) {
  const { t, formatDate } = useI18n();
  const alerts = raised(detail);
  return (
    <div className="flex max-w-3xl flex-col gap-8">
      {alerts.length > 0 && (
        <Headed heading={t('computers.alerts')}>
          <ul className="flex flex-col gap-1 text-sm">
            {alerts.map((alert) => (
              <li key={alert.key} className="flex gap-2">
                <span className={alert.severity === 'critical' ? 'text-danger' : 'text-ink'}>
                  {t(`computers.severity.${alert.severity}` as MessageKey)}
                </span>
                <span className="flex-1">{alert.text}</span>
                <span className="text-muted">{formatDate(alert.raised_at)}</span>
              </li>
            ))}
          </ul>
        </Headed>
      )}
      <Managers detail={detail} />
      <Secrets detail={detail} />
      <Removal detail={detail} />
    </div>
  );
}

function Managers({ detail }: { detail: Detail }) {
  const { t } = useI18n();
  const people = usePeople();
  const added = useManagerAdded(detail.id);
  const removed = useManagerRemoved(detail.id);
  const [chosen, setChosen] = useState('');
  const others = (people.data?.users ?? []).filter(
    (person) => !detail.managers.some((manager) => manager.id === person.id),
  );
  const failed = added.error ?? removed.error;
  const add = (event: FormEvent) => {
    event.preventDefault();
    if (chosen) added.mutate(Number(chosen), { onSuccess: () => setChosen('') });
  };
  return (
    <Headed heading={t('computers.managers')}>
      <ul className="flex flex-col gap-1 text-sm">
        {detail.managers.map((manager) => (
          <li key={manager.id} className="flex items-center gap-2">
            <span className="flex-1 truncate">
              {manager.name} <span className="text-muted">{manager.email}</span>
            </span>
            <button
              type="button"
              className={iconButton}
              aria-label={`${t('computers.manager.remove')}: ${manager.name}`}
              title={t('computers.manager.remove')}
              disabled={detail.managers.length === 1 || removed.isPending}
              onClick={() => removed.mutate(manager.id)}
            >
              <Trash2 size={14} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={add} className={inline}>
        <div className={inlineField}>
          <Labelled label={t('computers.manager.add')}>
            {(labelled) => (
              <select
                id={labelled}
                value={chosen}
                onChange={(event) => setChosen(event.target.value)}
                className={field}
              >
                <option value="" />
                {others.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            )}
          </Labelled>
        </div>
        <button type="submit" className={button} disabled={!chosen || added.isPending}>
          {t('computers.manager.addButton')}
        </button>
      </form>
      {failed && (
        <p role="alert" className="text-sm text-danger">
          {refusalText(failed, t)}
        </p>
      )}
    </Headed>
  );
}

const SECRETS: { secret: Secret; at: 'recovery_key_at' | 'backup_password_at' }[] = [
  { secret: 'recovery_key', at: 'recovery_key_at' },
  { secret: 'backup_password', at: 'backup_password_at' },
];

function Secrets({ detail }: { detail: Detail }) {
  const { t, formatDate } = useI18n();
  return (
    <>
      {SECRETS.map(({ secret, at }) => (
        <SecretPart key={secret} detail={detail} secret={secret} at={detail[at]} />
      ))}
      {detail.openings.length > 0 && (
        <Headed heading={t('computers.openings')}>
          <ul className="flex flex-col gap-1 text-sm">
            {detail.openings.map((opening) => (
              <li key={`${opening.secret}-${opening.at}`} className="flex flex-wrap gap-x-2">
                <span>{t(`computers.secret.${opening.secret}` as MessageKey)}</span>
                <span className="text-muted">{opening.by?.name ?? t('computers.someone')}</span>
                <span className="text-muted">{formatDate(opening.at)}</span>
                {opening.address && <span className="text-muted">{opening.address}</span>}
              </li>
            ))}
          </ul>
        </Headed>
      )}
    </>
  );
}

function SecretPart({ detail, secret, at }: { detail: Detail; secret: Secret; at: string | null }) {
  const { t, formatDate } = useI18n();
  const opened = useSecretOpened(detail.id);
  return (
    <Headed
      heading={t(`computers.secret.${secret}` as MessageKey)}
      action={
        at &&
        !opened.data && (
          <button
            type="button"
            className={button}
            disabled={opened.isPending}
            onClick={() => opened.mutate(secret)}
          >
            {t('computers.secret.show')}
          </button>
        )
      }
    >
      <p className="text-sm text-muted">
        {at ? `${t('computers.secret.kept')} ${formatDate(at)}` : t('computers.secret.none')}
      </p>
      {opened.data && (
        <output className="block rounded border border-line bg-panel p-3 font-mono text-sm break-all select-all">
          {opened.data.value}
        </output>
      )}
      {opened.error && (
        <p role="alert" className="text-sm text-danger">
          {refusalText(opened.error, t)}
        </p>
      )}
    </Headed>
  );
}

function Removal({ detail }: { detail: Detail }) {
  const { t } = useI18n();
  const removed = useRemoved();
  const navigate = useNavigate();
  const [asking, setAsking] = useState(false);
  return (
    <Headed
      heading={t('computers.remove')}
      action={
        <button type="button" className={dangerButton} onClick={() => setAsking(true)}>
          {t('computers.remove.button')}
        </button>
      }
    >
      {removed.error && (
        <p role="alert" className="text-sm text-danger">
          {refusalText(removed.error, t)}
        </p>
      )}
      {asking && (
        <ConfirmDialog
          heading={t('computers.remove')}
          confirmLabel={t('computers.remove.button')}
          onClose={() => setAsking(false)}
          onConfirm={() =>
            removed.mutate(detail.id, {
              onSuccess: () => navigate('/computers', { replace: true }),
            })
          }
        >
          {t('computers.remove.text').replace('{name}', detail.name)}
        </ConfirmDialog>
      )}
    </Headed>
  );
}

type Network = 'dhcp' | 'static';

function AddDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [made, setMade] = useState<Made | null>(null);
  return (
    <Modal heading={t('computers.add')} wide onClose={onClose}>
      {made ? <Ready made={made} onClose={onClose} /> : <Asked made={setMade} onClose={onClose} />}
    </Modal>
  );
}

function Asked({ made, onClose }: { made: (made: Made) => void; onClose: () => void }) {
  const { t, language } = useI18n();
  const install = useInstall();
  const [answers, setAnswers] = useState<Answers>({
    language,
    keyboard: '',
    role: 'workstation',
    hostname: '',
    network: '',
    wifi: '',
    wifi_password: '',
    ssh_key: [],
    password: '',
    erase: false,
  });
  const [network, setNetwork] = useState<Network>('dhcp');
  const [keys, setKeys] = useState('');
  const [again, setAgain] = useState('');
  const set = <K extends keyof Answers>(key: K, value: Answers[K]) =>
    setAnswers((before) => ({ ...before, [key]: value }));
  const differ = answers.password !== again;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (differ) return;
    const workstation = answers.role === 'workstation';
    install.mutate(
      {
        ...answers,
        hostname: answers.hostname.trim() || 'auto',
        network: network === 'dhcp' ? 'dhcp' : answers.network,
        wifi: workstation ? answers.wifi : '',
        wifi_password: workstation ? answers.wifi_password : '',
        ssh_key: answers.role === 'server' ? keys.split('\n') : [],
      },
      { onSuccess: made },
    );
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Choice
          label={t('computers.install.role')}
          value={answers.role}
          change={(value) => set('role', value)}
          options={[
            ['workstation', 'computers.install.role.workstation'],
            ['server', 'computers.install.role.server'],
          ]}
        />
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('computers.install.hostname')}</span>
          <input
            value={answers.hostname}
            onChange={(event) => set('hostname', event.target.value)}
            placeholder={t('computers.install.hostname.auto')}
            pattern="[A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
            className={field}
          />
        </label>
        <Choice
          label={t('computers.install.language')}
          value={answers.language}
          change={(value) => set('language', value)}
          options={[
            ['hr', 'computers.install.language.hr'],
            ['en', 'computers.install.language.en'],
          ]}
        />
        <Choice
          label={t('computers.install.keyboard')}
          value={answers.keyboard}
          change={(value) => set('keyboard', value)}
          options={[
            ['', 'computers.install.keyboard.language'],
            ['hr', 'computers.install.keyboard.hr'],
            ['us', 'computers.install.keyboard.us'],
          ]}
        />
        <Choice
          label={t('computers.install.network')}
          value={network}
          change={setNetwork}
          options={[
            ['dhcp', 'computers.install.network.dhcp'],
            ['static', 'computers.install.network.static'],
          ]}
        />
        {network === 'static' && (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t('computers.install.address')}</span>
            <input
              value={answers.network}
              onChange={(event) => set('network', event.target.value)}
              placeholder="192.0.2.20/24 gateway 192.0.2.1 dns 1.1.1.1"
              required
              className={field}
            />
          </label>
        )}
        {answers.role === 'workstation' && (
          <>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted">{t('computers.install.wifi')}</span>
              <input
                value={answers.wifi}
                onChange={(event) => set('wifi', event.target.value)}
                maxLength={32}
                className={field}
              />
            </label>
            {answers.wifi && (
              <label className="flex flex-col gap-1 text-sm">
                <span className="text-muted">{t('computers.install.wifiPassword')}</span>
                <input
                  type="password"
                  value={answers.wifi_password}
                  onChange={(event) => set('wifi_password', event.target.value)}
                  minLength={8}
                  maxLength={64}
                  required
                  autoComplete="off"
                  className={field}
                />
              </label>
            )}
          </>
        )}
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('computers.install.password')}</span>
          <input
            type="password"
            value={answers.password}
            onChange={(event) => set('password', event.target.value)}
            minLength={8}
            maxLength={128}
            required
            autoComplete="new-password"
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('computers.install.passwordAgain')}</span>
          <input
            type="password"
            value={again}
            onChange={(event) => setAgain(event.target.value)}
            required
            autoComplete="new-password"
            aria-invalid={differ && again !== ''}
            className={field}
          />
        </label>
      </div>
      {answers.role === 'server' && (
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('computers.install.sshKey')}</span>
          <textarea
            value={keys}
            onChange={(event) => setKeys(event.target.value)}
            rows={3}
            placeholder="ssh-ed25519 AAAA… / https://github.com/…keys"
            className={`${field} font-mono`}
          />
        </label>
      )}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={answers.erase}
          onChange={(event) => set('erase', event.target.checked)}
        />
        {t('computers.install.erase')}
      </label>
      {differ && again !== '' && (
        <p role="alert" className="text-sm text-danger">
          {t('computers.install.passwordDiffers')}
        </p>
      )}
      {install.error && (
        <p role="alert" className="text-sm text-danger">
          {refusalText(install.error, t)}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" className={button} onClick={onClose}>
          {t('tree.cancel')}
        </button>
        <button type="submit" className={primaryButton} disabled={install.isPending || differ}>
          {t('computers.install.make')}
        </button>
      </div>
    </form>
  );
}

function Choice<T extends string>({
  label,
  value,
  change,
  options,
}: {
  label: string;
  value: T;
  change: (value: T) => void;
  options: [T, MessageKey][];
}) {
  const { t } = useI18n();
  return (
    <Labelled label={label}>
      {(labelled) => (
        <select
          id={labelled}
          value={value}
          onChange={(event) => change(event.target.value as T)}
          className={field}
        >
          {options.map(([option, word]) => (
            <option key={option} value={option}>
              {t(word)}
            </option>
          ))}
        </select>
      )}
    </Labelled>
  );
}

function saved(conf: string) {
  const address = URL.createObjectURL(new Blob([conf], { type: 'text/plain' }));
  const link = document.createElement('a');
  link.href = address;
  link.download = 'install.conf';
  link.click();
  URL.revokeObjectURL(address);
}

function Ready({ made, onClose }: { made: Made; onClose: () => void }) {
  const { t, formatDate, formatNumber } = useI18n();
  const sticks = useSticks(true);
  return (
    <div className="flex flex-col gap-4 text-sm">
      <div className="flex flex-col gap-1">
        <span className="text-muted">{t('computers.code')}</span>
        <output className="font-mono text-lg tracking-wider select-all">{made.code}</output>
        <span className="text-muted">
          {t('computers.code.expires')} {formatDate(made.expires_at)}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={primaryButton} onClick={() => saved(made.conf)}>
          {t('computers.install.download')}
        </button>
        <span className="text-muted">{t('computers.install.onStick')}</span>
      </div>
      {sticks.data && (
        <Headed heading={`${t('computers.sticks')} ${sticks.data.version}`}>
          <ul className="flex flex-col gap-1">
            {(['network', 'full'] as const).map((kind) => (
              <li key={kind} className="flex flex-wrap gap-x-2">
                <a href={sticks.data[kind].url} className="text-link hover:underline">
                  {t(`computers.stick.${kind}` as MessageKey)}
                </a>
                <span className="text-muted">
                  {formatSize(sticks.data[kind].size, formatNumber)}
                </span>
              </li>
            ))}
          </ul>
        </Headed>
      )}
      {sticks.error && (
        <p role="alert" className="text-danger">
          {refusalText(sticks.error, t)}
        </p>
      )}
      <div className="flex justify-end">
        <button type="button" className={button} onClick={onClose}>
          {t('computers.close')}
        </button>
      </div>
    </div>
  );
}
