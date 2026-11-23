import { useMutation, useQuery } from '@tanstack/react-query';
import { ChevronRight, Link2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Close, Modal } from './dialogs';
import { formatSize } from './explorer';
import type { FileEntry, FileSource, FileStat } from './files';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { button, field } from './styles';
import { errorMessage } from './tree';

/** The folders from the source's top down to the one shown, each a step back to it; a click
 * beside them, or on the pencil of a keyboard, turns them into the path to type. */
export function AddressBar({
  source,
  path,
  onGo,
}: {
  source: FileSource;
  path: string;
  onGo: (path: string) => void;
}) {
  const { t } = useI18n();
  const [typing, setTyping] = useState<string | null>(null);
  const parts = path ? path.split('/') : [];
  const labels = useQuery({
    queryKey: ['files', source.key, 'labels', path],
    queryFn: () => source.labels!(path),
    enabled: Boolean(source.labels && path),
    staleTime: 60_000,
  });
  const typed = !source.labels;
  if (typing !== null)
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setTyping(null);
          onGo(
            typing
              .split('/')
              .filter((part) => part && part !== '.')
              .join('/'),
          );
        }}
        className="min-w-0 flex-1"
      >
        <input
          autoFocus
          aria-label={t('files.address')}
          value={typing}
          onChange={(event) => setTyping(event.target.value)}
          onBlur={() => setTyping(null)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setTyping(null);
          }}
          className={`${field} w-full font-mono text-sm`}
        />
      </form>
    );
  const crumb = 'shrink-0 truncate rounded px-1 hover:bg-hover max-w-48';
  return (
    <nav
      aria-label={t('files.address')}
      onClick={(event) => {
        if (typed && event.target === event.currentTarget) setTyping(`/${path}`);
      }}
      className={`flex min-h-9 min-w-0 flex-1 items-center gap-1 overflow-hidden rounded px-1 text-sm text-muted ${typed ? 'cursor-text hover:bg-hover/50' : ''}`}
    >
      <button type="button" onClick={() => onGo('')} className={crumb}>
        {source.name}
      </button>
      {parts.map((part, index) => (
        <span key={index} className="flex min-w-0 items-center gap-1">
          <ChevronRight size={14} aria-hidden className="shrink-0" />
          <button
            type="button"
            aria-current={index === parts.length - 1 ? 'page' : undefined}
            onClick={() => onGo(parts.slice(0, index + 1).join('/'))}
            className={`${crumb} aria-[current]:text-ink`}
          >
            {labels.data?.[index] ?? (source.labels ? '…' : part)}
          </button>
        </span>
      ))}
      {typed && (
        <button
          type="button"
          onClick={() => setTyping(`/${path}`)}
          className="sr-only focus:not-sr-only"
        >
          {t('files.typePath')}
        </button>
      )}
    </nav>
  );
}

const BITS: { label: MessageKey; shift: number }[] = [
  { label: 'files.mode.owner', shift: 6 },
  { label: 'files.mode.group', shift: 3 },
  { label: 'files.mode.others', shift: 0 },
];
const RIGHTS: { label: MessageKey; bit: number }[] = [
  { label: 'files.mode.read', bit: 4 },
  { label: 'files.mode.write', bit: 2 },
  { label: 'files.mode.run', bit: 1 },
];

const octal = (mode: number) => (mode & 0o7777).toString(8).padStart(4, '0');

