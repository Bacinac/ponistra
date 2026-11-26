import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { ConfirmDialog } from '../dialogs';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import { button, iconButton } from '../styles';
import {
  MachineError,
  snapshotPath,
  useMachineWrite,
  useSnapshotFiles,
  type SnapshotFile,
} from './api';
import { Failure, table, useFormats } from './parts';
import { CopySnapshot } from './Snapshots';

const join = (folder: string, name: string) => `${folder.replace(/\/$/, '')}/${name}`;

export function SnapshotFiles() {
  const { t } = useI18n();
  const format = useFormats();
  const navigate = useNavigate();
  const { name = '', snapshot = '' } = useParams();
  const [search, setSearch] = useSearchParams();
  const path = search.get('path') || '/';
  const files = useSnapshotFiles(name, snapshot, path);
  const [asked, setAsked] = useState<string | null>(null);
  const [copying, setCopying] = useState(false);
  const restore = useMachineWrite((api, restored: string) =>
    api.send<{ path: string; previous?: string }>(
      'POST',
      `${snapshotPath(name, snapshot)}/files/restore`,
      { path: restored },
    ),
  );
  const open = (next: string) => setSearch(next === '/' ? {} : { path: next });
  const steps = path.split('/').filter(Boolean);
  const virtual = files.error instanceof MachineError && files.error.status === 409;
  const foreign = files.error instanceof MachineError && files.error.status === 403;
  const sorted = [...(files.data ?? [])].sort(
    (a, b) => Number(b.type === 'dir') - Number(a.type === 'dir') || a.name.localeCompare(b.name),
  );

  return (
    <div className="flex flex-col gap-6">
      <Link to="../.." relative="path" className="text-sm text-link hover:underline">
        ← {name}
      </Link>
      <Headed
        heading={`${t('machine.files')} · ${snapshot}`}
        action={
          <button type="button" className={button} onClick={() => setCopying(true)}>
            {t('machine.snapshot.copy')}
          </button>
        }
      >
        <nav
          aria-label={t('machine.files.path')}
          className="flex flex-wrap items-center gap-1 font-mono text-sm"
        >
          <button type="button" className="text-link hover:underline" onClick={() => open('/')}>
            /
          </button>
          {steps.map((step, index) => (
            <span key={index} className="flex items-center gap-1">
              <button
                type="button"
                className="text-link hover:underline"
                onClick={() => open(`/${steps.slice(0, index + 1).join('/')}`)}
              >
                {step}
              </button>
              {index < steps.length - 1 && <span className="text-muted">/</span>}
            </span>
          ))}
        </nav>
        {restore.data && (
          <p role="status" className="text-sm">
            {t('machine.files.restored').replace('{path}', restore.data.path)}
            {restore.data.previous &&
              ` ${t('machine.files.previous').replace('{previous}', restore.data.previous)}`}
          </p>
        )}
        {restore.isPending && (
          <p role="status" className="text-sm text-muted">
            {t('machine.files.restoring')}
          </p>
        )}
        <Failure error={restore.error} />
        {virtual ? (
          <p className="text-sm">{t('machine.files.virtual')}</p>
        ) : foreign ? (
          <p className="text-sm">{t('machine.guest.foreignFiles')}</p>
        ) : files.error ? (
          <Failure error={files.error} />
        ) : !files.data ? (
          <p className="text-sm text-muted">{t('machine.files.preparing')}</p>
        ) : sorted.length === 0 ? (
          <p className="text-sm text-muted">{t('machine.files.empty')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className={table}>
              <thead>
                <tr>
                  <th>{t('machine.files.name')}</th>
                  <th>{t('machine.size')}</th>
                  <th>{t('machine.files.mode')}</th>
                  <th>{t('machine.files.owner')}</th>
                  <th>{t('machine.files.modified')}</th>
                  <th>
                    <span className="sr-only">{t('machine.actions')}</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((file) => (
                  <FileRow
                    key={file.name}
                    file={file}
                    format={format}
                    open={() => open(join(path, file.name))}
                    restore={() => setAsked(join(path, file.name))}
                    busy={restore.isPending}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Headed>
      {asked && (
        <ConfirmDialog
          heading={t('machine.files.restoreHeading')}
          confirmLabel={t('machine.files.restore')}
          onConfirm={() => restore.mutate(asked)}
          onClose={() => setAsked(null)}
        >
          {t('machine.files.restoreText').replace('{path}', asked).replace('{guest}', name)}
        </ConfirmDialog>
      )}
      {copying && (
        <CopySnapshot
          guest={name}
          snapshot={snapshot}
          onClose={() => setCopying(false)}
          copied={(copy) => navigate(`../../../${encodeURIComponent(copy)}`, { relative: 'path' })}
        />
      )}
    </div>
  );
}

function FileRow({
  file,
  format,
  open,
  restore,
  busy,
}: {
  file: SnapshotFile;
  format: ReturnType<typeof useFormats>;
  open: () => void;
  restore: () => void;
  busy: boolean;
}) {
  const { t } = useI18n();
  return (
    <tr>
      <td className="font-mono text-xs">
        {file.type === 'dir' ? (
          <button type="button" className="text-link hover:underline" onClick={open}>
            {file.name}/
          </button>
        ) : (
          file.name
        )}
        {file.type === 'link' && <span className="text-muted"> → {file.target}</span>}
      </td>
      <td className="tabular-nums">{file.type === 'file' ? format.bytes(file.size) : '—'}</td>
      <td className="font-mono text-xs">{file.mode}</td>
      <td className="tabular-nums">
        {file.uid}:{file.gid}
      </td>
      <td>{format.date(file.modified_at)}</td>
      <td className="text-right">
        <button type="button" className={iconButton} disabled={busy} onClick={restore}>
          {t('machine.files.restore')}
        </button>
      </td>
    </tr>
  );
}
