import { LoaderCircle } from 'lucide-react';
import { useSyncExternalStore } from 'react';
import { ApiError, deleteJson, getJson, postJson } from './api';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';

/** What the server does in its queue (apps/jobs) rather than in one request, which the proxies
 * in front of it cut off after a minute or two. */
export type JobKind =
  | 'docx'
  | 'docm'
  | 'pdf'
  | 'xlsx'
  | 'csv'
  | 'xlsm'
  | 'pptx'
  | 'pptm'
  | 'ponx'
  | 'import'
  | 'into'
  | 'reimport'
  | 'copy'
  | 'compose'
  | 'redact'
  | 'scan'
  | 'links'
  | 'personal'
  | 'mail-move';

interface Job {
  id: string;
  kind: JobKind;
  state: 'waiting' | 'running' | 'done' | 'failed' | 'cancelled';
  status: number | null;
  error: string | null;
  answer: unknown;
  file: boolean;
  cancellable: boolean;
}

interface Shown {
  job: Job;
  name: string;
}

const CHECK_EVERY = 1000;
const UNDER_WAY = new Set<Job['state']>(['waiting', 'running']);

let shown: readonly Shown[] = [];
const listeners = new Set<() => void>();

function publish(next: readonly Shown[]) {
  shown = next;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => void listeners.delete(listener);
}

/** The job handed over and followed until it ends; it is shown only once it has taken longer
 * than a check, so that a quick one does not flash past. */
async function followed(kind: JobKind, parameters: object, name: string): Promise<Job> {
  let job = await postJson<Job>('/api/jobs', { kind, ...parameters });
  try {
    while (UNDER_WAY.has(job.state) && job.answer === null) {
      await new Promise((resolve) => setTimeout(resolve, CHECK_EVERY));
      job = await getJson<Job>(`/api/jobs/${job.id}`);
      const id = job.id;
      const others = shown.filter((each) => each.job.id !== id);
      publish(UNDER_WAY.has(job.state) ? [...others, { job, name }] : others);
    }
  } finally {
    const id = job.id;
    if (shown.some((each) => each.job.id === id))
      publish(shown.filter((each) => each.job.id !== id));
  }
  if (job.state !== 'done' && job.answer === null)
    throw new ApiError(`/api/jobs/${job.id}`, job.status ?? 409, job.error ?? job.state);
  return job;
}

/** What the job answered: the document, file or tab it made. */
export async function runJob<T>(kind: JobKind, parameters: object, name: string): Promise<T> {
  return (await followed(kind, parameters, name)).answer as T;
}

/** The file the job made, which the browser saves as it downloads it. */
export async function saveJob(kind: JobKind, parameters: object, name: string): Promise<void> {
  const job = await followed(kind, parameters, name);
  Object.assign(document.createElement('a'), {
    href: `/api/jobs/${job.id}/file?download=1`,
    download: name,
  }).click();
}

const DOING: Record<JobKind, MessageKey> = {
  docx: 'job.saving',
  docm: 'job.saving',
  pdf: 'job.saving',
  xlsx: 'job.saving',
  csv: 'job.saving',
  xlsm: 'job.saving',
  pptx: 'job.saving',
  pptm: 'job.saving',
  ponx: 'job.saving',
  import: 'job.import',
  into: 'job.import',
  reimport: 'job.import',
  copy: 'job.copy',
  compose: 'job.compose',
  redact: 'job.redact',
  scan: 'job.scan',
  links: 'job.import',
  personal: 'job.saving',
  'mail-move': 'job.mailMove',
};

async function cancel(job: Job) {
  try {
    await deleteJson(`/api/jobs/${job.id}`);
  } catch (error) {
    // It started a moment ago and makes what cannot be unmade; it goes on, shown as it runs.
    if (!(error instanceof ApiError && error.code === 'not_cancellable')) throw error;
  }
}

/** The user's jobs under way in this window, each with Cancel while it may be given up. */
export function JobBar() {
  const { t } = useI18n();
  const jobs = useSyncExternalStore(subscribe, () => shown);
  if (jobs.length === 0) return null;
  return (
    <div
      role="status"
      className="fixed right-4 bottom-4 z-40 flex max-w-[calc(100vw-2rem)] flex-col gap-1 rounded-lg border border-line bg-raised px-3 py-2 text-sm text-ink shadow-lg"
    >
      {jobs.map(({ job, name }) => (
        <p key={job.id} className="flex items-center gap-2">
          <LoaderCircle aria-hidden className="size-4 shrink-0 animate-spin text-muted" />
          <span className="truncate">
            {t(DOING[job.kind])}: {name}
            <span className="text-muted"> · {t(`job.${job.state as 'waiting' | 'running'}`)}</span>
          </span>
          {job.cancellable && (
            <button
              type="button"
              onClick={() => void cancel(job)}
              className="shrink-0 rounded px-2 py-1 font-medium text-link hover:bg-hover"
            >
              {t('tree.cancel')}
            </button>
          )}
        </p>
      ))}
    </div>
  );
}
