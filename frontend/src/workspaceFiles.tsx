import { X } from 'lucide-react';
import { useState } from 'react';
import { getJson, postJson, upload } from './api';
import type { Opened, Written } from './codeEditor';
import { ConfirmDialog } from './dialogs';
import { FileBrowser, segment, type FileEntry, type FileSource } from './files';
import { useI18n } from './i18n';
import { useHeldRelease } from './release';
import { iconButton } from './styles';

const asked = (folder: string, path: string, more: Record<string, string> = {}) =>
  new URLSearchParams({ folder, path, ...more }).toString();

/** A project of the workspace as a source of the file browser Documents shows a network location
 * in (ML6). */
function sourceOf(folder: string, name: string): FileSource {
  return {
    key: `workspace:${folder}`,
    name,
    writable: true,
    list: (path) =>
      getJson<{ path: string; entries: FileEntry[] }>(
        `/api/workspace/files?${asked(folder, path)}`,
      ),
    rawHref: (path, download) =>
      `/api/workspace/file/raw?${asked(folder, path, download ? { download: '1' } : {})}`,
    pictureHref: (path) => `/api/workspace/file/picture?${asked(folder, path)}`,
    heldBase: (path) => `/api/workspace/held/${segment(folder)}/${segment(path)}`,
    zipHref: (paths) =>
      `/api/workspace/files/zip?${new URLSearchParams([['folder', folder], ...paths.map((path) => ['path', path])]).toString()}`,
    read: (path) => getJson<Opened>(`/api/workspace/file?${asked(folder, path)}`),
    write: (path, text, hash) =>
      postJson<Written>('/api/workspace/file', { folder, path, text, hash }),
    folder: (path, name) => postJson('/api/workspace/files/folder', { folder, path, name }),
    rename: (path, to) => postJson('/api/workspace/files/rename', { folder, path, to }),
    remove: (paths) => postJson('/api/workspace/files/remove', { folder, paths }),
    put: async (path, name, file) =>
      postJson('/api/workspace/files/put', {
        folder,
        path,
        name,
        blob: (await upload(file)).sha256,
      }),
  };
}

/** The files of a project of the workspace (PJ6), in the browser Documents → Network uses. */
export function FilesPanel({
  folder,
  name,
  onDirty,
  onClose,
}: {
  folder: string;
  name: string;
  onDirty: (dirty: boolean) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [source] = useState(() => sourceOf(folder, name));
  const [at, setAt] = useState<{ path: string; file: string | null }>({ path: '', file: null });
  const [dirty, setDirtyHere] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const setDirty = (now: boolean) => {
    setDirtyHere(now);
    onDirty(now);
  };
  useHeldRelease(dirty);
  return (
    <>
      <FileBrowser
        source={source}
        path={at.path}
        file={at.file}
        onGo={(path, file) => setAt({ path, file: file ?? null })}
        onDirty={setDirty}
        frame={({ actions, primary, panel, children }) => (
          <section
            aria-label={t('workspace.view.files')}
            className="flex min-h-0 min-w-0 flex-1 flex-col"
          >
            <div className="mb-2 flex items-center gap-2">
              {primary}
              <div className="flex-1" />
              {actions}
              <button
                type="button"
                aria-label={t('workspace.files.close')}
                title={t('workspace.files.close')}
                onClick={() => (dirty ? setLeaving(true) : onClose())}
                className={iconButton}
              >
                <X size={16} aria-hidden />
              </button>
            </div>
            <div className="flex min-h-[60dvh] min-w-0 flex-1 gap-2">
              <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto">{children}</div>
              {panel}
            </div>
          </section>
        )}
      />
      {leaving && (
        <ConfirmDialog
          heading={t('workspace.files.discard')}
          confirmLabel={t('workspace.files.discardConfirm')}
          onConfirm={() => {
            setDirty(false);
            onClose();
          }}
          onClose={() => setLeaving(false)}
        >
          {t('workspace.files.discardBody')}
        </ConfirmDialog>
      )}
    </>
  );
}
