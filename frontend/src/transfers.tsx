import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Check, CircleAlert, LoaderCircle, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { deleteJson, getJson, postJson } from './api';
import { useVisitor } from './auth';
import { formatSize } from './explorer';
import type { FileSource } from './files';
import { useI18n } from './i18n';
import { iconButton } from './styles';
import { codeText } from './tree';

/** What a name the target already holds becomes, one answer for the whole transfer. */
export type Conflict = 'skip' | 'replace' | 'keep';

interface Progress {
  files: number;
  bytes: number;
  of_files: number;
  of_bytes: number;
  skipped: number;
  at: string;
  running: boolean;
}

interface Transfer {
  id: string;
  state: 'waiting' | 'running' | 'done' | 'failed' | 'cancelled';
  error: string | null;
  answer: Progress | Record<string, never> | null;
  cancellable: boolean;
  from: string;
  from_name: string;
  to: string;
  to_name: string;
  path: string;
  paths: number;
  move: boolean;
}

const TRANSFERS = ['transfers'];
const CHECK_EVERY = 1000;
const UNDER_WAY = new Set<Transfer['state']>(['waiting', 'running']);
const listeners = new Set<() => void>();
/** The transfers this window started, shown and followed even where they end before a check. */
const begun = new Set<string>();

const within = (folder: string, name: string) => (folder ? `${folder}/${name}` : name);
const above = (path: string) => path.replace(/\/?[^/]*$/, '');
const last = (path: string) => path.split('/').pop() ?? path;
const tree = (source: FileSource) => source.key.startsWith('ponistra:');
/** A name as Ponistra's tree holds it: a file's title, without its extension. */
const titled = (name: string) => name.replace(/(?<=.)\.[^.]{1,10}$/, '').toLocaleLowerCase('hr');

/** Copies or moves the entries into the folder of the other source, or of the same one, as a
 * job of the backend; a move within one source is a rename of that source instead. */
export async function startTransfer({
  from,
  paths,
  to,
  path,
  move,
  conflict,
}: {
  from: FileSource;
  paths: string[];
  to: FileSource;
  path: string;
  move: boolean;
  conflict: Conflict | null;
}): Promise<unknown> {
  const started = await postJson<Transfer>('/api/jobs', {
    kind: 'transfer',
    from: from.key,
    paths,
    to: to.key,
    path,
    move,
    conflict,
  });
  begun.add(started.id);
  for (const listener of listeners) listener();
  return started;
}

/** The names of the entries chosen that the target folder already holds, which the page asks
 * about once before the transfer starts. */
export async function conflictsOf(
  from: FileSource,
  paths: string[],
  to: FileSource,
  path: string,
): Promise<string[]> {
  const folders = [...new Set(paths.map(above))];
  const listed = await Promise.all(folders.map((folder) => from.list(folder)));
  const shown = new Map<string, string>();
  listed.forEach(({ entries }, at) => {
    for (const entry of entries)
      shown.set(within(folders[at], entry.name), entry.fileName ?? entry.label ?? entry.name);
  });
  const names = paths.map((each) => shown.get(each) ?? last(each));
  const held = (await to.list(path)).entries.map(
    (entry) => entry.fileName ?? entry.label ?? entry.name,
  );
  if (tree(to)) {
    const titles = new Set(held.map((each) => each.toLocaleLowerCase('hr')));
    return names.filter((name) => titles.has(titled(name)));
  }
  const taken = new Set(held);
  return names.filter((name) => taken.has(name));
}

function useTransfers() {
  const client = useQueryClient();
  const visitor = useVisitor();
  useEffect(() => {
    const woken = () => void client.invalidateQueries({ queryKey: TRANSFERS });
    listeners.add(woken);
    return () => void listeners.delete(woken);
  }, [client]);
  return useQuery({
    queryKey: TRANSFERS,
    queryFn: () => getJson<{ transfers: Transfer[] }>('/api/files/transfers'),
    enabled: !visitor,
    refetchInterval: (query) =>
      query.state.data?.transfers.some((each) => UNDER_WAY.has(each.state)) ? CHECK_EVERY : false,
  });
}

