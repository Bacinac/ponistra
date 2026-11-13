import {
  ChevronDown,
  ChevronUp,
  Combine,
  Copy,
  Download,
  FileText,
  FileUp,
  FolderUp,
  Folder,
  FolderInput,
  FolderOpen,
  Globe,
  Lock,
  PanelRight,
  LayoutDashboard,
  Pencil,
  Plus,
  ScanLine,
  Share2,
  TableProperties,
  Trash2,
  Star,
} from 'lucide-react';
import { useVisitor } from './auth';
import {
  lazy,
  Suspense,
  Fragment,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router';
import { AccessPanel, Audience } from './access';
import { idIn } from './address';
import { patchJson, postJson } from './api';
import { ChoiceBar, useChoice } from './choice';
import { CopyDialog, LinkDialog, MoveDialog, NameDialog } from './dialogs';
import { endDrag, startDrag, useDropTarget, type Saved } from './drag';
import {
  formatSize,
  sortNodes,
  storedPreview,
  storedSort,
  storePreview,
  storeSort,
  type Sort,
  type SortKey,
} from './explorer';
import { Addressed, Frame, Loaded, Missing, PhonePlaces, useWide, WIDE_PANEL } from './frame';
import { GatherDialog, useFollowedRun, type Gathering } from './gather';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { EDITABLE } from './image/edits';
import { FavouriteItem, useFavouriteMarks } from './favourites';
import { useReachable } from './live';
import { KeepItem } from './offline';
import { ActionsMenu, ContextMenuArea, Menu, MenuItem, MenuSeparator } from './menu';
import { useMenuPress } from './press';
import { PreviewPanel } from './preview';
import { button, iconButton, primaryButton } from './styles';
import {
  covers,
  errorMessage,
  kindLabel,
  kindOf,
  placeText,
  type FoundNode,
  nodeHref,
  NodeIcon,
  useBoards,
  useFavourites,
  useCompany,
  useFolder,
  useMove,
  useOpen,
  useShared,
  useToTrash,
  type ListedNode,
  type Role,
  type Root,
  type TreeNode,
} from './tree';
import { inFolder, loose, savedName, useFilePicker, useUploads, type Picked } from './upload';
import { useAi } from './editor/runs';
import { lazily } from './lazily';

const JoinDialog = lazy(() => import('./pdf/Join'));
const ScanDialog = lazily(() => import('./scan'), 'ScanDialog');

const EMPTY: Record<Root, MessageKey> = {
  mine: 'tree.empty',
  company: 'tree.companyEmpty',
  shared: 'tree.sharedEmpty',
};

type Dialog =
  | { type: 'folder' }
  | { type: 'document'; title?: string }
  | { type: 'link' }
  | { type: 'rename'; node: TreeNode }
  | { type: 'copy'; node: TreeNode }
  | { type: 'move'; nodes: ListedNode[] }
  | { type: 'group'; node: ListedNode }
  | { type: 'join'; nodes: ListedNode[] }
  | { type: 'scan' }
  | { type: 'gather'; nodes: ListedNode[] };

const COLUMNS: { key: SortKey; label: MessageKey; className: string }[] = [
  { key: 'title', label: 'tree.name', className: 'w-full' },
  { key: 'kind', label: 'explorer.kind', className: 'hidden md:table-cell' },
  { key: 'updated_at', label: 'explorer.updated', className: 'hidden sm:table-cell' },
  { key: 'updated_by', label: 'explorer.updatedBy', className: 'hidden lg:table-cell' },
  { key: 'size', label: 'explorer.size', className: 'hidden md:table-cell text-right' },
];

/** Beside a wide panel, which says the rest. */
const BRIEF: SortKey[] = ['title', 'updated_at'];

interface Section {
  key: string;
  heading: ReactNode;
  holds: Set<string>;
}

const editable = (nodes: ListedNode[]) =>
  nodes.every((node) => covers(node.role, 'edit') && !node.company);
const joinable = (nodes: ListedNode[]) =>
  nodes.length > 1 && nodes.every((node) => kindOf(node) === 'file');

/** A file as it is saved, a PDF with its notes, an image with its edits. */
function savedOf(node: ListedNode): Saved | undefined {
  if (node.kind !== 'file') return undefined;
  const bytes =
    kindOf(node) === 'file' ? 'noted' : EDITABLE.has(node.media_type ?? '') ? 'edited' : 'file';
  return {
    name: savedName(node),
    type: node.media_type ?? 'application/octet-stream',
    href: `/api/nodes/${node.id}/${bytes}?download=1`,
  };
}

function Row({
  node,
  brief,
  selected,
  choosing,
  current,
  pressed,
  dragged,
  menu,
  onSelect,
  onToggle,
  onOpen,
  onTwice,
  onNodes,
  onFiles,
  favourite,
}: {
  node: ListedNode;
  brief: boolean;
  selected: boolean;
  favourite: boolean;
  choosing: boolean;
  current: boolean;
  pressed: ReturnType<ReturnType<typeof useChoice>['press']>;
  /** What a drag takes along, and the file it saves when dropped out of the browser. */
  dragged: () => { ids: string[]; saved?: Saved };
  menu: ReactNode;
  onSelect: (event: MouseEvent) => void;
  onToggle: () => void;
  onOpen: () => void;
  onTwice: () => void;
  onNodes: (ids: string[]) => void;
  onFiles: (picked: Promise<Picked[]>) => void;
}) {
  const { t, formatDate, formatNumber } = useI18n();
  const target = node.kind === 'folder' && covers(node.role, 'edit');
  const drop = useDropTarget({
    id: node.id,
    onNodes: target ? onNodes : undefined,
    onFiles: target ? onFiles : undefined,
  });
  const cell = 'px-2 py-2 whitespace-nowrap';

  return (
    <tr
      {...drop.props}
      {...pressed}
      data-id={node.id}
      draggable={editable([node])}
      onDragStart={(event) => {
        const { ids, saved } = dragged();
        startDrag(event, ids, saved);
      }}
      onDragEnd={endDrag}
      aria-selected={selected}
      aria-current={current ? 'true' : undefined}
      tabIndex={0}
      onClick={onSelect}
      onDoubleClick={onTwice}
      onMouseDown={(event) => {
        if (event.button === 1) event.preventDefault();
      }}
      onAuxClick={(event) => {
        if (event.button === 1) window.open(nodeHref(node), '_blank');
      }}
      onKeyDown={(event: KeyboardEvent) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === 'Enter') onOpen();
        if (event.key === ' ') {
          event.preventDefault();
          onToggle();
        }
      }}
      className={`cursor-default border-b border-line select-none [-webkit-touch-callout:none] ${selected || current ? 'bg-selected' : 'hover:bg-hover'} ${drop.over ? 'outline-2 -outline-offset-2 outline-focus' : ''}`}
    >
      <td className="px-3" onClick={(event) => event.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={t('explorer.select')}
          className={`align-middle ${choosing ? '' : 'invisible'}`}
        />
      </td>
      <td className={`${cell} max-w-0`}>
        <div className="flex items-center gap-3">
          <NodeIcon node={node} />
          <span className="truncate">{node.title}</span>
          {favourite && (
            <Star
              size={14}
              role="img"
              aria-label={t('favourites.title')}
              className="shrink-0 fill-current text-accent"
            />
          )}
          {node.confined && (
            <Lock
              size={14}
              role="img"
              aria-label={t('confined.label')}
              className="shrink-0 text-muted"
            />
          )}
        </div>
      </td>
      {!brief && (
        <td className={`${cell} hidden text-sm text-muted md:table-cell`}>
          {kindLabel(kindOf(node), node.extension, t)}
        </td>
      )}
      <td className={`${cell} hidden text-sm text-muted sm:table-cell`}>
        {formatDate(node.updated_at)}
      </td>
      {!brief && (
        <>
          <td className={`${cell} hidden text-sm text-muted lg:table-cell`}>
            {node.updated_by?.name}
          </td>
          <td className={`${cell} hidden text-right text-sm text-muted md:table-cell`}>
            {node.size !== null && formatSize(node.size, formatNumber)}
          </td>
          <td className={`${cell} hidden text-sm text-muted sm:table-cell`}>
            <Audience node={node} />
          </td>
        </>
      )}
      <td
        className="pr-2"
        onClick={(event) => event.stopPropagation()}
        onDoubleClick={(event) => event.stopPropagation()}
      >
        <ActionsMenu>{menu}</ActionsMenu>
      </td>
    </tr>
  );
}

