import {
  ArrowDown,
  ArrowUp,
  Bot,
  Copy,
  Download,
  FileArchive,
  FileDown,
  FileSliders,
  FileSpreadsheet,
  FileText,
  FileType,
  FolderInput,
  History,
  Import,
  Languages,
  ListIndentDecrease,
  ListIndentIncrease,
  MessageSquareText,
  MonitorPlay,
  Paintbrush,
  Pencil,
  Play,
  Plus,
  Presentation,
  Printer,
  RefreshCw,
  Share2,
  ShieldOff,
  Trash2,
  type LucideIcon,
} from 'lucide-react';
import { useVisitor } from './auth';
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router';
import { AccessPanel } from './access';
import { useConsent } from './ai';
import { idIn } from './address';
import { deleteJson, patchJson, postJson } from './api';
import { CommentsPanel, DeskContext, useDeskState, useThreads } from './comments';
import { ConfirmDialog, CopyDialog, MoveDialog, NameDialog } from './dialogs';
import { Addressed, Frame, Loading, Missing } from './frame';
import { localeName, useI18n } from './i18n';
import { ImportedDialog, ImportReport, sourceHref, useImportInto, useReimport } from './imported';
import { FavouriteButton } from './favourites';
import { MenuChoices, MenuItem, MenuSeparator, MenuSub } from './menu';
import { button } from './styles';
import { usePrint } from './PrintPage';
import { useSaveAs } from './saveAs';
import {
  outlineStore,
  TabList,
  tabHref,
  tabLabel,
  tabMoves,
  useFound,
  type Move,
  type Place,
} from './tabs';
import {
  covers,
  DOCUMENT_LOCALES,
  Elsewhere,
  errorMessage,
  Failure,
  nodeHref,
  ROOT_CRUMBS,
  useNode,
  useToTrash,
  useTreeChange,
  type DocumentLocale,
  type ImportReport as Report,
  type Tab,
} from './tree';
import { IMPORT_ACCEPT, useFilePicker } from './upload';
import { VersionsPanel } from './versions';
import { AgentContext, type Agent, type Asker } from './editor/agent';
import { AgentPanel } from './editor/AgentPanel';

const DocumentEditor = lazy(() => import('./editor/Document'));

const MOVES: [Move, LucideIcon][] = [
  ['up', ArrowUp],
  ['down', ArrowDown],
  ['indent', ListIndentIncrease],
  ['outdent', ListIndentDecrease],
];

type Dialog =
  | { type: 'rename'; tab: Tab }
  | { type: 'delete'; tab: Tab }
  | { type: 'renameDocument' }
  | { type: 'copy' }
  | { type: 'move' }
  | { type: 'styling' }
  | { type: 'page' }
  | { type: 'imported'; report: Report }
  | { type: 'reimport' };

export function DocumentPage() {
  const nodeId = idIn(useParams().node);
  return nodeId ? <OpenDocument key={nodeId} nodeId={nodeId} /> : <Missing />;
}

