import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Download,
  ExternalLink,
  File as FileIcon,
  FileCode,
  FileDown,
  History,
  Languages,
  LayoutDashboard,
  LayoutGrid,
  MessageSquareText,
  RotateCcw,
  Share2,
  SlidersHorizontal,
} from 'lucide-react';
import { lazy, Suspense, useState, useSyncExternalStore } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { idIn } from './address';
import { AccessPanel } from './access';
import { postJson } from './api';
import { useSession, useVisitor } from './auth';
import { BoardVersionsPanel, BoardView, boardPage, useBoardAgent } from './board';
import { CommentsPanel, DeskContext, useDeskState, useThreads } from './comments';
import { Close, Modal, NameDialog } from './dialogs';
import { formatSize } from './explorer';
import { TranslateDialog, useFollowedRun, type Gathering } from './gather';
import { Addressed, Frame, Loading, Missing } from './frame';
import { useI18n } from './i18n';
import { FavouriteButton } from './favourites';
import { MenuItem } from './menu';
import type { Pen } from './pen';
import type { Sealed } from './pdf/load';
import { button, iconButton } from './styles';
import { EditPanel, useUndoKeys } from './image/EditPanel';
import { EDITABLE, edited, type Edits, type Ratio, type Tool } from './image/edits';
import { ImageView, useBitmap } from './image/ImageView';
import { useImageRoom, useKept } from './image/room';
import { Headings, outlineStore } from './tabs';
import { useForeign } from './translation';
import {
  covers,
  Elsewhere,
  errorMessage,
  Failure,
  kindLabel,
  kindOf,
  LONGEST_TITLE,
  nodeHref,
  nodeKey,
  useNode,
  type FileBytes,
  type Placement,
  type TreeNode,
} from './tree';
import { savedName } from './upload';
import { useAi } from './editor/runs';

const PdfView = lazy(() => import('./pdf/PdfView'));
const PagesView = lazy(() => import('./pdf/PagesView'));
const TextView = lazy(() => import('./TextView'));

export function FilePage() {
  const nodeId = idIn(useParams().node);
  return nodeId ? <OpenFile key={nodeId} nodeId={nodeId} /> : <Missing />;
}

