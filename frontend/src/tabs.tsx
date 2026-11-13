import { useMemo, useState, useSyncExternalStore, type DragEvent, type ReactNode } from 'react';
import { Link } from 'react-router';
import { segment } from './address';
import { tableNameText } from './editor/formulas';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { ContextMenuArea } from './menu';
import { useMenuPress } from './press';
import type { Tab } from './tree';

/** A tab's address under its document's or version's; the first tab's is that address itself. */
/** Where a search hit, a heading, a link or the name box leads in a tab: a block, or cells of
 * a table as the name box writes them, in the tab's first table where they name none or in the
 * block's. */
export interface Found {
  block: string | null;
  cell: string | null;
}

/** What the address's `block` and `cell` lead to, the same while they stay. */
export function useFound(params: URLSearchParams): Found | null {
  const block = params.get('block');
  const cell = params.get('cell');
  return useMemo(() => (block || cell ? { block, cell } : null), [block, cell]);
}

/** The query of an address leading to cells of a table (D16): `cell=B4` in the tab's first
 * table, `cell=Ulaz!B4` in another by its name, and beside its block where it has none. */
export function cellQuery(
  cells: string,
  table: { id: string; name: string | null; first: boolean },
): string {
  const cell = (text: string) => `cell=${encodeURIComponent(text)}`;
  if (table.first) return cell(cells);
  if (table.name) return cell(`${tableNameText(table.name)}!${cells}`);
  return `block=${encodeURIComponent(table.id)}&${cell(cells)}`;
}

export function tabHref(
  base: string,
  tab: Pick<Tab, 'id' | 'title'>,
  tabs?: readonly Pick<Tab, 'id'>[],
): string {
  return tabs?.[0]?.id === tab.id ? base : `${base}/${segment(tab.title, tab.id)}`;
}

// Tabs arrive depth first, so a parent is always seen before its subtabs.
export function tabDepths(tabs: readonly Tab[]): Map<string, number> {
  const depth = new Map<string, number>();
  for (const tab of tabs) depth.set(tab.id, tab.parent ? depth.get(tab.parent)! + 1 : 0);
  return depth;
}

export function tabLabel(tab: Tab, t: (key: MessageKey) => string): string {
  return tab.title || t('tab.untitled');
}

/** Where a tab goes: `position` counts the other subtabs of `parent`. */
export interface Place {
  parent: string | null;
  position: number;
}

export type Move = 'up' | 'down' | 'indent' | 'outdent';

export type Drop = 'before' | 'inside' | 'after';

function row(tabs: readonly Tab[], parent: string | null, without?: string): Tab[] {
  return tabs.filter((tab) => tab.parent === parent && tab.id !== without);
}

function indexIn(tabs: readonly Tab[], id: string): number {
  return tabs.findIndex((tab) => tab.id === id);
}

/** Where each move of a tab's menu takes it; null where it has nowhere to go. */
export function tabMoves(tabs: readonly Tab[], tab: Tab): Record<Move, Place | null> {
  const siblings = row(tabs, tab.parent);
  const at = indexIn(siblings, tab.id);
  const before = siblings[at - 1];
  const parent = tabs.find(({ id }) => id === tab.parent);
  return {
    up: before ? { parent: tab.parent, position: at - 1 } : null,
    down: at < siblings.length - 1 ? { parent: tab.parent, position: at + 1 } : null,
    indent: before ? { parent: before.id, position: row(tabs, before.id).length } : null,
    outdent: parent
      ? {
          parent: parent.parent,
          position: indexIn(row(tabs, parent.parent), parent.id) + 1,
        }
      : null,
  };
}

/** Where a tab dropped on another lands: before it, as its last subtab, or after it, which
 * under a tab with subtabs is as its first. Null where the tab would stay where it is. */
export function dropPlace(
  tabs: readonly Tab[],
  moving: string,
  target: Tab,
  drop: Drop,
): Place | null {
  for (let above: Tab | undefined = target; above;) {
    if (above.id === moving) return null;
    above = tabs.find(({ id }) => id === above!.parent);
  }
  const below = row(tabs, target.id, moving);
  let place: Place;
  if (drop === 'inside') place = { parent: target.id, position: below.length };
  else if (drop === 'after' && below.length) place = { parent: target.id, position: 0 };
  else {
    const at = indexIn(row(tabs, target.parent, moving), target.id);
    place = {
      parent: target.parent,
      position: drop === 'before' ? at : at + 1,
    };
  }
  const tab = tabs.find(({ id }) => id === moving)!;
  const now = indexIn(row(tabs, tab.parent), moving);
  return place.parent === tab.parent && place.position === now ? null : place;
}

function dropOf(event: DragEvent<HTMLElement>): Drop {
  const { top, height } = event.currentTarget.getBoundingClientRect();
  const y = (event.clientY - top) / height;
  return y < 0.25 ? 'before' : y > 0.75 ? 'after' : 'inside';
}

function lineAt(place: Place, depth: Map<string, number>): number {
  return place.parent ? depth.get(place.parent)! + 1 : 0;
}

const TAB = 'application/x-ponistra-tab';

let dragged: string | null = null;

export interface Heading {
  id: string;
  level: number;
  number: string | null;
  text: string;
}

/** The open tab's headings and the one whose section holds the cursor. */
export interface Outline {
  headings: Heading[];
  current: string | null;
}