function OpenDocument({ nodeId }: { nodeId: string }) {
  const { tab: tabSegment } = useParams();
  const { t, language, formatNumber } = useI18n();
  const visitor = useVisitor();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const found = useFound(params);
  const placement = useNode(nodeId);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [requested, setRequested] = useState<string | null>(null);
  const answered = useCallback(() => setRequested(null), []);
  const addTab = useTreeChange((parent?: string) =>
    postJson<Tab>(`/api/nodes/${nodeId}/tabs`, { parent }),
  );
  const removeTab = useTreeChange((tab: Tab) => deleteJson(`/api/tabs/${tab.id}`));
  const moveTab = useTreeChange(({ tab, place }: { tab: Tab; place: Place }) =>
    patchJson<Tab>(`/api/tabs/${tab.id}`, place),
  );
  const relocale = useTreeChange((locale: DocumentLocale) =>
    patchJson(`/api/nodes/${nodeId}`, { locale }),
  );
  const toTrash = useToTrash();
  const importInto = useImportInto(nodeId);
  const reimport = useReimport();
  const picker = useFilePicker(
    ([file]) =>
      importInto.mutate(file, {
        onSuccess: ({ tab, report }) => {
          const { node, tabs } = placement.data!;
          const panel = params.get('panel');
          const kept = panel ? `?${new URLSearchParams({ panel })}` : '';
          navigate(`${tabHref(nodeHref(node), tab, [...tabs, tab])}${kept}`);
          setDialog({ type: 'imported', report });
        },
      }),
    { accept: IMPORT_ACCEPT, multiple: false },
  );
  const printing = usePrint(nodeId);
  const saving = useSaveAs(nodeId);
  const consent = useConsent(nodeId, !visitor);
  const [outline] = useState(outlineStore);
  // The document's own address shows its first tab; a tab moved to the front from under
  // the reader must not swap the tab they are reading.
  const shownFirst = useRef<string | null>(null);
  const first = placement.data?.tabs[0]?.id ?? null;
  useEffect(() => {
    shownFirst.current = tabSegment ? null : first;
  }, [tabSegment, first]);
  const close = () => setDialog(null);
  const threads = useThreads(nodeId);
  const desk = useDeskState(params.get('comment'), (thread, replace) =>
    setParams(thread ? { panel: 'comments', comment: thread } : { panel: 'comments' }, { replace }),
  );
  const asker = useRef<Asker | null>(null);
  const openAgent = useRef(() => {});
  openAgent.current = () => setParams({ panel: 'agent' });
  const agent = useMemo<Agent>(() => ({ open: () => openAgent.current(), asker }), []);

  if (placement.isPending) {
    return (
      <Frame side={<Loading />}>
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

  const { node, path, root, role, confined, room, tabs } = placement.data;
  const writable = covers(role, 'edit');
  const confinedHint = confined ? t('confined.hint') : undefined;
  if (node.kind !== 'document') return <Elsewhere node={node} />;
  const home = nodeHref(node);
  const panel = params.get('panel');
  const kept = panel ? `?${new URLSearchParams({ panel })}` : '';
  const stillShown =
    !tabSegment && shownFirst.current !== first
      ? tabs.find((tab) => tab.id === shownFirst.current)
      : undefined;
  if (stillShown) return <Navigate to={`${tabHref(home, stillShown, tabs)}${kept}`} replace />;
  const current = tabSegment ? tabs.find((tab) => tab.id === idIn(tabSegment)) : tabs[0];
  if (tabSegment && !current) return <Navigate to={home} replace />;
  const address = current ? tabHref(home, current, tabs) : home;

  const comments = threads.data?.filter(
    (thread) => thread.tab === current?.id && !thread.resolved_at,
  ).length;
  const closePanel = () => {
    desk.drop();
    setParams({});
  };
  const add = (parent?: string) =>
    addTab.mutate(parent, {
      onSuccess: (tab) => navigate(`${tabHref(home, tab, tabs)}${kept}`),
    });
  const failure =
    addTab.error ??
    removeTab.error ??
    moveTab.error ??
    toTrash.error ??
    importInto.error ??
    reimport.error ??
    relocale.error ??
    printing.error ??
    saving.error ??
    consent.withdraw.error;
  const togglePanel = (name: string) =>
    panel === name ? closePanel() : setParams({ panel: name });
  const folder = path.findLast((step) => step.kind === 'folder');
  const trash = () =>
    toTrash.mutate([node.id], {
      onSuccess: () => navigate(folder ? nodeHref(folder) : ROOT_CRUMBS[root].href),
    });

  const menu = (
    <>
      <MenuItem
        icon={Copy}
        label={t('copy.make')}
        disabled={confined && !writable}
        hint={confined && !writable ? confinedHint : undefined}
        onSelect={() => setDialog({ type: 'copy' })}
      />
      <MenuItem
        icon={Pencil}
        label={t('tree.rename')}
        disabled={!writable}
        onSelect={() => setDialog({ type: 'renameDocument' })}
      />
      <MenuItem
        icon={FolderInput}
        label={t('tree.move')}
        disabled={!writable}
        onSelect={() => setDialog({ type: 'move' })}
      />
      {node.original && (
        <>
          <MenuItem
            icon={Download}
            label={t('import.original')}
            disabled={confined}
            hint={confinedHint}
            onSelect={() => location.assign(sourceHref(node))}
          />
          <MenuItem
            icon={RefreshCw}
            label={t('import.again')}
            disabled={!writable || reimport.isPending}
            onSelect={() => setDialog({ type: 'reimport' })}
          />
        </>
      )}
      <MenuSeparator />
      <MenuItem
        icon={Import}
        label={t('import.into')}
        disabled={!writable || importInto.isPending}
        onSelect={picker.open}
      />
      <MenuSeparator />
      <MenuSub icon={FileDown} label={t('save.as')} disabled={confined} hint={confinedHint}>
        <MenuItem
          icon={FileType}
          label={t('save.docx')}
          disabled={saving.isPending}
          onSelect={() => saving.mutate({ format: 'docx', title: node.title })}
        />
        {node.macros === 'docm' && (
          <MenuItem
            icon={FileType}
            label={t('save.docm')}
            disabled={saving.isPending}
            onSelect={() => saving.mutate({ format: 'docm', title: node.title })}
          />
        )}
        <MenuItem
          icon={FileText}
          label={t('save.pdf')}
          disabled={saving.isPending}
          onSelect={() => saving.mutate({ format: 'pdf', title: node.title })}
        />
        <MenuItem
          icon={FileSpreadsheet}
          label={t('save.xlsx')}
          disabled={saving.isPending}
          onSelect={() => saving.mutate({ format: 'xlsx', title: node.title })}
        />
        <MenuItem
          icon={FileSpreadsheet}
          label={t('save.csv')}
          disabled={saving.isPending}
          onSelect={() => saving.mutate({ format: 'csv', title: node.title })}
        />
        {node.macros === 'xlsm' && (
          <MenuItem
            icon={FileSpreadsheet}
            label={t('save.xlsm')}
            disabled={saving.isPending}
            onSelect={() => saving.mutate({ format: 'xlsm', title: node.title })}
          />
        )}
        <MenuItem
          icon={Presentation}
          label={t('save.pptx')}
          disabled={saving.isPending}
          onSelect={() => saving.mutate({ format: 'pptx', title: node.title })}
        />
        {node.macros === 'pptm' && (
          <MenuItem
            icon={Presentation}
            label={t('save.pptm')}
            disabled={saving.isPending}
            onSelect={() => saving.mutate({ format: 'pptm', title: node.title })}
          />
        )}
        <MenuItem
          icon={FileArchive}
          label={t('save.ponx')}
          disabled={saving.isPending}
          onSelect={() => saving.mutate({ format: 'ponx', title: node.title })}
        />
        <MenuItem
          icon={FileArchive}
          label={t('save.ponxVersions')}
          disabled={saving.isPending}
          onSelect={() => saving.mutate({ format: 'ponx', title: node.title, versions: true })}
        />
      </MenuSub>
      <MenuSeparator />
      <MenuItem
        icon={MonitorPlay}
        label={t('command.presentStart')}
        onSelect={() => setRequested('slide.present.start')}
      />
      <MenuItem
        icon={Play}
        label={t('command.present')}
        onSelect={() => setRequested('slide.present')}
      />
      <MenuItem
        icon={Printer}
        label={t('print.open')}
        disabled={confined}
        hint={confinedHint}
        onSelect={printing.print}
      />
      <MenuItem
        icon={FileSliders}
        label={t('page.setup')}
        disabled={!writable}
        onSelect={() => setDialog({ type: 'page' })}
      />
      <MenuItem
        icon={Paintbrush}
        label={t('styles.open')}
        disabled={!writable}
        onSelect={() => setDialog({ type: 'styling' })}
      />
      <MenuSub icon={Languages} label={t('document.locale')} disabled={!writable}>
        <MenuChoices
          value={node.locale}
          choices={DOCUMENT_LOCALES.map((locale) => ({
            value: locale,
            label: localeName(locale, language),
          }))}
          onChange={(locale) => relocale.mutate(locale)}
        />
      </MenuSub>
      {consent.given && (
        <MenuItem
          icon={ShieldOff}
          label={t('ai.consent.withdraw')}
          disabled={!writable}
          onSelect={() => consent.withdraw.mutate()}
        />
      )}
      <MenuSeparator />
      <MenuItem
        icon={MessageSquareText}
        label={t('comment.list')}
        onSelect={() => setParams({ panel: 'comments' })}
      />
      <MenuItem
        icon={History}
        label={t('version.list')}
        onSelect={() => setParams({ panel: 'versions' })}
      />
      {!visitor && (
        <MenuItem
          icon={Share2}
          label={t('access.share')}
          onSelect={() => setParams({ panel: 'access' })}
        />
      )}
      <MenuSeparator />
      <MenuItem icon={Trash2} label={t('tree.toTrash')} disabled={!writable} onSelect={trash} />
    </>
  );

  const side = (
    <div className="flex flex-col gap-0.5">
      <TabList
        tabs={tabs}
        current={current}
        href={(tab) => `${tabHref(home, tab, tabs)}${kept}`}
        outline={{
          store: outline,
          href: (block) =>
            `${address}?${new URLSearchParams(panel ? { panel, block } : { block })}`,
        }}
        onMove={writable ? (tab, place) => moveTab.mutate({ tab, place }) : undefined}
        menu={(tab) => {
          const moves = tabMoves(tabs, tab);
          return (
            <>
              <MenuItem
                icon={Pencil}
                label={t('tree.rename')}
                disabled={!writable}
                onSelect={() => setDialog({ type: 'rename', tab })}
              />
              <MenuItem
                icon={Plus}
                label={t('tab.newChild')}
                disabled={!writable}
                onSelect={() => add(tab.id)}
              />
              <MenuSeparator />
              {MOVES.map(([move, icon]) => (
                <MenuItem
                  key={move}
                  icon={icon}
                  label={t(`tab.${move}`)}
                  disabled={!writable || !moves[move]}
                  onSelect={() => moveTab.mutate({ tab, place: moves[move]! })}
                />
              ))}
              <MenuSeparator />
              <MenuItem
                icon={Trash2}
                label={t('tab.delete')}
                disabled={!writable}
                onSelect={() => setDialog({ type: 'delete', tab })}
              />
            </>
          );
        }}
      />
      <button
        type="button"
        disabled={!writable}
        onClick={() => add()}
        className="flex items-center gap-2 rounded px-2 py-1.5 text-sm text-muted hover:bg-hover hover:text-ink disabled:opacity-40"
      >
        <Plus size={16} aria-hidden />
        {t('tab.new')}
      </button>
    </div>
  );

  const actions = (
    <>
      <FavouriteButton id={node.id} size={16} className={button} />
      {writable && !visitor && (
        <button
          type="button"
          aria-pressed={panel === 'agent'}
          onClick={() => togglePanel('agent')}
          className={`${button} aria-pressed:bg-selected`}
        >
          <Bot size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('agent.title')}</span>
        </button>
      )}
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
      <button
        type="button"
        aria-pressed={panel === 'versions'}
        onClick={() => togglePanel('versions')}
        className={`${button} aria-pressed:bg-selected`}
      >
        <History size={16} aria-hidden />
        <span className="sr-only sm:not-sr-only">{t('version.list')}</span>
      </button>
    </>
  );

  return (
    <DeskContext value={desk}>
      <AgentContext value={agent}>
        <Addressed href={address}>
          <Frame
            path={path}
            root={root}
            menu={menu}
            actions={actions}
            side={side}
            panel={
              (panel === 'comments' && (
                <CommentsPanel
                  document={node}
                  tab={current?.id ?? null}
                  role={role}
                  onClose={closePanel}
                />
              )) ||
              (panel === 'versions' && (
                <VersionsPanel document={node} role={role} onClose={closePanel} />
              )) ||
              (panel === 'access' && <AccessPanel node={node} onClose={closePanel} />) ||
              (panel === 'agent' && writable && !visitor && (
                <AgentPanel tab={current?.id ?? null} onClose={closePanel} />
              ))
            }
          >
            <div className="flex w-full flex-col gap-4">
              {failure && (
                <p className="mx-auto w-full max-w-(--column) text-sm text-danger">
                  {errorMessage(failure, t)}
                </p>
              )}
              {printing.pending && (
                <p className="mx-auto w-full max-w-(--column) text-sm text-muted">
                  {t('print.preparing')}
                </p>
              )}
              {saving.isPending && (
                <p className="mx-auto w-full max-w-(--column) text-sm text-muted">
                  {t('save.pending')}
                </p>
              )}
              {(importInto.isPending || reimport.isPending) && (
                <p className="mx-auto w-full max-w-(--column) text-sm text-muted">
                  {t('import.importing')}
                </p>
              )}
              {writable && (
                <ImportReport
                  node={node}
                  confined={confined}
                  reimporting={reimport.isPending}
                  onReimport={() => setDialog({ type: 'reimport' })}
                />
              )}
              <Suspense fallback={<Loading />}>
                <DocumentEditor
                  key={room}
                  room={room!}
                  tab={current ?? null}
                  tabs={tabs}
                  documentId={node.id}
                  original={node.original}
                  home={home}
                  readOnly={!writable}
                  found={found}
                  outline={outline}
                  locale={node.locale}
                  title={node.title}
                  dialog={
                    dialog?.type === 'styling' || dialog?.type === 'page' ? dialog.type : null
                  }
                  onDialogClose={close}
                  requested={requested}
                  onRequested={answered}
                />
              </Suspense>
            </div>
            {dialog?.type === 'rename' && (
              <NameDialog
                heading={t('tree.rename')}
                submitLabel={t('tree.save')}
                initial={tabLabel(dialog.tab, t)}
                onSubmit={(title) => patchJson(`/api/tabs/${dialog.tab.id}`, { title })}
                onDone={close}
                onClose={close}
              />
            )}
            {dialog?.type === 'renameDocument' && (
              <NameDialog
                heading={t('tree.rename')}
                submitLabel={t('tree.save')}
                initial={node.title}
                onSubmit={(title) => patchJson(`/api/nodes/${node.id}`, { title })}
                onDone={close}
                onClose={close}
              />
            )}
            {dialog?.type === 'copy' && (
              <CopyDialog node={node} onDone={(copy) => navigate(nodeHref(copy))} onClose={close} />
            )}
            {dialog?.type === 'move' && <MoveDialog nodes={[{ ...node, role }]} onClose={close} />}
            {dialog?.type === 'imported' && (
              <ImportedDialog report={dialog.report} onClose={close} />
            )}
            {dialog?.type === 'reimport' && (
              <ConfirmDialog
                heading={t('import.againTitle')}
                confirmLabel={t('import.again')}
                onConfirm={() => reimport.mutate(node)}
                onClose={close}
              >
                {t('import.againWarning')}
              </ConfirmDialog>
            )}
            {picker.element}
            {dialog?.type === 'delete' && (
              <ConfirmDialog
                heading={t('tab.deleteTitle')}
                confirmLabel={t('tab.delete')}
                onConfirm={() => removeTab.mutate(dialog.tab)}
                onClose={close}
              >
                <strong>{tabLabel(dialog.tab, t)}</strong> {t('tab.deleteWarning')}
              </ConfirmDialog>
            )}
          </Frame>
        </Addressed>
      </AgentContext>
    </DeskContext>
  );
}