function ModeForm({
  source,
  path,
  stat,
  onChanged,
}: {
  source: FileSource;
  path: string;
  stat: FileStat;
  onChanged: (stat: FileStat) => void;
}) {
  const { t } = useI18n();
  const [mode, setMode] = useState(stat.mode!);
  const change = useMutation({
    mutationFn: () => source.mode!(path, mode),
    onSuccess: onChanged,
  });
  return (
    <form
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        change.mutate();
      }}
      className="flex flex-col gap-2"
    >
      <table className="text-sm">
        <thead>
          <tr className="text-muted">
            <th />
            {RIGHTS.map(({ label }) => (
              <th key={label} className="px-2 font-normal">
                {t(label)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {BITS.map(({ label, shift }) => (
            <tr key={label}>
              <th className="pr-2 text-left font-normal text-muted">{t(label)}</th>
              {RIGHTS.map(({ label: right, bit }) => (
                <td key={right} className="px-2 text-center">
                  <input
                    type="checkbox"
                    aria-label={`${t(label)}: ${t(right)}`}
                    checked={Boolean(mode & (bit << shift))}
                    onChange={() => setMode(mode ^ (bit << shift))}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-2">
        <span className="font-mono text-sm">{octal(mode)}</span>
        <div className="flex-1" />
        <button type="submit" disabled={mode === stat.mode || change.isPending} className={button}>
          {t('tree.save')}
        </button>
      </div>
      {change.error && (
        <p role="alert" className="text-sm text-danger">
          {errorMessage(change.error, t)}
        </p>
      )}
    </form>
  );
}

function OwnerForm({
  source,
  path,
  stat,
  onChanged,
}: {
  source: FileSource;
  path: string;
  stat: FileStat;
  onChanged: (stat: FileStat) => void;
}) {
  const { t } = useI18n();
  const [uid, setUid] = useState(String(stat.uid));
  const [gid, setGid] = useState(String(stat.gid));
  const valid = /^\d+$/.test(uid) && /^\d+$/.test(gid);
  const change = useMutation({
    mutationFn: () => source.owner!(path, Number(uid), Number(gid)),
    onSuccess: onChanged,
  });
  return (
    <form
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        if (valid) change.mutate();
      }}
      className="flex flex-col gap-2"
    >
      <div className="flex items-center gap-2 text-sm">
        <label className="flex items-center gap-1">
          <span className="text-muted">UID</span>
          <input
            inputMode="numeric"
            value={uid}
            onChange={(event) => setUid(event.target.value)}
            className={`${field} w-20`}
          />
        </label>
        <label className="flex items-center gap-1">
          <span className="text-muted">GID</span>
          <input
            inputMode="numeric"
            value={gid}
            onChange={(event) => setGid(event.target.value)}
            className={`${field} w-20`}
          />
        </label>
        <div className="flex-1" />
        <button
          type="submit"
          disabled={
            !valid || change.isPending || (Number(uid) === stat.uid && Number(gid) === stat.gid)
          }
          className={button}
        >
          {t('files.changeOwner')}
        </button>
      </div>
      {change.error && (
        <p role="alert" className="text-sm text-danger">
          {errorMessage(change.error, t)}
        </p>
      )}
    </form>
  );
}

/** What a source tells of a file or a folder: its kind, size, dates, owner and mode, a folder's
 * size with all it holds, a file's checksum; the mode changed where the source allows. */
export function Properties({
  source,
  path,
  entry,
  onClose,
}: {
  source: FileSource;
  path: string;
  entry: FileEntry;
  onClose: () => void;
}) {
  const { t, formatDate, formatNumber } = useI18n();
  const stat = useQuery({
    queryKey: ['files', source.key, 'stat', path],
    queryFn: () => source.stat!(path),
    enabled: Boolean(source.stat),
  });
  const [changed, setChanged] = useState<FileStat | null>(null);
  const shown = changed ?? stat.data;
  const folder = entry.kind === 'folder';
  const size = useMutation({ mutationFn: () => source.folderSize!(path) });
  const sum = useMutation({ mutationFn: () => source.checksum!(path, 'sha256') });
  const line = (label: MessageKey, value: string | null | undefined) =>
    value ? (
      <>
        <dt className="text-muted">{t(label)}</dt>
        <dd className="min-w-0 break-words">{value}</dd>
      </>
    ) : null;
  return (
    <Modal heading={entry.label ?? entry.name} onClose={onClose}>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {line('files.where', `${source.name}/${path}`)}
        {entry.link && (
          <>
            <dt className="text-muted">{t('files.link')}</dt>
            <dd className="flex min-w-0 items-center gap-1 font-mono text-xs break-all">
              <Link2 size={14} aria-hidden className="shrink-0" />
              {entry.link}
            </dd>
          </>
        )}
        {!folder &&
          line('explorer.size', entry.size !== null ? formatSize(entry.size, formatNumber) : null)}
        {line('explorer.updated', entry.modified && formatDate(entry.modified))}
        {shown &&
          line(
            'files.owner',
            [shown.owner ?? shown.uid, shown.group ?? shown.gid]
              .filter((part) => part !== null && part !== undefined)
              .join(' : '),
          )}
        {shown?.mode !== null && shown?.mode !== undefined && line('files.mode', octal(shown.mode))}
        {shown?.attributes?.length ? line('files.attributes', shown.attributes.join(', ')) : null}
      </dl>
      {stat.error && <p className="text-sm text-danger">{errorMessage(stat.error, t)}</p>}
      {folder && source.folderSize && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {size.data ? (
            <span>
              {`${formatSize(size.data.size, formatNumber)} · ${t('files.counted')
                .replace('{files}', formatNumber(size.data.files))
                .replace('{folders}', formatNumber(size.data.folders))}`}
              {size.data.partial && ` (${t('files.partial')})`}
            </span>
          ) : (
            <button
              type="button"
              disabled={size.isPending}
              onClick={() => size.mutate()}
              className={button}
            >
              {t(size.isPending ? 'files.counting' : 'files.folderSize')}
            </button>
          )}
          {size.error && <span className="text-danger">{errorMessage(size.error, t)}</span>}
        </div>
      )}
      {!folder && source.checksum && (
        <div className="flex flex-col items-start gap-1 text-sm">
          {sum.data ? (
            <>
              <span className="text-muted">{sum.data.algorithm.toUpperCase()}</span>
              <code className="font-mono text-xs break-all select-all">{sum.data.digest}</code>
            </>
          ) : (
            <button
              type="button"
              disabled={sum.isPending}
              onClick={() => sum.mutate()}
              className={button}
            >
              {t(sum.isPending ? 'files.summing' : 'files.checksum')}
            </button>
          )}
          {sum.error && <span className="text-danger">{errorMessage(sum.error, t)}</span>}
        </div>
      )}
      {source.mode && shown && shown.mode !== null && (
        <ModeForm
          key={shown.mode}
          source={source}
          path={path}
          stat={shown}
          onChanged={setChanged}
        />
      )}
      {source.owner && shown && shown.uid !== null && shown.gid !== null && (
        <OwnerForm
          key={`${shown.uid}:${shown.gid}`}
          source={source}
          path={path}
          stat={shown}
          onChanged={setChanged}
        />
      )}
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}