function OpenFile({ nodeId }: { nodeId: string }) {
  const { t, formatNumber } = useI18n();
  const visitor = useVisitor();
  const placement = useNode(nodeId);
  const [params, setParams] = useSearchParams();
  const { key } = useLocation();
  const [outline] = useState(outlineStore);
  const bookmarked = Boolean(useSyncExternalStore(outline.subscribe, outline.get)?.headings.length);
  const threads = useThreads(nodeId);
  const desk = useDeskState(params.get('comment'), (thread, replace) =>
    setParams(thread ? { panel: 'comments', comment: thread } : { panel: 'comments' }, { replace }),
  );
  const [marked, setMarked] = useState(false);
  const [sealed, setSealed] = useState<Sealed | null>(null);
  const seal = (how: Sealed) => setSealed((now) => now ?? how);
  const panel = params.get('panel');
  const arranging = params.get('view') === 'pages';
  const page = Number(params.get('page')) || null;
  const ai = useAi();
  const foreign = useForeign(placement.data?.pdf?.language);
  const [translating, setTranslating] = useState<'asking' | Gathering | null>(null);
  const followed = useFollowedRun(translating === 'asking' ? null : translating, () =>
    setTranslating(null),
  );

  if (placement.isPending) {
    return (
      <Frame>
        <Loading />
      </Frame>
    );
  }
  if (placement.isError) {
    return (
      <Frame>
        <Failure error={placement.error} />
      </Frame>
    );
  }

  const { node, path, root, role, confined, room, pdf } = placement.data;
  if (node.kind !== 'file') return <Elsewhere node={node} />;
  if (kindOf(node) !== 'file') return <Kept placement={placement.data} />;
  const file = `/api/nodes/${node.id}/file?v=${pdf!.served}`;
  const given = `/api/nodes/${node.id}/noted`;
  const guarded = sealed === 'password';
  const noted = marked || Boolean(threads.data?.length);
  const address = nodeHref(node);
  const comments = threads.data?.filter((thread) => !thread.resolved_at).length;
  const kept = confined && !covers(role, 'edit');

  const keeping = (next: Record<string, string>) =>
    setParams(arranging ? { ...next, view: 'pages' } : next);
  const closePanel = () => {
    desk.drop();
    keeping({});
  };
  const togglePanel = (name: string) => (panel === name ? closePanel() : keeping({ panel: name }));

  const actions = (
    <>
      <FavouriteButton id={node.id} size={16} className={button} />
      <button
        type="button"
        aria-pressed={arranging}
        disabled={!arranging && sealed !== null}
        title={sealed && !arranging ? t(`pages.sealed.${sealed}`) : undefined}
        onClick={() =>
          setParams({ ...(panel ? { panel } : {}), ...(arranging ? {} : { view: 'pages' }) })
        }
        className={`${button} aria-pressed:bg-selected`}
      >
        <LayoutGrid size={16} aria-hidden />
        <span className="sr-only sm:not-sr-only">{t('pages.view')}</span>
      </button>
      <button
        type="button"
        aria-pressed={panel === 'comments'}
        onClick={() => togglePanel('comments')}
        className={`${button} aria-pressed:bg-selected`}
      >
        <MessageSquareText size={16} aria-hidden />
        <span className="sr-only sm:not-sr-only">{t('comment.list')}</span>
        {!!comments && <span className="text-xs text-muted">{formatNumber(comments)}</span>}
      </button>
      {!visitor && (
        <button
          type="button"
          aria-pressed={panel === 'access'}
          onClick={() => togglePanel('access')}
          className={`${button} aria-pressed:bg-selected`}
        >
          <Share2 size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('access.share')}</span>
        </button>
      )}
      {confined ? (
        <button type="button" disabled title={t('confined.hint')} className={button}>
          <Download size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('file.download')}</span>
        </button>
      ) : (
        <a
          href={`${given}?download=1`}
          title={guarded && noted ? t('file.locked') : undefined}
          className={button}
        >
          <Download size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">
            {guarded && noted ? t('file.original') : t('file.download')}
          </span>
        </a>
      )}
    </>
  );

  return (
    <DeskContext value={desk}>
      <Addressed href={address}>
        <Frame
          path={path}
          root={root}
          menu={
            <>
              <MenuItem
                icon={ExternalLink}
                label={t('file.open')}
                disabled={confined}
                hint={confined ? t('confined.hint') : undefined}
                onSelect={() => window.open(given, '_blank', 'noreferrer')}
              />
              {((noted && !guarded) || pdf!.recognised) && (
                <MenuItem
                  icon={FileDown}
                  label={t('file.original')}
                  disabled={confined}
                  hint={confined ? t('confined.hint') : undefined}
                  onSelect={() => location.assign(`/api/nodes/${node.id}/original?download=1`)}
                />
              )}
              {foreign && (
                <MenuItem
                  icon={Languages}
                  label={t('action.fileTranslate.ask')}
                  disabled={!ai.data || kept}
                  hint={ai.data === false ? t('ai.off') : kept ? t('confined.hint') : undefined}
                  onSelect={() => setTranslating('asking')}
                />
              )}
            </>
          }
          actions={actions}
          side={
            bookmarked ? (
              <Headings
                store={outline}
                indent={0}
                href={(heading) =>
                  `${address}?${new URLSearchParams(panel ? { panel, heading } : { heading })}`
                }
              />
            ) : undefined
          }
          panel={
            (panel === 'comments' && (
              <CommentsPanel document={node} tab={null} role={role} onClose={closePanel} />
            )) ||
            (panel === 'access' && <AccessPanel node={node} onClose={closePanel} />)
          }
        >
          <Suspense fallback={<Loading />}>
            {arranging ? (
              <PagesView file={node} url={file} onSealed={seal} />
            ) : (
              <PdfView
                file={file}
                page={page}
                heading={params.get('heading')}
                find={params.get('find')}
                visit={key}
                outline={outline}
                notes={{
                  room: room!,
                  fileId: node.id,
                  title: node.title,
                  editable: covers(role, 'edit'),
                }}
                onNoted={setMarked}
                onSealed={seal}
                status={<Reading nodeId={node.id} bytes={pdf!} />}
              />
            )}
          </Suspense>
          {followed.bar}
          {followed.failure && (
            <Modal
              heading={t('command.failed')}
              onClose={() => {
                followed.reset();
                setTranslating(null);
              }}
            >
              <p>{errorMessage(followed.failure, t)}</p>
              <div className="flex justify-end">
                <Close />
              </div>
            </Modal>
          )}
          {translating === 'asking' && (
            <TranslateDialog
              file={node}
              onStarted={setTranslating}
              onClose={() => setTranslating((now) => (now === 'asking' ? null : now))}
            />
          )}
        </Frame>
      </Addressed>
    </DeskContext>
  );
}

/** A file other than a PDF: an image or a text is shown, an image its edits drawn in, audio and
 * video are played, anything else is only saved. */