/** The folders a transfer that ended changed are listed anew. */
function useEnded(transfers: Transfer[]) {
  const client = useQueryClient();
  const seen = useRef(new Map<string, Transfer['state']>());
  useEffect(() => {
    for (const each of transfers) {
      const before = seen.current.get(each.id) ?? (begun.has(each.id) ? 'waiting' : undefined);
      seen.current.set(each.id, each.state);
      if (before === undefined || !UNDER_WAY.has(before) || UNDER_WAY.has(each.state)) continue;
      void client.invalidateQueries({ queryKey: ['files', each.to] });
      if (each.move) void client.invalidateQueries({ queryKey: ['files', each.from] });
    }
  }, [transfers, client]);
}

function Shown({ transfer, onDismiss }: { transfer: Transfer; onDismiss: () => void }) {
  const { t, formatNumber } = useI18n();
  const progress = transfer.answer && 'files' in transfer.answer ? transfer.answer : null;
  const going = UNDER_WAY.has(transfer.state);
  const share = progress
    ? progress.of_bytes
      ? progress.bytes / progress.of_bytes
      : progress.of_files
        ? progress.files / progress.of_files
        : 0
    : 0;
  const counted = (
    key: 'transfers.items' | 'transfers.files' | 'transfers.skipped',
    count: number,
  ) => t(key).replace('{count}', formatNumber(count));
  return (
    <li className="flex flex-col gap-1 rounded-md border border-line px-3 py-2 text-sm">
      <div className="flex min-w-0 items-center gap-2">
        {going ? (
          <LoaderCircle aria-hidden className="size-4 shrink-0 animate-spin text-muted" />
        ) : transfer.state === 'done' ? (
          <Check aria-hidden className="size-4 shrink-0 text-accent" />
        ) : (
          <CircleAlert aria-hidden className="size-4 shrink-0 text-danger" />
        )}
        <span className="shrink-0 font-medium">
          {t(transfer.move ? 'transfers.move' : 'transfers.copy')}
        </span>
        <span className="truncate">{counted('transfers.items', transfer.paths)}</span>
        <span className="flex min-w-0 items-center gap-1 text-muted">
          <span className="truncate">{transfer.from_name}</span>
          <ArrowRight aria-hidden className="size-3 shrink-0" />
          <span className="truncate">{transfer.to_name}</span>
        </span>
        <div className="flex-1" />
        {going && transfer.cancellable && (
          <button
            type="button"
            onClick={() => void deleteJson(`/api/jobs/${transfer.id}`)}
            className="shrink-0 rounded px-2 py-1 font-medium text-link hover:bg-hover"
          >
            {t('tree.cancel')}
          </button>
        )}
        {!going && (
          <button
            type="button"
            aria-label={t('transfers.dismiss')}
            title={t('transfers.dismiss')}
            onClick={onDismiss}
            className={iconButton}
          >
            <X size={14} aria-hidden />
          </button>
        )}
      </div>
      {going && (
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(share * 100)}
          className="h-1.5 overflow-hidden rounded bg-line"
        >
          <div className="h-full bg-accent" style={{ width: `${share * 100}%` }} />
        </div>
      )}
      {progress && (
        <p className="truncate text-muted">
          {formatNumber(progress.files)} / {counted('transfers.files', progress.of_files)}
          {progress.of_bytes > 0 &&
            ` · ${formatSize(progress.bytes, formatNumber)} / ${formatSize(progress.of_bytes, formatNumber)}`}
          {progress.skipped > 0 && ` · ${counted('transfers.skipped', progress.skipped)}`}
          {going && progress.at && ` · ${progress.at}`}
        </p>
      )}
      {transfer.state === 'waiting' && <p className="text-muted">{t('job.waiting')}</p>}
      {transfer.state === 'failed' && (
        <p role="alert" className="text-danger">
          {codeText(transfer.error ?? 'unexpected', t)}
        </p>
      )}
      {transfer.state === 'cancelled' && <p className="text-muted">{t('transfers.cancelled')}</p>}
    </li>
  );
}

/** The queue of transfers: those under way with how far they have come, and those ended
 * lately until they are put away. */
export function Transfers() {
  const { t } = useI18n();
  const found = useTransfers();
  const transfers = found.data?.transfers ?? [];
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  useEnded(transfers);
  const shown = transfers.filter(
    (each) => (begun.has(each.id) || UNDER_WAY.has(each.state)) && !dismissed.has(each.id),
  );
  if (shown.length === 0) return null;
  return (
    <section aria-label={t('transfers.title')} className="flex flex-col gap-1">
      <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto">
        {shown.map((each) => (
          <Shown
            key={each.id}
            transfer={each}
            onDismiss={() => setDismissed((now) => new Set(now).add(each.id))}
          />
        ))}
      </ul>
    </section>
  );
}
