import { useQueryClient } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronRight,
  Columns3,
  FileUp,
  Folder,
  FolderInput,
  Globe,
  LayoutGrid,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';
import { useRef, useState, type CSSProperties, type DragEvent, type ReactNode } from 'react';
import { FavouriteItem, useFavouriteMarks } from './favourites';
import { Link } from 'react-router';
import { patchJson, postJson, upload } from './api';
import { ChoiceBar, ChoiceBox, useChoice, type Choice } from './choice';
import { LinkDialog, NameDialog } from './dialogs';
import { endDrag, startDrag } from './drag';
import { Frame, Loading } from './frame';
import { useI18n } from './i18n';
import { LINKS, useLinks, type Links, type Listed } from './linksData';
import { runJob } from './jobs';
import { ContextMenuArea, Menu, MenuItem, MenuSeparator, MenuSub } from './menu';
import { useMenuPress } from './press';
import { iconButton, primaryButton } from './styles';
import {
  errorMessage,
  Failure,
  LinkIcon,
  nodeHref,
  PlaceLink,
  ROOT_CRUMBS,
  ROOT_LABELS,
  useMove,
  useToTrash,
  useTreeChange,
  type FoundNode,
  type Root,
  type TreeNode,
  stepTitle,
} from './tree';
import { IMAGE_ACCEPT, useFilePicker } from './upload';

/** The links of one folder: one of the user's own groups, or a folder of the organisation's or
 * of what others share, under the path the user finds it along. */
interface Group {
  folder: string | null;
  root: Root;
  path: FoundNode['path'];
  /** The user's own group; the links at the top of their folder of links have none. */
  own?: Listed;
  /** Among the user's own links. */
  mine: boolean;
  links: Listed[];
}

type Dragged = { links: string[] } | { group: Listed };

/** Where a drag would drop: links before or after a tile of a group or at the end of it, a group
 * before or after another, an image onto a tile as its icon. */
type Spot =
  | { into: string; at: string | null; after: boolean }
  | { group: string; after: boolean }
  | { icon: string };

const ROOTS: Root[] = ['mine', 'company', 'shared'];
const LOADABLE = `.html,.htm,.yaml,.yml,${IMAGE_ACCEPT}`;

/** The user's folder of links, made when there is none yet. */
function usePlace(given: string | null) {
  const queryClient = useQueryClient();
  return async (): Promise<string> => {
    if (given) return given;
    const made = await postJson<TreeNode>('/api/links', {});
    await queryClient.invalidateQueries({ queryKey: LINKS });
    return made.id;
  };
}

function parentOf(group: Listed): string | null {
  return group.path.at(-1)?.id ?? null;
}

function ownName(group: Listed): string {
  return [...group.path.slice(1).map((above) => above.title), group.title].join(' › ');
}

/** The groups each followed by the groups inside it. */
function inOrder(place: string | null, groups: Listed[]): Listed[] {
  const below = new Map<string | null, Listed[]>();
  for (const group of groups)
    below.set(parentOf(group), [...(below.get(parentOf(group)) ?? []), group]);
  const ordered: Listed[] = [];
  const walk = (id: string | null) => {
    for (const group of below.get(id) ?? []) {
      ordered.push(group);
      walk(group.id);
    }
  };
  if (place) walk(place);
  return ordered;
}

function grouped({ folder, groups, links }: Links): { own: Group[]; others: Group[] } {
  const own: Group[] = [
    { folder, root: 'mine', path: [], mine: true, links: [] },
    ...inOrder(folder, groups).map((group) => ({
      folder: group.id,
      root: 'mine' as Root,
      path: [],
      own: group,
      mine: true,
      links: [],
    })),
  ];
  const byFolder = new Map(own.map((group) => [group.folder, group]));
  const others = new Map<string, Group>();
  for (const link of links) {
    const at = link.path.at(-1)?.id ?? null;
    const mine = byFolder.get(at);
    if (mine && link.root === 'mine') {
      mine.links.push(link);
      continue;
    }
    const key = `${link.root}:${at}`;
    const group = others.get(key) ?? {
      folder: at,
      root: link.root,
      path: link.path,
      mine: false,
      links: [],
    };
    group.links.push(link);
    others.set(key, group);
  }
  const named = (group: Group) => group.path.map((above) => above.title).join('\u0000');
  return {
    own,
    others: [...others.values()].sort(
      (one, other) =>
        ROOTS.indexOf(one.root) - ROOTS.indexOf(other.root) ||
        named(one).localeCompare(named(other), 'hr'),
    ),
  };
}