function Kept({ placement: { node, path, root, role, confined, room } }: { placement: Placement }) {
  const { t } = useI18n();
  const visitor = useVisitor();
  const [params, setParams] = useSearchParams();
  const panel = params.get('panel');
  const kind = kindOf(node);
  const image = kind === 'image';
  const board = kind === 'board';
  const source = board && params.get('view') === 'source';
  const version = board ? params.get('version') : null;
  const agent = useBoardAgent(node, role, board);
  const editable = EDITABLE.has(node.media_type ?? '');
  const writable = editable && covers(role, 'edit');
  const imageRoom = useImageRoom(editable ? room : null, node.id);
  const kept = useKept(imageRoom);
  const [cropping, setCropping] = useState<Ratio | undefined>();
  const [toning, setToning] = useState<Partial<Edits>>({});
  const [tool, setTool] = useState<Tool | null>(null);
  const [pen, setPen] = useState<Pen>({ color: 'red', width: 2 });
  const [saving, setSaving] = useState(false);
  const me = useSession().data?.user?.id ?? null;
  const navigate = useNavigate();
  const file = `/api/nodes/${node.id}/file`;
  const given = editable ? `/api/nodes/${node.id}/edited` : file;
  const bitmap = useBitmap(editable ? file : null);
  const upright = bitmap instanceof ImageBitmap ? bitmap : null;
  const edits = { ...kept.edits, ...toning };
  const altered = edited(kept.edits) || kept.marks.length > 0;
  const editing = writable && panel === 'edit';
  useUndoKeys(writable ? imageRoom : null);
  const toggle = (name: string) => {
    setCropping(undefined);
    setTool(null);
    setParams(panel === name ? {} : { panel: name });
  };
  const shown = (changes: Record<string, string | null>) =>
    setParams((current) => {
      const next = new URLSearchParams(current);
      for (const [name, value] of Object.entries(changes))
        if (value === null) next.delete(name);
        else next.set(name, value);
      return next;
    });
  const suffix = t('image.saveAs.suffix');
  return (
    <Addressed href={nodeHref(node)}>
      <Frame
        path={path}
        root={root}
        menu={
          board ? (
            <>
              <MenuItem
                icon={ExternalLink}
                label={t('file.open')}
                onSelect={() => window.open(boardPage(node.id, version), '_blank', 'noreferrer')}
              />
              <MenuItem
                icon={source ? LayoutDashboard : FileCode}
                label={source ? t('board.shown') : t('board.source')}
                onSelect={() => shown({ view: source ? null : 'source' })}
              />
              {agent.item}
            </>
          ) : (
            image && (
              <>
                <MenuItem
                  icon={ExternalLink}
                  label={t('file.open')}
                  disabled={confined}
                  hint={confined ? t('confined.hint') : undefined}
                  onSelect={() => window.open(given, '_blank', 'noreferrer')}
                />
                {altered && (
                  <MenuItem
                    icon={FileDown}
                    label={t('file.original')}
                    disabled={confined}
                    hint={confined ? t('confined.hint') : undefined}
                    onSelect={() => location.assign(`${file}?download=1`)}
                  />
                )}
              </>
            )
          )
        }
        actions={
          <>
            <FavouriteButton id={node.id} size={16} className={button} />
            {writable && (
              <button
                type="button"
                aria-pressed={editing}
                onClick={() => toggle('edit')}
                className={`${button} aria-pressed:bg-selected`}
              >
                <SlidersHorizontal size={16} aria-hidden />
                <span className="sr-only sm:not-sr-only">{t('image.edit')}</span>
              </button>
            )}
            {!visitor && (
              <button
                type="button"
                aria-pressed={panel === 'access'}
                onClick={() => toggle('access')}
                className={`${button} aria-pressed:bg-selected`}
              >
                <Share2 size={16} aria-hidden />
                <span className="sr-only sm:not-sr-only">{t('access.share')}</span>
              </button>
            )}
            {board && (
              <button
                type="button"
                aria-pressed={panel === 'versions'}
                onClick={() => toggle('versions')}
                className={`${button} aria-pressed:bg-selected`}
              >
                <History size={16} aria-hidden />
                <span className="sr-only sm:not-sr-only">{t('version.list')}</span>
              </button>
            )}
            {agent.button}
            {confined ? (
              <button type="button" disabled title={t('confined.hint')} className={button}>
                <Download size={16} aria-hidden />
                <span className="sr-only sm:not-sr-only">{t('file.download')}</span>
              </button>
            ) : (
              <a href={`${given}?download=1`} className={button}>
                <Download size={16} aria-hidden />
                <span className="sr-only sm:not-sr-only">{t('file.download')}</span>
              </a>
            )}
          </>
        }
        panel={
          (panel === 'access' && <AccessPanel node={node} onClose={() => toggle('access')} />) ||
          (board && panel === 'versions' && (
            <BoardVersionsPanel
              node={node}
              role={role}
              version={version}
              onVersion={(chosen) => shown({ version: chosen })}
              onClose={() => toggle('versions')}
            />
          )) ||
          (editing && (
            <EditPanel
              room={imageRoom}
              kept={kept}
              altered={altered}
              edits={edits}
              upright={upright}
              cropping={cropping}
              onCropping={setCropping}
              onToning={setToning}
              tool={tool}
              onTool={setTool}
              pen={pen}
              onPen={setPen}
              save={t('image.saveAs')}
              onSave={() => setSaving(true)}
              onClose={() => toggle('edit')}
            />
          ))
        }
      >
        {editable ? (
          bitmap === 'failed' || bitmap === 'unsupported' ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
              <About node={node} note={t('image.unreadable')} />
            </div>
          ) : upright ? (
            <ImageView
              bitmap={upright}
              title={node.title}
              edits={edits}
              marks={kept.marks}
              cropping={editing ? cropping : undefined}
              onCrop={(crop) => imageRoom?.change({ crop })}
              marking={
                editing && imageRoom
                  ? { tool, pen, me, onMark: imageRoom.mark, onTool: setTool }
                  : null
              }
            />
          ) : (
            <Loading />
          )
        ) : image ? (
          <div className="flex h-full items-center justify-center overflow-auto p-6">
            <img src={file} alt={node.title} className="max-h-full max-w-full object-contain" />
          </div>
        ) : board && !source ? (
          <BoardView node={node} version={version} className="block h-full w-full border-0" />
        ) : kind === 'text' || board ? (
          <Suspense fallback={<Loading />}>
            <TextView nodeId={node.id} name={savedName(node)} />
          </Suspense>
        ) : kind === 'video' || kind === 'audio' ? (
          <Played node={node} file={file} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
            <About node={node} note={t('file.notShown')} />
          </div>
        )}
      </Frame>
      {saving && (
        <NameDialog
          heading={t('image.saveAs.heading')}
          submitLabel={t('tree.create')}
          initial={`${node.title.slice(0, LONGEST_TITLE - suffix.length - 1)} ${suffix}`}
          note={t('image.saveAs.note')}
          onSubmit={(title) => postJson<TreeNode>(`/api/nodes/${node.id}/edited`, { title })}
          onDone={(copy) => navigate(nodeHref(copy))}
          onClose={() => setSaving(false)}
        />
      )}
    </Addressed>
  );
}

