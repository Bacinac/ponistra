import { useQuery } from '@tanstack/react-query';
import { Pencil, RotateCcw, Save } from 'lucide-react';
import { lazy, Suspense, useState, type FormEvent } from 'react';
import { Navigate, NavLink, useNavigate, useParams, useSearchParams } from 'react-router';
import { compact, idIn } from './address';
import { getJson, patchJson, postJson } from './api';
import { Cancel, ConfirmDialog, Modal, NameDialog, Picker } from './dialogs';
import { Addressed, Frame, Loading, Missing, Panel } from './frame';
import { useI18n } from './i18n';
import { ContextMenuArea, MenuItem, MenuSeparator } from './menu';
import { useMenuPress } from './press';
import { button, primaryButton } from './styles';
import { outlineStore, TabList, tabHref, useFound } from './tabs';
import type { User } from './auth';
import {
  covers,
  errorMessage,
  Failure,
  nodeHref,
  TREE,
  useTreeChange,
  type Place,
  type Role,
  type Tab,
  type TreeNode,
} from './tree';

const SavedEditor = lazy(() =>
  import('./editor/Editor').then((module) => ({ default: module.SavedEditor })),
);

export interface Version {
  id: string;
  number: number;
  title: string;
  created_at: string;
  restored_from: number | null;
  editors: User[];
}

interface VersionDetail extends Place {
  version: Version;
  tabs: Tab[];
}

function useVersions(documentId: string) {
  return useQuery({
    queryKey: [...TREE, 'versions', documentId],
    queryFn: () => getJson<{ versions: Version[] }>(`/api/nodes/${documentId}/versions`),
  });
}

function useVersion(id: string) {
  return useQuery({
    queryKey: [...TREE, 'version', id],
    queryFn: () => getJson<VersionDetail>(`/api/versions/${id}`),
  });
}

function useRestore() {
  const navigate = useNavigate();
  const restore = useTreeChange((version: Version) =>
    postJson<Version>(`/api/versions/${version.id}/restore`),
  );
  return {
    error: restore.error,
    mutate: (version: Version, document: TreeNode) =>
      restore.mutate(version, { onSuccess: () => navigate(nodeHref(document)) }),
  };
}

function useVersionText() {
  const { t, formatDate, formatNumber } = useI18n();
  return {
    name: (version: Version) =>
      version.title ||
      (version.restored_from === null
        ? t('version.automatic')
        : `${t('version.restoredFrom')} ${formatNumber(version.restored_from)}`),
    details: (version: Version) =>
      [
        `${t('version.number')} ${formatNumber(version.number)}`,
        formatDate(version.created_at),
        version.editors.map((editor) => editor.name).join(', '),
      ]
        .filter(Boolean)
        .join(' · '),
  };
}

