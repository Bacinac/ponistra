import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CircleCheck, CircleX, Copy, Download } from 'lucide-react';
import { useState, type FormEvent, type ReactNode } from 'react';
import { Navigate } from 'react-router';
import { getJson, patchJson, postJson } from './api';
import { useSession } from './auth';
import { Cancel, Close, ConfirmDialog, Labelled, Modal } from './dialogs';
import { formatSize } from './explorer';
import { Loaded } from './frame';
import { AdminFrame } from './settings';
import { useI18n } from './i18n';
import { problemText } from './problems';
import type { MessageKey } from './i18n/hr';
import { button, field, primaryButton } from './styles';
import { errorMessage } from './tree';

type Service = 'database' | 'converter' | 'printer' | 'ocr' | 'meetings' | 'relay' | 'outside';
type Queue = 'jobs' | 'ocr' | 'text' | 'unread' | 'batches';

interface Health {
  version: string;
  /** The relay is there only where the installation has one. */
  services: Partial<Record<Service, boolean>>;
  snapshots:
    | { count: number; newest: string | null; due: string; late: boolean; error?: undefined }
    | { error: string; late: true };
  disks: { holds: ('files' | 'snapshots')[]; free: number; total: number }[];
  archive: { at: string | null; error: string; late: boolean };
  /** Deleted files kept seven days before they go. */
  stored: { database: number; files: number; dead: number };
  queues: Record<Queue, number>;
  offsite: { locked: number; setting: Offsite | null };
  /** What the watch found wrong for longer than its grace, oldest first. */
  problems: { key: string; since: string }[];
}

/** The bucket the snapshots are mirrored to, as the server tells an administrator: never its
    secret, only its last four characters. */
interface Offsite {
  endpoint: string;
  bucket: string;
  access_key: string;
  hint: string;
  lost: boolean;
  /** The day the generation the mirror adds to began, as YYYY-MM-DD. */
  generation: string;
  mirrored_at: string | null;
  /** Whether the bucket refused to delete the generation's canary; null before the first try. */
  protected: boolean | null;
  error: string;
  late: boolean;
  checked_at: string | null;
  check_error: string;
  tried_at: string | null;
  /** What the last trial restore brought back from the bucket. */
  trial: { snapshot: string; time: string; nodes: number; files: number } | null;
  trial_error: string;
}

/** Everything a new server needs to bring the installation back from the bucket, shown once. */
interface Kit {
  endpoint: string;
  bucket: string;
  access_key: string;
  secret: string;
  emergency: string;
}

const SERVICES: Service[] = [
  'database',
  'converter',
  'printer',
  'ocr',
  'meetings',
  'relay',
  'outside',
];
const QUEUES: Queue[] = ['jobs', 'ocr', 'text', 'unread', 'batches'];

const cell = 'px-2 py-2';
const value = `${cell} text-right tabular-nums`;