/** A recording in the browser's own player; one it cannot play says so. */
function Played({ node, file }: { node: TreeNode; file: string }) {
  const { t } = useI18n();
  const [failed, setFailed] = useState(false);
  const video = kindOf(node) === 'video';
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
      {failed ? (
        <About node={node} note={t('file.notPlayed')} />
      ) : video ? (
        <video
          src={file}
          controls
          preload="metadata"
          aria-label={node.title}
          onError={() => setFailed(true)}
          className="max-h-full max-w-full"
        />
      ) : (
        <>
          <About node={node} />
          <audio
            src={file}
            controls
            preload="metadata"
            aria-label={node.title}
            onError={() => setFailed(true)}
            className="w-full max-w-md"
          />
        </>
      )}
    </div>
  );
}

function About({ node, note }: { node: TreeNode; note?: string }) {
  const { t, formatNumber } = useI18n();
  return (
    <>
      <FileIcon size={48} aria-hidden className="text-muted" />
      <p className="font-semibold">{node.title}</p>
      <p className="text-sm text-muted">
        {[
          kindLabel(kindOf(node), node.extension, t),
          node.size !== null && formatSize(node.size, formatNumber),
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {note && <p className="max-w-sm text-sm text-muted">{note}</p>}
    </>
  );
}

/** Where the reading of the file's pages without text stands, when there is anything to say. */
function Reading({ nodeId, bytes }: { nodeId: string; bytes: FileBytes }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: () => postJson(`/api/nodes/${nodeId}/ocr`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: nodeKey(nodeId) }),
  });
  if (bytes.ocr === 'waiting') return <span className="truncate">{t('ocr.waiting')}</span>;
  if (bytes.ocr === 'refused') {
    return <span className="truncate">{t(`ocr.refused.${bytes.reason!}`)}</span>;
  }
  if (bytes.ocr !== 'failed') return null;
  return (
    <>
      <span className="truncate text-danger">
        {retry.isError ? errorMessage(retry.error, t) : t('ocr.failed')}
      </span>
      <button
        type="button"
        aria-label={t('ocr.retry')}
        title={t('ocr.retry')}
        disabled={retry.isPending}
        onClick={() => retry.mutate()}
        className={`${iconButton} disabled:opacity-40`}
      >
        <RotateCcw size={16} aria-hidden />
      </button>
    </>
  );
}