function RestoreDialog({
  version,
  onRestore,
  onClose,
}: {
  version: Version;
  onRestore: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const text = useVersionText();
  return (
    <ConfirmDialog
      heading={t('version.restoreTitle')}
      confirmLabel={t('version.restore')}
      onConfirm={onRestore}
      onClose={onClose}
    >
      <strong>{text.name(version)}</strong> ({text.details(version)}). {t('version.restoreWarning')}
    </ConfirmDialog>
  );
}

/** Picks the version a tab is compared with, the latest first. */
export function CompareDialog({
  documentId,
  onCompare,
  onClose,
}: {
  documentId: string;
  onCompare: (version: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const versions = useVersions(documentId);
  const text = useVersionText();
  const [chosen, setChosen] = useState<string | null>(null);
  const listed = versions.data?.versions ?? [];
  const version = chosen ?? listed[0]?.id;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!version) return;
    onCompare(version);
    onClose();
  }

  return (
    <Modal heading={t('action.documentCompare')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {versions.isPending ? (
          <Loading />
        ) : versions.isError ? (
          <p className="text-sm text-danger">{errorMessage(versions.error, t)}</p>
        ) : version ? (
          <Picker
            label={t('compare.version')}
            value={version}
            options={listed.map((each) => [each.id, `${text.name(each)} · ${text.details(each)}`])}
            onChange={setChosen}
          />
        ) : (
          <p className="text-sm text-muted">{t('version.empty')}</p>
        )}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={!version} className={primaryButton}>
            {t('compare.run')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

type Dialog =
  { type: 'save' } | { type: 'name'; version: Version } | { type: 'restore'; version: Version };

export function VersionsPanel({
  document,
  role,
  onClose,
}: {
  document: TreeNode;
  role: Role;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const versions = useVersions(document.id);
  const restore = useRestore();
  const text = useVersionText();
  const press = useMenuPress();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const close = () => setDialog(null);
  const href = `${nodeHref(document)}/versions`;
  const writable = covers(role, 'edit');

  return (
    <Panel title={t('version.list')} onClose={onClose}>
      <button
        type="button"
        disabled={!writable}
        className={`${button} justify-center`}
        onClick={() => setDialog({ type: 'save' })}
      >
        <Save size={16} aria-hidden />
        {t('version.save')}
      </button>
      {versions.isPending ? (
        <Loading />
      ) : versions.isError ? (
        <p className="text-sm text-danger">{errorMessage(versions.error, t)}</p>
      ) : versions.data.versions.length === 0 ? (
        <p className="text-sm text-muted">{t('version.empty')}</p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {versions.data.versions.map((version) => (
            <li key={version.id}>
              <ContextMenuArea
                items={
                  <>
                    <MenuItem
                      icon={Pencil}
                      label={version.title ? t('tree.rename') : t('version.name')}
                      disabled={!writable}
                      onSelect={() => setDialog({ type: 'name', version })}
                    />
                    <MenuSeparator />
                    <MenuItem
                      icon={RotateCcw}
                      label={t('version.restore')}
                      disabled={!writable}
                      onSelect={() => setDialog({ type: 'restore', version })}
                    />
                  </>
                }
              >
                <NavLink
                  {...press}
                  to={`${href}/${compact(version.id)}`}
                  className="flex min-w-0 flex-col rounded px-2 py-1.5 select-none hover:bg-hover aria-[current=page]:bg-selected [-webkit-touch-callout:none]"
                >
                  <span className={`truncate text-sm ${version.title ? 'font-semibold' : ''}`}>
                    {text.name(version)}
                  </span>
                  <span className="text-xs text-muted">{text.details(version)}</span>
                </NavLink>
              </ContextMenuArea>
            </li>
          ))}
        </ul>
      )}
      {restore.error && <p className="text-sm text-danger">{errorMessage(restore.error, t)}</p>}
      {dialog?.type === 'save' && (
        <NameDialog
          heading={t('version.save')}
          submitLabel={t('tree.save')}
          onSubmit={(title) => postJson(`/api/nodes/${document.id}/versions`, { title })}
          onDone={close}
          onClose={close}
        />
      )}
      {dialog?.type === 'name' && (
        <NameDialog
          heading={dialog.version.title ? t('tree.rename') : t('version.name')}
          submitLabel={t('tree.save')}
          initial={dialog.version.title}
          onSubmit={(title) => patchJson(`/api/versions/${dialog.version.id}`, { title })}
          onDone={close}
          onClose={close}
        />
      )}
      {dialog?.type === 'restore' && (
        <RestoreDialog
          version={dialog.version}
          onRestore={() => restore.mutate(dialog.version, document)}
          onClose={close}
        />
      )}
    </Panel>
  );
}

export function VersionPage() {
  const versionId = idIn(useParams().version);
  return versionId ? <OpenVersion key={versionId} versionId={versionId} /> : <Missing />;
}

function OpenVersion({ versionId }: { versionId: string }) {
  const { tab: tabSegment } = useParams();
  const [params] = useSearchParams();
  const found = useFound(params);
  const { t } = useI18n();
  const navigate = useNavigate();
  const [outline] = useState(outlineStore);
  const detail = useVersion(versionId);
  const restore = useRestore();
  const text = useVersionText();
  const [restoring, setRestoring] = useState(false);

  if (detail.isPending) {
    return (
      <Frame side={<Loading />}>
        <Loading />
      </Frame>
    );
  }
  if (detail.isError) {
    return (
      <Frame>
        <Failure error={detail.error} />
      </Frame>
    );
  }

  const { version, path, root, role, tabs } = detail.data;
  const document = path.at(-1)!;
  const href = `${nodeHref(document)}/versions/${compact(version.id)}`;
  const current = tabSegment ? tabs.find((tab) => tab.id === idIn(tabSegment)) : tabs[0];
  if (tabSegment && !current) return <Navigate to={href} replace />;
  const address = current ? tabHref(href, current, tabs) : href;

  return (
    <Addressed href={address}>
      <Frame
        path={path}
        root={root}
        after={[{ title: text.name(version) }]}
        actions={
          <button
            type="button"
            disabled={!covers(role, 'edit')}
            className={button}
            onClick={() => setRestoring(true)}
          >
            <RotateCcw size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">{t('version.restore')}</span>
          </button>
        }
        side={
          <TabList
            tabs={tabs}
            current={current}
            href={(tab) => tabHref(href, tab, tabs)}
            outline={{
              store: outline,
              href: (block) => `${address}?${new URLSearchParams({ block })}`,
            }}
          />
        }
        panel={
          <VersionsPanel
            document={document}
            role={role}
            onClose={() => navigate(nodeHref(document))}
          />
        }
      >
        <div className="flex w-full flex-col gap-4">
          <p className="mx-auto w-full max-w-(--column) text-sm text-muted">
            {text.details(version)} · {t('version.readOnly')}
          </p>
          {restore.error && (
            <p className="mx-auto w-full max-w-(--column) text-sm text-danger">
              {errorMessage(restore.error, t)}
            </p>
          )}
          {current && (
            <Suspense fallback={<Loading />}>
              <SavedEditor
                key={current.id}
                version={version.id}
                home={href}
                tabs={tabs}
                tab={current.id}
                found={found}
                outline={outline}
                locale={document.locale}
              />
            </Suspense>
          )}
        </div>
        {restoring && (
          <RestoreDialog
            version={version}
            onRestore={() => restore.mutate(version, document)}
            onClose={() => setRestoring(false)}
          />
        )}
      </Frame>
    </Addressed>
  );
}