function sameOutline(a: Outline | null, b: Outline | null): boolean {
  if (!a || !b) return a === b;
  return (
    a.current === b.current &&
    a.headings.length === b.headings.length &&
    a.headings.every(({ id, level, number, text }, index) => {
      const other = b.headings[index];
      return (
        other.id === id && other.level === level && other.number === number && other.text === text
      );
    })
  );
}

/** Written by the open tab's editor and read by the tab list, so typing re-renders the list
 * alone and only when a heading or the section around the cursor changes. */
export function outlineStore() {
  let outline: Outline | null = null;
  const listeners = new Set<() => void>();
  return {
    get: () => outline,
    set(next: Outline | null) {
      if (sameOutline(outline, next)) return;
      outline = next;
      for (const listener of listeners) listener();
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export type OutlineStore = ReturnType<typeof outlineStore>;

export function Headings({
  store,
  href,
  indent,
}: {
  store: OutlineStore;
  href: (block: string) => string;
  indent: number;
}) {
  const { t } = useI18n();
  const outline = useSyncExternalStore(store.subscribe, store.get);
  if (!outline?.headings.length) return null;
  const top = Math.min(...outline.headings.map(({ level }) => level));
  return (
    <ul aria-label={t('tab.headings')} style={{ paddingLeft: `${indent}rem` }}>
      {outline.headings.map((heading) => (
        <li key={heading.id} style={{ paddingLeft: `${(heading.level - top) * 0.75}rem` }}>
          <Link
            to={href(heading.id)}
            aria-current={heading.id === outline.current ? 'location' : undefined}
            className="block truncate rounded px-2 py-1 text-sm text-muted hover:bg-hover hover:text-ink aria-[current=location]:font-medium aria-[current=location]:text-ink"
          >
            {heading.number && <span className="tabular-nums">{heading.number} </span>}
            {heading.text}
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function TabList<T extends Tab>({
  tabs,
  current,
  href,
  menu,
  outline,
  onMove,
}: {
  tabs: T[];
  current?: T;
  href: (tab: T) => string;
  /** The tab's menu, opened by a right click or a long press on it. */
  menu?: (tab: T) => ReactNode;
  /** The open tab's headings, listed under it, each leading to its block. */
  outline?: { store: OutlineStore; href: (block: string) => string };
  /** Given, the tabs are dragged into a new order or under one another. */
  onMove?: (tab: T, place: Place) => void;
}) {
  const { t } = useI18n();
  const depth = tabDepths(tabs);
  const press = useMenuPress();
  const [target, setTarget] = useState<{
    id: string;
    drop: Drop;
    place: Place;
  } | null>(null);

  const dragging = (event: DragEvent<HTMLElement>, tab: T) => {
    if (!dragged || !event.dataTransfer.types.includes(TAB)) return null;
    const drop = dropOf(event);
    const place = dropPlace(tabs, dragged, tab, drop);
    return place && { drop, place };
  };

  return (
    <nav aria-label={t('tab.list')} className="flex flex-col gap-0.5">
      {tabs.map((tab) => {
        const indent = depth.get(tab.id)!;
        const shown = target?.id === tab.id ? target : null;
        const drop = shown?.drop;
        const link = (
          <Link
            {...(menu ? press : {})}
            to={href(tab)}
            draggable={onMove ? false : undefined}
            aria-current={tab.id === current?.id ? 'page' : undefined}
            className={`flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-hover aria-[current=page]:bg-selected aria-[current=page]:font-semibold ${menu ? 'select-none [-webkit-touch-callout:none]' : ''}`}
          >
            <span className="truncate">{tabLabel(tab, t)}</span>
          </Link>
        );
        return (
          <div key={tab.id} className="flex flex-col gap-0.5">
            <div
              draggable={Boolean(onMove)}
              onDragStart={
                onMove &&
                ((event) => {
                  dragged = tab.id;
                  event.dataTransfer.clearData();
                  event.dataTransfer.setData(TAB, tab.id);
                  event.dataTransfer.effectAllowed = 'move';
                })
              }
              onDragEnd={() => {
                dragged = null;
                setTarget(null);
              }}
              onDragOver={(event) => {
                const over = dragging(event, tab);
                setTarget((now) =>
                  now?.id === tab.id && now.drop === over?.drop
                    ? now
                    : over && { id: tab.id, ...over },
                );
                if (!over) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = 'move';
              }}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                  setTarget(null);
                }
              }}
              onDrop={(event) => {
                const over = dragging(event, tab);
                setTarget(null);
                if (!over) return;
                event.preventDefault();
                const moving = tabs.find(({ id }) => id === dragged)!;
                onMove?.(moving, over.place);
              }}
              style={{ paddingLeft: `${indent}rem` }}
              className={`relative flex items-center gap-1 rounded ${drop === 'inside' ? 'outline-2 -outline-offset-2 outline-focus' : ''}`}
            >
              {menu ? <ContextMenuArea items={menu(tab)}>{link}</ContextMenuArea> : link}
              {(drop === 'before' || drop === 'after') && (
                <span
                  aria-hidden
                  style={{ marginLeft: `${lineAt(shown!.place, depth)}rem` }}
                  className={`pointer-events-none absolute inset-x-0 h-0.5 rounded bg-focus ${drop === 'before' ? '-top-px' : '-bottom-px'}`}
                />
              )}
            </div>
            {outline && tab.id === current?.id && (
              <Headings store={outline.store} href={outline.href} indent={indent + 1} />
            )}
          </div>
        );
      })}
    </nav>
  );
}