function site(href: string): string {
  return new URL(href).hostname.replace(/^www\./, '');
}

function sameSpot(one: Spot | null, other: Spot | null): boolean {
  return JSON.stringify(one) === JSON.stringify(other);
}

function beyondHalf(event: DragEvent, across: boolean): boolean {
  const box = event.currentTarget.getBoundingClientRect();
  return across
    ? event.clientX > box.left + box.width / 2
    : event.clientY > box.top + box.height / 2;
}

function oneImage(event: DragEvent): File | null {
  const files = [...event.dataTransfer.files];
  return files.length === 1 && files[0].type.startsWith('image/') ? files[0] : null;
}

function Heading({ group }: { group: Group }) {
  const { t } = useI18n();
  const last = group.path.at(-1);
  return (
    <h2 className="flex min-w-0 flex-wrap items-center gap-1 text-base font-semibold text-muted">
      <Link to={ROOT_CRUMBS[group.root].href} className="hover:text-ink hover:underline">
        {t(ROOT_LABELS[group.root])}
      </Link>
      {group.path.map((above) => (
        <span key={above.id} className="flex min-w-0 items-center gap-1">
          <ChevronRight size={14} aria-hidden className="shrink-0" />
          <Link
            to={nodeHref(above)}
            className={`truncate hover:underline ${above === last ? 'text-ink' : 'hover:text-ink'}`}
          >
            {stepTitle(above, t)}
          </Link>
        </span>
      ))}
    </h2>
  );
}

const tile = 'flex h-full min-h-[4.25rem] w-full items-center gap-3 rounded-xl border p-3';
const marker = 'pointer-events-none absolute rounded-full bg-accent';

function Tile({
  link,
  choice,
  spot,
  draggable,
  items,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
}: {
  link: Listed;
  choice: Choice<string>;
  spot: Spot | null;
  draggable: boolean;
  /** What can be done to the link, from its menu; none where the user only reads it. */
  items: ReactNode;
  onDragStart: (event: DragEvent) => void;
  onDragEnd: () => void;
  onDragOver: (event: DragEvent) => void;
  onDrop: (event: DragEvent) => void;
}) {
  const picked = choice.has(link.id);
  const lands = spot && 'at' in spot && spot.at === link.id ? spot : null;
  const iconing = spot && 'icon' in spot && spot.icon === link.id;
  const shown = (
    <li
      className="relative"
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <PlaceLink
        {...(items ? choice.opener(link.id) : {})}
        to={nodeHref(link)}
        title={link.title}
        className={`${tile} shadow-sm transition select-none [-webkit-touch-callout:none] hover:-translate-y-0.5 hover:border-accent hover:shadow-md ${picked ? 'border-accent bg-selected' : 'border-line bg-raised'} ${iconing ? 'ring-2 ring-accent' : ''} ${choice.many > 0 && items ? 'pr-9' : ''}`}
      >
        <LinkIcon link={link} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate font-medium">{link.title}</span>
          <span className="truncate text-xs text-muted">
            {link.description || site(link.href ?? '')}
          </span>
        </span>
      </PlaceLink>
      {choice.many > 0 && items && (
        <ChoiceBox
          checked={picked}
          onToggle={(range) => choice.toggle(link.id, range)}
          className="absolute top-2 right-2"
        />
      )}
      {lands && (
        <span className={`${marker} inset-y-2 w-1 ${lands.after ? '-right-2' : '-left-2'}`} />
      )}
    </li>
  );
  return items ? <ContextMenuArea items={items}>{shown}</ContextMenuArea> : shown;
}

const COLUMNS = [1, 2, 3, 4, 5, 6];

