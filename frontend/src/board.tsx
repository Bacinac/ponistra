import { useQuery } from '@tanstack/react-query';
import { Bot, FolderCog, RotateCcw } from 'lucide-react';
import { useCallback, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { getJson, patchJson, postJson } from './api';
import { useSession } from './auth';
import { Cancel, ConfirmDialog, Modal, Picker } from './dialogs';
import { Loading, Panel } from './frame';
import { useI18n } from './i18n';
import { useChanges } from './live';
import { ContextMenuArea, MenuItem } from './menu';
import { useMenuPress } from './press';
import { covers, errorMessage, TREE, useTreeChange, type Role, type TreeNode } from './tree';
import { button, primaryButton } from './styles';
import type { Version } from './versions';
import { useOpenWorkspace } from './workspace';

/** A version of a board (D36): who wrote it, and through which outside agent. */
interface BoardVersion extends Version {
  agent: string;
}

/** The page PONISTRA shows a board in; it holds the board sandboxed and lets it go nowhere. */
export function boardPage(nodeId: string, version?: string | null): string {
  return `/api/nodes/${nodeId}/board${version ? `?version=${version}` : ''}`;
}

/** A board as it is, or the page one of its versions kept; a new page shows as soon as it is
 * written, and the page hears when what the board keeps changed, to read it again. */
export function BoardView({
  node,
  version,
  className,
}: {
  node: Pick<TreeNode, 'id' | 'title' | 'updated_at'>;
  version?: string | null;
  className: string;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const told = useCallback((areas: string[]) => {
    if (areas.includes('boards') || areas.includes('*'))
      frame.current?.contentWindow?.postMessage({ ponistra: 'changed' }, window.location.origin);
  }, []);
  useChanges(told);
  return (
    <iframe
      ref={frame}
      key={`${node.updated_at}:${version ?? ''}`}
      src={boardPage(node.id, version)}
      title={node.title}
      className={className}
    />
  );
}

export function BoardVersionsPanel({
  node,
  role,
  version,
  onVersion,
  onClose,
}: {
  node: TreeNode;
  role: Role;
  version: string | null;
  onVersion: (version: string | null) => void;
  onClose: () => void;
}) {
  const { t, formatDate, formatNumber } = useI18n();
  const versions = useQuery({
    queryKey: [...TREE, 'versions', node.id],
    queryFn: () => getJson<{ versions: BoardVersion[] }>(`/api/nodes/${node.id}/versions`),
  });
  const restore = useTreeChange((chosen: BoardVersion) =>
    postJson<BoardVersion>(`/api/file-versions/${chosen.id}/restore`),
  );
  const press = useMenuPress();
  const [restoring, setRestoring] = useState<BoardVersion | null>(null);
  const writable = covers(role, 'edit');
  const name = (each: BoardVersion) =>
    each.restored_from === null
      ? `${t('version.number')} ${formatNumber(each.number)}`
      : `${t('version.restoredFrom')} ${formatNumber(each.restored_from)}`;
  const details = (each: BoardVersion) =>
    [formatDate(each.created_at), ...each.editors.map((editor) => editor.name), each.agent]
      .filter(Boolean)
      .join(' · ');

  return (
    <Panel title={t('version.list')} onClose={onClose}>
      {versions.isPending ? (
        <Loading />
      ) : versions.isError ? (
        <p className="text-sm text-danger">{errorMessage(versions.error, t)}</p>
      ) : versions.data.versions.length === 0 ? (
        <p className="text-sm text-muted">{t('board.versionsEmpty')}</p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {versions.data.versions.map((each, index) => {
            const current = index === 0;
            return (
              <li key={each.id}>
                <ContextMenuArea
                  items={
                    <MenuItem
                      icon={RotateCcw}
                      label={t('version.restore')}
                      disabled={!writable || current}
                      onSelect={() => setRestoring(each)}
                    />
                  }
                >
                  <button
                    type="button"
                    {...press}
                    aria-current={(current ? version === null : version === each.id) || undefined}
                    onClick={() => onVersion(current ? null : each.id)}
                    className="flex w-full min-w-0 flex-col rounded px-2 py-1.5 text-left select-none hover:bg-hover aria-[current=true]:bg-selected [-webkit-touch-callout:none]"
                  >
                    <span className="truncate text-sm">
                      {name(each)}
                      {current && <span className="text-muted"> · {t('board.current')}</span>}
                    </span>
                    <span className="text-xs text-muted">{details(each)}</span>
                  </button>
                </ContextMenuArea>
              </li>
            );
          })}
        </ul>
      )}
      {restore.error && <p className="text-sm text-danger">{errorMessage(restore.error, t)}</p>}
      {restoring && (
        <ConfirmDialog
          heading={t('board.restoreTitle')}
          confirmLabel={t('version.restore')}
          onConfirm={() => restore.mutate(restoring, { onSuccess: () => onVersion(null) })}
          onClose={() => setRestoring(null)}
        >
          <strong>{name(restoring)}</strong> ({details(restoring)}). {t('board.restoreWarning')}
        </ConfirmDialog>
      )}
    </Panel>
  );
}

interface WorkspaceProject {
  name: string | null;
  path: string;
}

/** The board's agent (S7): a new chat in the owner's code workspace, in the folder the board's
 * owner chose for it, with the task of carrying out the answers written on the board waiting for
 * the owner's Enter. The page itself opens nothing, as its sandbox lets it go nowhere. */
export function useBoardAgent(
  node: Pick<TreeNode, 'id' | 'title' | 'agent_folder'>,
  role: Role,
  board: boolean,
): { button: ReactNode; item: ReactNode } {
  const { t } = useI18n();
  const held = Boolean(useSession().data?.user?.workspace);
  const workspace = useOpenWorkspace();
  const [choosing, setChoosing] = useState<'send' | 'choose' | null>(null);
  const choosable = covers(role, 'edit');
  if (!board || !held || !(node.agent_folder || choosable)) return { button: null, item: null };
  const send = (folder: string) =>
    workspace.open({
      query: `?${new URLSearchParams({
        folder,
        chat: 'new',
        prompt: t('board.agentPrompt').replace('{title}', node.title).replace('{id}', node.id),
      })}`,
      name: `ponistra-code-${folder.split('/').findLast(Boolean) ?? 'general'}`,
    });
  return {
    button: (
      <>
        <button
          type="button"
          disabled={workspace.isPending}
          onClick={() => (node.agent_folder ? send(node.agent_folder) : setChoosing('send'))}
          className={button}
        >
          <Bot size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('board.agent')}</span>
        </button>
        {choosing && (
          <AgentFolderDialog
            node={node}
            sending={choosing === 'send'}
            onChosen={(folder) => {
              setChoosing(null);
              if (choosing === 'send') send(folder);
            }}
            onClose={() => setChoosing(null)}
          />
        )}
      </>
    ),
    item: (
      <MenuItem
        icon={FolderCog}
        label={t('board.agentFolder')}
        disabled={!choosable}
        onSelect={() => setChoosing('choose')}
      />
    ),
  };
}

function AgentFolderDialog({
  node,
  sending,
  onChosen,
  onClose,
}: {
  node: Pick<TreeNode, 'id' | 'agent_folder'>;
  sending: boolean;
  onChosen: (folder: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const projects = useQuery({
    queryKey: ['workspace', 'projects'],
    queryFn: () => getJson<{ projects: WorkspaceProject[] }>('/api/workspace/projects'),
    retry: false,
  });
  const [chosen, setChosen] = useState<string | null>(null);
  const save = useTreeChange((folder: string) =>
    patchJson(`/api/nodes/${node.id}`, { agent_folder: folder }),
  );
  const listed = projects.data?.projects ?? [];
  const folder = chosen ?? node.agent_folder ?? listed[0]?.path ?? '';
  const options = listed.map(
    (project) => [project.path, project.name ?? t('workspace.general')] as const,
  );
  if (node.agent_folder && !listed.some((project) => project.path === node.agent_folder))
    options.unshift([node.agent_folder, node.agent_folder] as const);

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(folder, { onSuccess: () => onChosen(folder) });
  }

  return (
    <Modal heading={t('board.agentFolderTitle')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        {projects.isPending ? (
          <Loading />
        ) : projects.isError ? (
          <p className="text-sm text-danger">{errorMessage(projects.error, t)}</p>
        ) : (
          <Picker
            label={t('board.agentProject')}
            value={folder}
            options={options}
            onChange={setChosen}
          />
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={!folder || save.isPending} className={primaryButton}>
            {sending ? t('board.agent') : t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