function Section({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg">{heading}</h2>
      {children}
    </section>
  );
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <tbody>
        {rows.map(([label, shown]) => (
          <tr key={label} className="border-b border-line">
            <td className={`${cell} w-full`}>{label}</td>
            <td className={`${value} whitespace-nowrap`}>{shown}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Verdict({ ok, good, bad }: { ok: boolean; good: MessageKey; bad: MessageKey }) {
  const { t } = useI18n();
  const Icon = ok ? CircleCheck : CircleX;
  return (
    <span className={`inline-flex items-center gap-1.5 ${ok ? '' : 'text-danger'}`}>
      <Icon size={16} aria-hidden className={ok ? 'text-accent' : undefined} />
      {t(ok ? good : bad)}
    </span>
  );
}

function day(given: string): Date {
  const [year, month, date] = given.split('-').map(Number);
  return new Date(year, month - 1, date);
}

function kitText(kit: Kit, heading: string, keep: string): string {
  return [
    `# ${heading}`,
    `# ${keep}`,
    `PONISTRA_OFFSITE_ENDPOINT=${kit.endpoint}`,
    `PONISTRA_OFFSITE_BUCKET=${kit.bucket}`,
    `PONISTRA_OFFSITE_ACCESS_KEY=${kit.access_key}`,
    `PONISTRA_OFFSITE_SECRET=${kit.secret}`,
    `PONISTRA_EMERGENCY_KEY=${kit.emergency}`,
    '',
  ].join('\n');
}

function KitDialog({ kit, onClose }: { kit: Kit; onClose: () => void }) {
  const { t, formatDay } = useI18n();
  const text = kitText(
    kit,
    `Ponistra – ${t('health.kit.title')} – ${location.host} – ${formatDay(new Date())}`,
    t('health.kit.keep'),
  );
  const save = () => {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `ponistra-${location.host}-kit.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Modal heading={t('health.kit.title')} wide onClose={onClose}>
      <p className="text-sm">{t('health.kit.note')}</p>
      <pre className="overflow-x-auto rounded border border-line bg-panel p-3 text-xs">{text}</pre>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={() => void navigator.clipboard.writeText(text)}
          className={`${button} inline-flex items-center gap-1.5`}
        >
          <Copy size={16} aria-hidden />
          {t('health.kit.copy')}
        </button>
        <button
          type="button"
          onClick={save}
          className={`${primaryButton} inline-flex items-center gap-1.5`}
        >
          <Download size={16} aria-hidden />
          {t('health.kit.download')}
        </button>
        <Close />
      </div>
    </Modal>
  );
}

function OffsiteForm({
  setting,
  locked,
  onSaved,
  onClose,
}: {
  setting: Offsite | null;
  locked: number;
  onSaved: (kit: Kit) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [endpoint, setEndpoint] = useState(setting?.endpoint ?? '');
  const [bucket, setBucket] = useState(setting?.bucket ?? '');
  const [accessKey, setAccessKey] = useState(setting?.access_key ?? '');
  const [secret, setSecret] = useState('');
  const save = useMutation({
    mutationFn: () =>
      patchJson<{ kit: Kit }>('/api/backups/offsite', {
        endpoint: endpoint.trim(),
        bucket: bucket.trim(),
        access_key: accessKey.trim(),
        secret: secret.trim() || undefined,
      }),
    onSuccess: ({ kit }) => {
      void queryClient.invalidateQueries({ queryKey: ['health'] });
      onSaved(kit);
    },
  });
  const kept = !!setting && setting.hint !== '' && !setting.lost;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <Modal heading={t('health.offsite')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <p className="text-sm text-muted">
          {t('health.offsite.how')} {locked} {t('health.offsite.howDays')}
        </p>
        <Labelled label={t('health.offsite.endpoint')}>
          {(id) => (
            <input
              id={id}
              required
              type="url"
              maxLength={200}
              spellCheck={false}
              placeholder="https://…eu.r2.cloudflarestorage.com"
              value={endpoint}
              onChange={(event) => setEndpoint(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <Labelled label={t('health.offsite.bucket')}>
          {(id) => (
            <input
              id={id}
              required
              maxLength={63}
              spellCheck={false}
              value={bucket}
              onChange={(event) => setBucket(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <Labelled label={t('health.offsite.accessKey')}>
          {(id) => (
            <input
              id={id}
              required
              maxLength={128}
              spellCheck={false}
              value={accessKey}
              onChange={(event) => setAccessKey(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <Labelled label={t('health.offsite.secret')}>
          {(id) => (
            <input
              id={id}
              type="password"
              required={!kept}
              maxLength={256}
              autoComplete="new-password"
              spellCheck={false}
              value={secret}
              placeholder={kept ? t('health.offsite.secretReplace') : undefined}
              onChange={(event) => setSecret(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        {kept && (
          <p className="-mt-2 text-xs text-muted">
            {t('health.offsite.secretKept')} …{setting.hint}
          </p>
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t(save.isPending ? 'health.offsite.checking' : 'health.offsite.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function OffsiteSection({ offsite }: { offsite: Health['offsite'] }) {
  const { t, formatDate, formatDay, formatNumber } = useI18n();
  const [editing, setEditing] = useState(false);
  const [renewing, setRenewing] = useState(false);
  const [kit, setKit] = useState<Kit | null>(null);
  const renew = useMutation({
    mutationFn: () => postJson<{ kit: Kit }>('/api/backups/offsite/kit'),
    onSuccess: (made) => {
      setRenewing(false);
      setKit(made.kit);
    },
  });
  const { setting, locked } = offsite;
  return (
    <Section heading={t('health.offsite')}>
      <p className="text-sm text-muted">{t('health.offsite.note')}</p>
      {setting === null ? (
        <p className="text-sm text-danger">{t('health.offsite.none')}</p>
      ) : (
        <>
          {setting.error && (
            <p className="text-sm text-danger">
              {t('health.offsite.error')} {setting.error}
            </p>
          )}
          {!setting.error && setting.late && (
            <p className="text-sm text-danger">{t('health.offsite.late')}</p>
          )}
          {setting.protected === false && (
            <p className="text-sm text-danger">
              {t('health.offsite.unprotectedNote')} {locked} {t('health.offsite.howDays')}
            </p>
          )}
          {setting.lost && <p className="text-sm text-danger">{t('health.offsite.secretLost')}</p>}
          {setting.check_error && (
            <p className="text-sm text-danger">
              {t('health.offsite.checkError')} {setting.check_error}
            </p>
          )}
          {setting.trial_error && (
            <p className="text-sm text-danger">
              {t('health.offsite.trialError')} {setting.trial_error}
            </p>
          )}
          <Rows
            rows={[
              [t('health.offsite.bucket'), setting.bucket],
              [
                t('health.offsite.generation'),
                setting.generation ? formatDay(day(setting.generation)) : '–',
              ],
              [
                t('health.offsite.mirrored'),
                setting.mirrored_at ? formatDate(setting.mirrored_at) : '–',
              ],
              [
                t('health.offsite.protection'),
                setting.protected === null ? (
                  '–'
                ) : (
                  <Verdict
                    ok={setting.protected}
                    good="health.offsite.protected"
                    bad="health.offsite.unprotected"
                  />
                ),
              ],
              [
                t('health.offsite.checked'),
                setting.checked_at ? formatDate(setting.checked_at) : '–',
              ],
              [t('health.offsite.tried'), setting.tried_at ? formatDate(setting.tried_at) : '–'],
            ]}
          />
          {setting.trial && !setting.trial_error && (
            <p className="text-sm text-muted">
              {t('health.offsite.trialFrom')} {formatDate(setting.trial.time)}
              {t('health.offsite.trialNodes')} {formatNumber(setting.trial.nodes)}
              {t('health.offsite.trialFiles')} {formatNumber(setting.trial.files)}
              {t('health.offsite.trialWhole')}
            </p>
          )}
        </>
      )}
      {renew.isError && <p className="text-sm text-danger">{errorMessage(renew.error, t)}</p>}
      <div className="flex justify-end gap-2">
        {setting && (
          <button type="button" onClick={() => setRenewing(true)} className={button}>
            {t('health.kit.renew')}
          </button>
        )}
        <button type="button" onClick={() => setEditing(true)} className={primaryButton}>
          {t(setting ? 'health.offsite.change' : 'health.offsite.set')}
        </button>
      </div>
      {editing && (
        <OffsiteForm
          setting={setting}
          locked={locked}
          onSaved={(made) => {
            setEditing(false);
            setKit(made);
          }}
          onClose={() => setEditing(false)}
        />
      )}
      {renewing && (
        <ConfirmDialog
          heading={t('health.kit.renew')}
          confirmLabel={t('health.kit.renewConfirm')}
          onConfirm={() => renew.mutate()}
          onClose={() => setRenewing(false)}
        >
          {t('health.kit.renewWarning')}
        </ConfirmDialog>
      )}
      {kit && <KitDialog kit={kit} onClose={() => setKit(null)} />}
    </Section>
  );
}

function diskLabel(holds: Health['disks'][number]['holds']): MessageKey {
  if (holds.length > 1) return 'health.disk.both';
  return holds[0] === 'files' ? 'health.disk.files' : 'health.disk.snapshots';
}

function Report({ health }: { health: Health }) {
  const { t, formatDate, formatNumber } = useI18n();
  const size = (bytes: number) => formatSize(bytes, formatNumber);
  const { snapshots } = health;
  return (
    <AdminFrame title={t('health.title')}>
      <div className="flex w-full max-w-3xl flex-col gap-8">
        <p className="text-sm text-muted">
          {t('status.version')} {health.version}
        </p>
        {health.problems.length > 0 && (
          <Section heading={t('health.problems')}>
            <Rows
              rows={health.problems.map(({ key, since }) => [
                problemText(key, t),
                <span className="text-danger">
                  {t('health.problems.since')} {formatDate(since)}
                </span>,
              ])}
            />
          </Section>
        )}
        <Section heading={t('health.services')}>
          <Rows
            rows={SERVICES.filter((service) => service in health.services).map((service) => [
              t(`health.service.${service}`),
              <Verdict
                ok={health.services[service] === true}
                good="health.answers"
                bad="health.silent"
              />,
            ])}
          />
        </Section>
        <Section heading={t('health.snapshots')}>
          <p className="text-sm text-muted">{t('health.snapshots.note')}</p>
          {snapshots.error !== undefined ? (
            <p className="text-sm text-danger">
              {t('health.snapshots.error')} {snapshots.error}
            </p>
          ) : (
            <>
              {snapshots.late && (
                <p className="text-sm text-danger">
                  {t(snapshots.newest ? 'health.snapshots.late' : 'health.snapshots.none')}
                </p>
              )}
              <Rows
                rows={[
                  [
                    t('health.snapshots.newest'),
                    snapshots.newest ? formatDate(snapshots.newest) : '–',
                  ],
                  [t('health.snapshots.due'), formatDate(snapshots.due)],
                  [t('health.snapshots.count'), formatNumber(snapshots.count)],
                  [
                    t('health.snapshots.archived'),
                    health.archive.at ? formatDate(health.archive.at) : '–',
                  ],
                ]}
              />
            </>
          )}
          {health.archive.error ? (
            <p className="text-sm text-danger">
              {t('health.snapshots.archiveError')} {health.archive.error}
            </p>
          ) : (
            health.archive.late && (
              <p className="text-sm text-danger">{t('health.snapshots.archiveLate')}</p>
            )
          )}
        </Section>
        <OffsiteSection offsite={health.offsite} />
        <Section heading={t('health.storage')}>
          <Rows
            rows={[
              [t('health.stored.database'), size(health.stored.database)],
              [t('health.stored.files'), size(health.stored.files)],
              [t('health.stored.dead'), size(health.stored.dead)],
              ...health.disks.map((disk): [string, ReactNode] => [
                t(diskLabel(disk.holds)),
                `${size(disk.free)} ${t('health.disk.freeOf')} ${size(disk.total)}`,
              ]),
            ]}
          />
        </Section>
        <Section heading={t('health.queues')}>
          <Rows
            rows={QUEUES.map((queue) => [
              t(`health.queue.${queue}`),
              formatNumber(health.queues[queue]),
            ])}
          />
        </Section>
      </div>
    </AdminFrame>
  );
}

export function HealthPage() {
  const me = useSession().data?.user;
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => getJson<Health>('/api/health'),
    enabled: !!me?.is_admin,
    refetchInterval: 30_000,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return <Loaded query={health}>{(data) => <Report health={data} />}</Loaded>;
}