/** The heading of one of the user's groups, whose long press opens what can be done to it. */
function GroupHeading({
  group,
  name,
  count,
  draggable,
  onDragStart,
  onDragEnd,
  onRename,
  onAdd,
}: {
  group: Listed;
  name: string;
  count: number;
  draggable: boolean;
  onDragStart: (event: DragEvent) => void;
  onDragEnd: () => void;
  onRename: (group: Listed) => void;
  onAdd: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const toTrash = useToTrash();
  const columns = useTreeChange((value: number | null) =>
    patchJson(`/api/nodes/${group.id}`, { columns: value }),
  );
  const press = useMenuPress();
  const failed = columns.error ?? toTrash.error;
  const items = (
    <>
      <MenuItem icon={Globe} label={t('create.link')} onSelect={onAdd} />
      <MenuItem icon={Pencil} label={t('tree.rename')} onSelect={() => onRename(group)} />
      <MenuSub icon={Columns3} label={t('links.columns')}>
        <MenuItem
          icon={LayoutGrid}
          label={t('links.columnsAuto')}
          checked={group.columns === null}
          onSelect={() => columns.mutate(null)}
        />
        {COLUMNS.map((each) => (
          <MenuItem
            key={each}
            icon={Columns3}
            label={formatNumber(each)}
            checked={group.columns === each}
            onSelect={() => columns.mutate(each)}
          />
        ))}
      </MenuSub>
      <MenuItem
        icon={Trash2}
        label={t('tree.toTrash')}
        disabled={toTrash.isPending}
        onSelect={() => toTrash.mutate([group.id])}
      />
    </>
  );
  return (
    <ContextMenuArea items={items}>
      <header
        {...press}
        draggable={draggable}
        onDragStart={(event) => {
          press.onDragStart();
          onDragStart(event);
        }}
        onDragEnd={onDragEnd}
        className="flex min-h-8 min-w-0 items-center gap-2 select-none [-webkit-touch-callout:none]"
      >
        <h2 className="truncate text-base font-semibold">{name}</h2>
        <span className="text-sm text-muted">{formatNumber(count)}</span>
        {failed && <span className="text-xs text-danger">{errorMessage(failed, t)}</span>}
      </header>
    </ContextMenuArea>
  );
}

/** The heading of a folder of the organisation's or of what others share; where the user may add
 * to it, its long press offers a new link. */
function FolderHeading({ group, onAdd }: { group: Group; onAdd: (() => void) | null }) {
  const { t, formatNumber } = useI18n();
  const press = useMenuPress();
  const heading = (
    <div
      {...(onAdd ? press : {})}
      className="flex min-h-8 min-w-0 items-center gap-2 select-none [-webkit-touch-callout:none]"
    >
      <Heading group={group} />
      <span className="text-sm text-muted">{formatNumber(group.links.length)}</span>
    </div>
  );
  if (!onAdd) return heading;
  return (
    <ContextMenuArea items={<MenuItem icon={Globe} label={t('create.link')} onSelect={onAdd} />}>
      {heading}
    </ContextMenuArea>
  );
}

/** At most the columns the group is given, fewer where the page is too narrow for them. */
function columnsOf(group: Group): CSSProperties | undefined {
  const columns = group.own?.columns;
  if (!columns) return undefined;
  return {
    gridTemplateColumns: `repeat(auto-fill, minmax(max(10rem, calc((100% - ${columns - 1} * 0.75rem) / ${columns})), 1fr))`,
  };
}

type Dialog =
  | { making: 'link'; into: string | null }
  | { making: 'group' }
  | { editing: Listed }
  | { renaming: Listed };

export function LinksPage() {
  const { t } = useI18n();
  const links = useLinks();
  const folder = links.data?.folder ?? null;
  const place = usePlace(folder);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const dragged = useRef<Dragged | null>(null);
  const [dragging, setDragging] = useState<'links' | 'group' | null>(null);
  const [spot, setSpot] = useState<Spot | null>(null);
  const move = useMove();
  const toTrash = useToTrash();
  const marks = useFavouriteMarks();
  const load = useTreeChange(async (files: File[]) => {
    const parent = await place();
    const given = await Promise.all(
      files.map(async (file) => ({ blob: (await upload(file)).sha256, name: file.name })),
    );
    return runJob('links', { parent, files: given }, files.map((file) => file.name).join(', '));
  });
  const icon = useTreeChange(async ({ link, file }: { link: Listed; file: File }) =>
    patchJson(`/api/nodes/${link.id}`, { icon: { blob: (await upload(file)).sha256 } }),
  );
  const picker = useFilePicker((files) => load.mutate(files), { accept: LOADABLE });
  const { own, others } = links.data ? grouped(links.data) : { own: [], others: [] };
  const groups = own.flatMap((group) => (group.own ? [group.own] : []));
  const changeable = [...own, ...others].flatMap((group) =>
    group.links.filter((link) => link.role !== 'read'),
  );
  const choice = useChoice(changeable.map((link) => link.id));
  const chosen = changeable.filter((link) => choice.has(link.id));
  const fine = matchMedia('(pointer: fine)').matches;
  const failed = load.error ?? move.error ?? icon.error ?? toTrash.error ?? marks.change.error;
  const close = () => setDialog(null);
  const done = { onSuccess: () => choice.choose([]) };

  function moveTo(ids: string[], into: Group) {
    move.mutate({ ids, parent: into.folder, before: null }, done);
  }

  function aim(next: Spot | null) {
    setSpot((current) => (sameSpot(current, next) ? current : next));
  }

  function started(event: DragEvent, held: Dragged) {
    event.stopPropagation();
    dragged.current = held;
    startDrag(event, 'links' in held ? held.links : [held.group.id]);
    // Laid out again while the drag starts, the page would lose it.
    window.setTimeout(() => setDragging('links' in held ? 'links' : 'group'));
  }

  function ended() {
    dragged.current = null;
    setDragging(null);
    setSpot(null);
    endDrag();
  }

  function dropped() {
    const held = dragged.current;
    const at = spot;
    ended();
    if (!held || !at) return;
    if ('links' in held && 'into' in at) {
      const into = own.find((group) => group.folder === at.into);
      if (!into || (at.at && held.links.includes(at.at))) return;
      const rest = into.links.filter((link) => !held.links.includes(link.id));
      const index = rest.findIndex((link) => link.id === at.at);
      const before = !at.at ? null : at.after ? (rest[index + 1]?.id ?? null) : at.at;
      move.mutate({ ids: held.links, parent: at.into, before }, done);
    } else if ('group' in held && 'group' in at) {
      const siblings = groups.filter(
        (group) => parentOf(group) === parentOf(held.group) && group.id !== held.group.id,
      );
      const index = siblings.findIndex((group) => group.id === at.group);
      const before = at.after ? (siblings[index + 1]?.id ?? null) : at.group;
      move.mutate({ ids: [held.group.id], parent: parentOf(held.group), before });
    }
  }

  function linkItems(link: Listed) {
    const favourite = <FavouriteItem nodes={[link]} marks={marks} />;
    if (link.role === 'read') return favourite;
    return (
      <>
        {favourite}
        <MenuItem
          icon={Pencil}
          label={t('tree.editLink')}
          onSelect={() => setDialog({ editing: link })}
        />
        {link.root === 'mine' && own.length > 1 && (
          <MenuSub icon={FolderInput} label={t('links.moveTo')}>
            {own.map((group) => (
              <MenuItem
                key={group.folder ?? ''}
                icon={Folder}
                label={group.own ? ownName(group.own) : t('links.ungrouped')}
                disabled={group.folder === (link.path.at(-1)?.id ?? null)}
                onSelect={() => moveTo([link.id], group)}
              />
            ))}
          </MenuSub>
        )}
        <MenuItem
          icon={Trash2}
          label={t('tree.toTrash')}
          onSelect={() => toTrash.mutate([link.id])}
        />
      </>
    );
  }

  function section(group: Group) {
    const name = group.own
      ? ownName(group.own)
      : group.mine
        ? t('links.ungrouped')
        : [t(ROOT_LABELS[group.root]), ...group.path.map((above) => above.title)].join(' / ');
    if (group.mine && !group.own && !group.links.length && dragging !== 'links') return null;
    const into = group.mine ? group.folder : null;
    const landing =
      spot && 'group' in spot && group.own && spot.group === group.own.id ? spot : null;
    const ending = spot && 'into' in spot && spot.into === into && !spot.at;
    const add = () => setDialog({ making: 'link', into: group.folder });
    return (
      <section
        key={`${group.mine ? 'own' : group.root}:${group.folder}`}
        aria-label={name}
        className="relative flex flex-col gap-3"
        onDragOver={(event) => {
          const held = dragged.current;
          if (held && 'links' in held && into) {
            event.preventDefault();
            event.stopPropagation();
            if (!(spot && 'into' in spot && spot.into === into && spot.at))
              aim({ into, at: group.links.at(-1)?.id ?? null, after: true });
          } else if (
            held &&
            'group' in held &&
            group.own &&
            held.group.id !== group.own.id &&
            parentOf(held.group) === parentOf(group.own)
          ) {
            event.preventDefault();
            event.stopPropagation();
            aim({ group: group.own.id, after: beyondHalf(event, false) });
          }
        }}
        onDrop={(event) => {
          if (!dragged.current) return;
          event.preventDefault();
          event.stopPropagation();
          dropped();
        }}
      >
        {group.own ? (
          <GroupHeading
            group={group.own}
            name={name}
            count={group.links.length}
            draggable={fine}
            onDragStart={(event) => started(event, { group: group.own! })}
            onDragEnd={ended}
            onRename={(renaming) => setDialog({ renaming })}
            onAdd={add}
          />
        ) : (
          !group.mine && (
            <FolderHeading
              group={group}
              onAdd={group.links.some((link) => link.role !== 'read') ? add : null}
            />
          )
        )}
        <ul
          style={columnsOf(group)}
          className={`grid gap-3 ${group.own?.columns ? '' : 'grid-cols-[repeat(auto-fill,minmax(15rem,1fr))]'}`}
        >
          {group.links.map((link) => {
            const mine = group.mine && link.role !== 'read';
            return (
              <Tile
                key={link.id}
                link={link}
                choice={choice}
                spot={spot}
                draggable={fine && mine}
                items={linkItems(link)}
                onDragStart={(event) =>
                  started(event, { links: choice.has(link.id) ? choice.chosen : [link.id] })
                }
                onDragEnd={ended}
                onDragOver={(event) => {
                  const held = dragged.current;
                  if (!held && link.role !== 'read' && event.dataTransfer.types.includes('Files')) {
                    event.preventDefault();
                    event.stopPropagation();
                    event.dataTransfer.dropEffect = 'copy';
                    aim({ icon: link.id });
                  } else if (held && 'links' in held && into) {
                    event.preventDefault();
                    event.stopPropagation();
                    aim({ into, at: link.id, after: beyondHalf(event, true) });
                  }
                }}
                onDrop={(event) => {
                  if (dragged.current) return;
                  event.preventDefault();
                  event.stopPropagation();
                  setSpot(null);
                  const image = oneImage(event);
                  if (image && link.role !== 'read') icon.mutate({ link, file: image });
                  else if (event.dataTransfer.files.length)
                    load.mutate([...event.dataTransfer.files]);
                }}
              />
            );
          })}
          {into && !group.links.length && (
            <li
              className={`${tile} border-dashed text-sm text-muted ${ending ? 'border-accent bg-selected' : 'border-line'}`}
            >
              {t('links.empty')}
            </li>
          )}
        </ul>
        {landing && (
          <span className={`${marker} inset-x-0 h-1 ${landing.after ? '-bottom-5' : '-top-5'}`} />
        )}
      </section>
    );
  }

  return (
    <Frame
      title={t('links.title')}
      primary={
        <Menu
          trigger={
            <button type="button" disabled={!links.data} className={primaryButton}>
              <Plus size={16} aria-hidden />
              <span className="sr-only sm:not-sr-only">{t('create.new')}</span>
              <ChevronDown size={16} aria-hidden />
            </button>
          }
        >
          <MenuItem
            icon={Globe}
            label={t('create.link')}
            onSelect={() => setDialog({ making: 'link', into: null })}
          />
          <MenuItem
            icon={Folder}
            label={t('links.newGroup')}
            onSelect={() => setDialog({ making: 'group' })}
          />
          <MenuSeparator />
          <MenuItem
            icon={FileUp}
            label={t('links.load')}
            disabled={load.isPending}
            onSelect={picker.open}
          />
        </Menu>
      }
    >
      <section
        className="flex w-full max-w-6xl flex-col gap-10"
        onKeyDown={(event) =>
          choice.onKeyDown(event, () =>
            toTrash.mutate(
              chosen.map((link) => link.id),
              done,
            ),
          )
        }
        onDragOver={(event) => {
          if (dragged.current || !event.dataTransfer.types.includes('Files')) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = 'copy';
          aim(null);
        }}
        onDrop={(event) => {
          if (dragged.current || !event.dataTransfer.files.length) return;
          event.preventDefault();
          load.mutate([...event.dataTransfer.files]);
        }}
      >
        {picker.element}
        {choice.many > 0 && (
          <ChoiceBar all={choice.all}>
            {chosen.length === 1 && (
              <button
                type="button"
                aria-label={t('tree.editLink')}
                title={t('tree.editLink')}
                onClick={() => setDialog({ editing: chosen[0] })}
                className={iconButton}
              >
                <Pencil size={16} aria-hidden />
              </button>
            )}
            {folder && (
              <Menu
                align="start"
                trigger={
                  <button
                    type="button"
                    aria-label={t('links.moveTo')}
                    title={t('links.moveTo')}
                    className={iconButton}
                  >
                    <FolderInput size={16} aria-hidden />
                  </button>
                }
              >
                {own.map((group) => (
                  <MenuItem
                    key={group.folder ?? ''}
                    icon={Folder}
                    label={group.own ? ownName(group.own) : t('links.ungrouped')}
                    disabled={move.isPending}
                    onSelect={() =>
                      moveTo(
                        chosen.map((link) => link.id),
                        group,
                      )
                    }
                  />
                ))}
              </Menu>
            )}
            <button
              type="button"
              aria-label={t('tree.toTrash')}
              title={t('tree.toTrash')}
              disabled={toTrash.isPending}
              onClick={() =>
                toTrash.mutate(
                  chosen.map((link) => link.id),
                  done,
                )
              }
              className={iconButton}
            >
              <Trash2 size={16} aria-hidden />
            </button>
          </ChoiceBar>
        )}
        {failed && <p className="text-sm text-danger">{errorMessage(failed, t)}</p>}
        {links.isPending ? (
          <Loading />
        ) : links.isError ? (
          <Failure error={links.error} />
        ) : (
          <>
            {(own[0].links.length ? own : [...own.slice(1), own[0]]).map(section)}
            {others.map(section)}
            {own.length === 1 && !own[0].links.length && !others.length && (
              <p className="text-muted">{t('links.empty')}</p>
            )}
          </>
        )}
        {dialog && 'making' in dialog && dialog.making === 'link' && (
          <LinkDialog
            heading={t('create.link')}
            submitLabel={t('tree.create')}
            onSubmit={async (given) =>
              postJson<TreeNode>('/api/nodes', {
                kind: 'link',
                parent: dialog.into ?? (await place()),
                ...given,
              })
            }
            onClose={close}
          />
        )}
        {dialog && 'making' in dialog && dialog.making === 'group' && (
          <NameDialog
            heading={t('links.newGroup')}
            submitLabel={t('tree.create')}
            onSubmit={async (title) =>
              postJson<TreeNode>('/api/nodes', { kind: 'folder', parent: await place(), title })
            }
            onDone={close}
            onClose={close}
          />
        )}
        {dialog && 'editing' in dialog && (
          <LinkDialog
            heading={t('tree.editLink')}
            submitLabel={t('tree.save')}
            link={dialog.editing}
            onSubmit={(given) => patchJson(`/api/nodes/${dialog.editing.id}`, given)}
            onClose={() => {
              close();
              choice.choose([]);
            }}
          />
        )}
        {dialog && 'renaming' in dialog && (
          <NameDialog
            heading={t('tree.rename')}
            submitLabel={t('tree.save')}
            initial={dialog.renaming.title}
            onSubmit={(title) => patchJson(`/api/nodes/${dialog.renaming.id}`, { title })}
            onDone={close}
            onClose={close}
          />
        )}
      </section>
    </Frame>
  );
}