function Explorer({
  folder,
  root,
  role,
  confined,
  path,
  items,
  above,
  empty,
  title,
  showing = false,
  sections,
}: {
  folder: TreeNode | null;
  root?: Root;
  role: Role | null;
  confined: boolean;
  path: TreeNode[];
  items: ListedNode[];
  above?: ReactNode;
  empty?: MessageKey;
  title?: string;
  /** The list is there to show what it holds: the panel opens wide on the first of them. */
  showing?: boolean;
  /** The headings it is divided under, in order, each holding its rows however they are sorted. */
  sections?: Section[];
}) {
  const { t, formatNumber } = useI18n();
  const visitor = useVisitor();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const folderId = folder?.id ?? null;
  const reachable = useReachable();
  const writable = covers(role, 'edit') && reachable;
  const kept = (nodes: ListedNode[]) => (confined && !writable) || nodes.some((node) => node.kept);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [sort, setSort] = useState<Sort>(storedSort);
  const [previewing, setPreviewing] = useState(() => showing || storedPreview());
  const [glance, setGlance] = useState<string | null>(null);
  const wide = useWide();
  const [menuOn, setMenuOn] = useState<'folder' | 'selection'>('folder');
  const move = useMove();
  const toTrash = useToTrash();
  const marks = useFavouriteMarks();
  const upload = useUploads();
  const picker = useFilePicker((files) => upload.start(loose(files), folderId));
  const folderPicker = useFilePicker((files) => upload.start(inFolder(files), folderId), {
    folder: true,
  });
  const close = () => setDialog(null);
  useEffect(() => {
    if (params.get('create') !== 'document' || !writable) return;
    setDialog({ type: 'document', title: params.get('title') ?? '' });
    setParams(
      (now) => {
        now.delete('create');
        now.delete('title');
        return now;
      },
      { replace: true },
    );
  }, [params, setParams, writable]);
  const ai = useAi();
  const [gathering, setGathering] = useState<Gathering | null>(null);
  const followed = useFollowedRun(gathering, () => setGathering(null), true);

  const sorted = sortNodes(
    items.filter((node) => !node.notes && !node.links && !node.boards),
    sort,
  );
  const parts = sections
    ? sections.map((section) => ({
        section,
        nodes: sorted.filter((node) => section.holds.has(node.id)),
      }))
    : [{ section: null, nodes: sorted }];
  const ordered = parts.flatMap((part) => part.nodes);
  const columns = COLUMNS.filter((column) => !showing || BRIEF.includes(column.key));
  const ids = ordered.map((node) => node.id);
  const choice = useChoice(ids);
  const chosen = ordered.filter((node) => choice.has(node.id));
  const glimpsed = ordered.find((node) => node.id === glance);
  const glanced =
    chosen.length > 0 ? chosen : glimpsed ? [glimpsed] : showing ? ordered.slice(0, 1) : [];
  const opened = useOpen();
  const open = (node: TreeNode) => opened(nodeHref(node));
  const shown = params.get('panel') === 'access' ? (params.get('node') ?? folderId) : null;
  const sharing = shown === folderId ? folder : items.find((node) => node.id === shown);
  const share = (node: TreeNode | null) =>
    setParams(!node || shown === node.id ? {} : { panel: 'access', node: node.id });
  const beside = wide && previewing && !sharing;
  const choose = (next: string[], from: string | null = choice.anchor) => choice.choose(next, from);
  const toggle = (id: string) => choice.toggle(id);
  const trash = (nodes: ListedNode[]) => {
    setGlance(null);
    choose([], null);
    toTrash.mutate(nodes.map((node) => node.id));
  };
  const moveInto = (parent: string) => (moving: string[]) =>
    move.mutate({ ids: moving, parent }, { onSuccess: () => choose([], null) });
  const preview = (on: boolean) => {
    setPreviewing(on);
    if (!showing) storePreview(on);
  };
  const sortBy = (key: SortKey) => {
    const next = { key, descending: sort.key === key && !sort.descending };
    setSort(next);
    storeSort(next);
  };
  const toggled = useRef<string | null>(null);
  const select = (node: TreeNode, event: MouseEvent) => {
    if (choice.pressed() || event.detail > 1) return;
    const choosing = choice.many > 0 || event.ctrlKey || event.metaKey;
    toggled.current = choosing ? node.id : null;
    if (choosing) choice.toggle(node.id, event.shiftKey);
    else if (beside) setGlance(node.id);
    else open(node);
  };

  const create = (fields: object) => (title: string) =>
    postJson<TreeNode>('/api/nodes', { ...fields, title, parent: folderId });

  const newItems = (
    <>
      <MenuItem
        icon={FileText}
        label={t('tree.newDocument')}
        disabled={!writable}
        onSelect={() => setDialog({ type: 'document' })}
      />
      <MenuItem
        icon={Folder}
        label={t('create.folder')}
        disabled={!writable}
        onSelect={() => setDialog({ type: 'folder' })}
      />
      <MenuItem
        icon={Globe}
        label={t('create.link')}
        disabled={!writable}
        onSelect={() => setDialog({ type: 'link' })}
      />
      <MenuSeparator />
      <MenuItem
        icon={FileUp}
        label={t('create.upload')}
        disabled={!writable}
        onSelect={picker.open}
      />
      <MenuItem
        icon={FolderUp}
        label={t('create.uploadFolder')}
        disabled={!writable}
        onSelect={folderPicker.open}
      />
      <MenuItem
        icon={ScanLine}
        label={t('create.scan')}
        disabled={!writable}
        onSelect={() => setDialog({ type: 'scan' })}
      />
    </>
  );

  const itemsFor = (nodes: ListedNode[]) => {
    const [single] = nodes.length === 1 ? nodes : [];
    const changeable = editable(nodes) && reachable;
    const inside = kept(nodes);
    return (
      <>
        {single && (
          <MenuItem icon={FolderOpen} label={t('tree.open')} onSelect={() => open(single)} />
        )}
        {single && (
          <MenuItem
            icon={Pencil}
            label={t(single.kind === 'link' ? 'tree.editLink' : 'tree.rename')}
            disabled={!changeable}
            onSelect={() => setDialog({ type: 'rename', node: single })}
          />
        )}
        {single?.kind === 'document' && (
          <MenuItem
            icon={Copy}
            label={t('copy.make')}
            disabled={inside}
            hint={inside ? t('confined.hint') : undefined}
            onSelect={() => setDialog({ type: 'copy', node: single })}
          />
        )}
        {joinable(nodes) && (
          <MenuItem
            icon={Combine}
            label={t('join.make')}
            disabled={inside}
            hint={inside ? t('confined.hint') : undefined}
            onSelect={() => setDialog({ type: 'join', nodes })}
          />
        )}
        <MenuItem
          icon={TableProperties}
          label={t('action.nodesExtract.ask')}
          disabled={
            !ai.data || inside || nodes.every((node) => savedOf(node) && kindOf(node) !== 'file')
          }
          hint={ai.data === false ? t('ai.off') : inside ? t('confined.hint') : undefined}
          onSelect={() => setDialog({ type: 'gather', nodes })}
        />
        <MenuItem
          icon={FolderInput}
          label={t('tree.move')}
          disabled={!changeable}
          onSelect={() => setDialog({ type: 'move', nodes })}
        />
        {single && kindOf(single) === 'board' && (
          <MenuItem
            icon={LayoutDashboard}
            label={t('boards.group')}
            disabled={!changeable}
            onSelect={() => setDialog({ type: 'group', node: single })}
          />
        )}
        {single?.kind === 'file' && (
          <MenuItem
            icon={Download}
            label={t('file.download')}
            disabled={confined || single.kept}
            hint={confined || single.kept ? t('confined.hint') : undefined}
            onSelect={() => location.assign(savedOf(single)!.href)}
          />
        )}
        {single && !visitor && (
          <MenuItem icon={Share2} label={t('access.share')} onSelect={() => share(single)} />
        )}
        <FavouriteItem nodes={nodes} marks={marks} />
        <KeepItem nodes={nodes} confined={inside} />
        <MenuSeparator />
        <MenuItem
          icon={Trash2}
          label={t('tree.toTrash')}
          disabled={!changeable}
          onSelect={() => trash(nodes)}
        />
      </>
    );
  };

  const area = useDropTarget({
    onFiles: writable ? (picked) => upload.start(picked, folderId) : undefined,
  });
  const failure =
    upload.error ?? toTrash.error ?? move.error ?? marks.change.error ?? followed.failure;

  return (
    <Frame
      path={path}
      root={root}
      title={title}
      actions={
        <>
          {wide && (
            <button
              type="button"
              aria-pressed={previewing}
              onClick={() => preview(!previewing)}
              className={`${button} aria-pressed:bg-selected`}
            >
              <PanelRight size={16} aria-hidden />
              <span className="sr-only lg:not-sr-only">{t('preview.title')}</span>
            </button>
          )}
          {folder && !visitor && (
            <button
              type="button"
              aria-pressed={shown === folder.id}
              onClick={() => share(folder)}
              className={`${button} aria-pressed:bg-selected`}
            >
              <Share2 size={16} aria-hidden />
              <span className="sr-only sm:not-sr-only">{t('access.share')}</span>
            </button>
          )}
        </>
      }
      primary={
        <Menu
          trigger={
            <button type="button" disabled={!writable} className={primaryButton}>
              <Plus size={16} aria-hidden />
              <span className="sr-only sm:not-sr-only">{t('create.new')}</span>
              <ChevronDown size={16} aria-hidden />
            </button>
          }
        >
          {newItems}
        </Menu>
      }
      panel={
        sharing ? (
          <AccessPanel key={sharing.id} node={sharing} onClose={() => share(null)} />
        ) : (
          wide &&
          previewing && (
            <PreviewPanel
              chosen={glanced}
              kept={kept(glanced)}
              column={showing ? WIDE_PANEL : undefined}
              onClose={() => preview(false)}
            />
          )
        )
      }
    >
      <ContextMenuArea
        items={menuOn === 'selection' ? itemsFor(chosen) : newItems}
        onOpen={(event) => {
          const id = (event.target as HTMLElement).closest('tr[data-id]')?.getAttribute('data-id');
          if (id && !choice.has(id)) choose([id], id);
          setMenuOn(id ? 'selection' : 'folder');
        }}
      >
        <div
          {...area.props}
          onClick={() => {
            choose([], null);
            setGlance(null);
          }}
          onKeyDown={(event) =>
            choice.onKeyDown(event, () => {
              if (editable(chosen)) trash(chosen);
            })
          }
          className={`flex min-h-full w-full max-w-5xl flex-col gap-3 rounded ${area.over ? 'outline-2 -outline-offset-2 outline-dashed outline-muted' : ''}`}
        >
          {above}
          {confined && (
            <p className="flex items-center gap-2 text-sm text-muted">
              <Lock size={14} aria-hidden />
              {t('confined.hint')}
            </p>
          )}
          {ordered.length === 0 ? (
            <p className="text-muted">{t(empty ?? 'tree.empty')}</p>
          ) : (
            <div>
              {chosen.length > 0 && (
                <ChoiceBar over all={choice.all}>
                  {joinable(chosen) && (
                    <button
                      type="button"
                      aria-label={t('join.make')}
                      title={t('join.make')}
                      disabled={kept(chosen)}
                      onClick={() => setDialog({ type: 'join', nodes: chosen })}
                      className={iconButton}
                    >
                      <Combine size={16} aria-hidden />
                    </button>
                  )}
                  <button
                    type="button"
                    aria-label={t('tree.move')}
                    title={t('tree.move')}
                    disabled={!editable(chosen)}
                    onClick={() => setDialog({ type: 'move', nodes: chosen })}
                    className={iconButton}
                  >
                    <FolderInput size={16} aria-hidden />
                  </button>
                  <button
                    type="button"
                    aria-label={t('tree.toTrash')}
                    title={t('tree.toTrash')}
                    disabled={!editable(chosen)}
                    onClick={() => trash(chosen)}
                    className={iconButton}
                  >
                    <Trash2 size={16} aria-hidden />
                  </button>
                  <ActionsMenu>{itemsFor(chosen)}</ActionsMenu>
                </ChoiceBar>
              )}
              <table className="w-full border-collapse">
                <thead className="text-left text-sm text-muted">
                  <tr className="h-10 border-b border-line">
                    <th className="w-10 px-3" />
                    {columns.map((column) => (
                      <th
                        key={column.key}
                        aria-sort={
                          sort.key === column.key
                            ? sort.descending
                              ? 'descending'
                              : 'ascending'
                            : undefined
                        }
                        className={`px-2 py-2 font-normal whitespace-nowrap ${column.className}`}
                      >
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            sortBy(column.key);
                          }}
                          className="inline-flex items-center gap-1 hover:text-ink"
                        >
                          {t(column.label)}
                          {sort.key === column.key &&
                            (sort.descending ? (
                              <ChevronDown size={14} aria-hidden />
                            ) : (
                              <ChevronUp size={14} aria-hidden />
                            ))}
                        </button>
                      </th>
                    ))}
                    {!showing && (
                      <th className="hidden px-2 py-2 font-normal whitespace-nowrap sm:table-cell">
                        {t('access.title')}
                      </th>
                    )}
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody onClick={(event) => event.stopPropagation()}>
                  {parts.map(({ section, nodes }) => (
                    <Fragment key={section?.key ?? 'all'}>
                      {section && (
                        <tr>
                          <th
                            scope="rowgroup"
                            colSpan={columns.length + (showing ? 2 : 3)}
                            className="px-3 pt-4 pb-1 text-left font-normal"
                          >
                            {section.heading}
                          </th>
                        </tr>
                      )}
                      {nodes.map((node) => (
                        <Row
                          key={node.id}
                          node={node}
                          brief={showing}
                          favourite={marks.ids.has(node.id)}
                          selected={choice.has(node.id)}
                          choosing={chosen.length > 0}
                          current={beside && chosen.length === 0 && glanced[0]?.id === node.id}
                          pressed={choice.press(() => toggle(node.id))}
                          dragged={() =>
                            choice.has(node.id) && chosen.length > 1
                              ? { ids: chosen.map((each) => each.id) }
                              : {
                                  ids: [node.id],
                                  saved: confined || node.kept ? undefined : savedOf(node),
                                }
                          }
                          menu={itemsFor([node])}
                          onSelect={(event) => select(node, event)}
                          onToggle={() => toggle(node.id)}
                          onOpen={() => open(node)}
                          onTwice={() => {
                            if (beside || toggled.current === node.id) open(node);
                          }}
                          onNodes={moveInto(node.id)}
                          onFiles={(picked) => upload.start(picked, node.id)}
                        />
                      ))}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div
            onClick={(event) => event.stopPropagation()}
            className="pointer-events-none sticky bottom-4 z-10 flex flex-col gap-2 empty:hidden *:pointer-events-auto"
          >
            {followed.bar}
          </div>
          {upload.pending && (
            <p className="text-sm text-muted" role="status">
              {upload.progress
                ? `${t('upload.progress')} ${formatNumber(upload.progress.done)} / ${formatNumber(upload.progress.total)} · ${formatSize(upload.progress.sent, formatNumber)} / ${formatSize(upload.progress.size, formatNumber)}`
                : t('file.uploading')}
            </p>
          )}
          {upload.unimported.length > 0 && (
            <p className="text-sm text-danger">
              {t('upload.unimported')}{' '}
              {upload.unimported
                .map(({ name, error }) => `${name} (${errorMessage(error, t)})`)
                .join(', ')}
            </p>
          )}
          {upload.failed.length > 0 && (
            <p className="text-sm text-danger">
              {t('upload.failed')}{' '}
              {upload.failed
                .map(({ name, error }) => `${name} (${errorMessage(error, t)})`)
                .join(', ')}
            </p>
          )}
          {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        </div>
      </ContextMenuArea>
      {picker.element}
      {folderPicker.element}
      {dialog?.type === 'folder' && (
        <NameDialog
          heading={t('create.folder')}
          submitLabel={t('tree.create')}
          onSubmit={create({ kind: 'folder' })}
          onDone={close}
          onClose={close}
        />
      )}
      {dialog?.type === 'document' && (
        <NameDialog
          heading={t('tree.newDocument')}
          submitLabel={t('tree.create')}
          initial={dialog.title}
          onSubmit={create({ kind: 'document' })}
          onDone={(node) => navigate(nodeHref(node))}
          onClose={close}
        />
      )}
      {dialog?.type === 'copy' && <CopyDialog node={dialog.node} onDone={close} onClose={close} />}
      {dialog?.type === 'link' && (
        <LinkDialog
          heading={t('create.link')}
          submitLabel={t('tree.create')}
          onSubmit={(given) =>
            postJson<TreeNode>('/api/nodes', { kind: 'link', parent: folderId, ...given })
          }
          onClose={close}
        />
      )}
      {dialog?.type === 'rename' && dialog.node.kind === 'link' && (
        <LinkDialog
          heading={t('tree.editLink')}
          submitLabel={t('tree.save')}
          link={dialog.node}
          onSubmit={(given) => patchJson(`/api/nodes/${dialog.node.id}`, given)}
          onClose={close}
        />
      )}
      {dialog?.type === 'rename' && dialog.node.kind !== 'link' && (
        <NameDialog
          heading={t('tree.rename')}
          submitLabel={t('tree.save')}
          initial={dialog.node.title}
          onSubmit={(title) => patchJson(`/api/nodes/${dialog.node.id}`, { title })}
          onDone={close}
          onClose={close}
        />
      )}
      {dialog?.type === 'move' && <MoveDialog nodes={dialog.nodes} onClose={close} />}
      {dialog?.type === 'group' && (
        <NameDialog
          heading={t('boards.group')}
          submitLabel={t('tree.move')}
          onSubmit={(group) => postJson('/api/nodes/boards', { node: dialog.node.id, group })}
          onDone={close}
          onClose={close}
        />
      )}
      {dialog?.type === 'gather' && (
        <GatherDialog
          nodes={dialog.nodes}
          name={dialog.nodes.length === 1 ? dialog.nodes[0].title : (folder?.title ?? null)}
          onStarted={(started) => {
            setGathering(started);
            choose([], null);
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'join' && (
        <Suspense fallback={null}>
          <JoinDialog
            files={dialog.nodes}
            onDone={(joined) => navigate(nodeHref(joined))}
            onClose={close}
          />
        </Suspense>
      )}
      {dialog?.type === 'scan' && (
        <Suspense fallback={null}>
          <ScanDialog
            parent={folderId}
            onDone={(scanned) => navigate(nodeHref(scanned))}
            onClose={close}
          />
        </Suspense>
      )}
    </Frame>
  );
}

function TopPage({
  root,
  query,
  above,
  empty,
}: {
  root: Root;
  query: ReturnType<typeof useShared>;
  above?: ReactNode;
  empty?: MessageKey;
}) {
  return (
    <Loaded query={query}>
      {({ children }) => (
        <Explorer
          key={root}
          folder={null}
          root={root}
          role={null}
          confined={false}
          path={[]}
          items={children}
          above={above}
          empty={empty ?? EMPTY[root]}
        />
      )}
    </Loaded>
  );
}

/** A group's heading; the user's own group is renamed or trashed from its long press. */
function BoardGroup({
  title,
  count,
  group,
}: {
  title: string;
  count: number;
  group: { id: string; title: string } | null;
}) {
  const { t, formatNumber } = useI18n();
  const toTrash = useToTrash();
  const press = useMenuPress();
  const [renaming, setRenaming] = useState(false);
  const heading = (
    <header
      {...(group ? press : {})}
      className="flex min-h-8 min-w-0 items-center gap-2 select-none [-webkit-touch-callout:none]"
    >
      <h2 className="truncate text-base font-semibold text-ink">{title}</h2>
      <span className="text-sm text-muted">{formatNumber(count)}</span>
      {toTrash.error && (
        <span className="text-xs text-danger">{errorMessage(toTrash.error, t)}</span>
      )}
    </header>
  );
  if (!group) return heading;
  return (
    <>
      <ContextMenuArea
        items={
          <>
            <MenuItem icon={Pencil} label={t('tree.rename')} onSelect={() => setRenaming(true)} />
            <MenuItem
              icon={Trash2}
              label={t('tree.toTrash')}
              disabled={toTrash.isPending}
              onSelect={() => toTrash.mutate([group.id])}
            />
          </>
        }
      >
        {heading}
      </ContextMenuArea>
      {renaming && (
        <NameDialog
          heading={t('tree.rename')}
          submitLabel={t('tree.save')}
          initial={group.title}
          onSubmit={(renamed) => patchJson(`/api/nodes/${group.id}`, { title: renamed })}
          onDone={() => setRenaming(false)}
          onClose={() => setRenaming(false)}
        />
      )}
    </>
  );
}

/** The boards under their groups: the user's own by name, those without one after them, then
 * what others share, by where it comes from. */
function boardSections(
  boards: (ListedNode & FoundNode)[],
  t: (key: MessageKey) => string,
): Section[] {
  const found = new Map<
    string,
    { rank: number; title: string; group: FoundNode['path'][number] | null; holds: Set<string> }
  >();
  for (const board of boards) {
    const key = `${board.root}:${board.path.at(-1)?.id ?? ''}`;
    const held = found.get(key);
    if (held) {
      held.holds.add(board.id);
      continue;
    }
    const own = board.root === 'mine';
    const named = own ? board.path.slice(1) : [];
    found.set(key, {
      rank: !own ? 2 : named.length ? 0 : 1,
      title: own
        ? named.map((step) => step.title).join(' › ') || t('links.ungrouped')
        : placeText(board, t),
      group: named.at(-1) ?? null,
      holds: new Set([board.id]),
    });
  }
  return [...found.entries()]
    .sort(([, one], [, other]) => one.rank - other.rank || one.title.localeCompare(other.title))
    .map(([key, { title, group, holds }]) => ({
      key,
      holds,
      heading: <BoardGroup title={title} count={holds.size} group={group} />,
    }));
}

export function BoardsPage() {
  const { t } = useI18n();
  return (
    <Loaded query={useBoards()}>
      {({ children }) => (
        <Explorer
          folder={null}
          role={null}
          confined={false}
          path={[]}
          items={children}
          empty="boards.empty"
          title={t('boards.title')}
          showing
          sections={boardSections(children, t)}
        />
      )}
    </Loaded>
  );
}

/** What the user keeps at hand, under the place each lives in. */
function favouriteSections(
  favourites: (ListedNode & FoundNode)[],
  t: (key: MessageKey) => string,
): Section[] {
  const found = new Map<string, Set<string>>();
  for (const node of favourites) {
    const place = placeText(node, t);
    found.set(place, (found.get(place) ?? new Set()).add(node.id));
  }
  return [...found.entries()]
    .sort(([one], [other]) => one.localeCompare(other))
    .map(([place, holds]) => ({
      key: place,
      holds,
      heading: <BoardGroup title={place} count={holds.size} group={null} />,
    }));
}

export function FavouritesPage() {
  const { t } = useI18n();
  return (
    <Loaded query={useFavourites()}>
      {({ children }) => (
        <Explorer
          folder={null}
          role={null}
          confined={false}
          path={[]}
          items={children}
          empty="favourites.empty"
          title={t('favourites.title')}
          sections={favouriteSections(children, t)}
        />
      )}
    </Loaded>
  );
}

export function SharedPage() {
  const { t } = useI18n();
  const [params, setParams] = useSearchParams();
  const byMe = params.get('by') === 'me';
  const query = useShared(byMe);
  return (
    <TopPage
      root="shared"
      query={query}
      empty={byMe ? 'tree.sharedByMeEmpty' : 'tree.sharedEmpty'}
      above={
        <div
          role="group"
          aria-label={t('tree.shared')}
          className="flex self-start rounded-lg bg-raised p-0.5"
        >
          {([false, true] as const).map((me) => (
            <button
              key={String(me)}
              type="button"
              aria-pressed={me === byMe}
              onClick={() => setParams(me ? { by: 'me' } : {}, { replace: true })}
              className="rounded-md px-3 py-1 text-sm text-muted hover:text-ink aria-pressed:bg-surface aria-pressed:font-semibold aria-pressed:text-ink aria-pressed:shadow-sm"
            >
              {t(me ? 'tree.sharedByMe' : 'tree.sharedWithMe')}
            </button>
          ))}
        </div>
      }
    />
  );
}

export function CompanyPage() {
  return <TopPage root="company" query={useCompany()} />;
}

export function FolderPage() {
  const segment = useParams().folder;
  const folderId = segment === undefined ? null : idIn(segment);
  return folderId === null && segment !== undefined ? (
    <Missing />
  ) : (
    <OpenFolder folderId={folderId} />
  );
}

function OpenFolder({ folderId }: { folderId: string | null }) {
  const wide = useWide();
  const query = useFolder(folderId, { stays: true });
  return (
    <Loaded query={query}>
      {({ folder, root, role, confined, path, children }) =>
        (folder?.notes || folder?.links || folder?.boards || path[0]?.boards) &&
        !query.isPlaceholderData ? (
          <Navigate to={folder?.notes ? '/notes' : folder?.links ? '/links' : '/boards'} replace />
        ) : (
          <Addressed
            href={query.isPlaceholderData ? null : folder ? nodeHref(folder) : '/documents'}
          >
            <Explorer
              key={folder?.id ?? 'root'}
              folder={folder}
              root={root}
              role={role}
              confined={confined}
              path={path}
              items={children}
              above={folder || wide ? undefined : <PhonePlaces />}
            />
          </Addressed>
        )
      }
    </Loaded>
  );
}
