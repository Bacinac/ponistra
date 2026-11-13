import { kindOf, type TreeNode } from './tree';

export type SortKey = 'title' | 'kind' | 'updated_at' | 'updated_by' | 'size';

export interface Sort {
  key: SortKey;
  descending: boolean;
}

const SORT_KEY = 'ponistra.sort';
const SORT_KEYS: SortKey[] = ['title', 'kind', 'updated_at', 'updated_by', 'size'];
const BY_TITLE: Sort = { key: 'title', descending: false };

export function storedSort(): Sort {
  try {
    const sort = JSON.parse(localStorage.getItem(SORT_KEY) ?? 'null') as Sort | null;
    if (sort && SORT_KEYS.includes(sort.key))
      return { key: sort.key, descending: !!sort.descending };
  } catch {
    return BY_TITLE;
  }
  return BY_TITLE;
}

const PREVIEW_KEY = 'ponistra.preview';

export function storedPreview(): boolean {
  try {
    return localStorage.getItem(PREVIEW_KEY) === 'on';
  } catch {
    return false;
  }
}

export function storePreview(on: boolean) {
  try {
    localStorage.setItem(PREVIEW_KEY, on ? 'on' : 'off');
  } catch {
    return;
  }
}

export function storeSort(sort: Sort) {
  try {
    localStorage.setItem(SORT_KEY, JSON.stringify(sort));
  } catch {
    return;
  }
}

const collator = new Intl.Collator('hr', { numeric: true, sensitivity: 'base' });

function compare(a: TreeNode, b: TreeNode, key: SortKey): number {
  switch (key) {
    case 'title':
      return collator.compare(a.title, b.title);
    case 'kind':
      return collator.compare(
        `${kindOf(a)} ${a.extension ?? ''}`,
        `${kindOf(b)} ${b.extension ?? ''}`,
      );
    case 'updated_at':
      return Date.parse(a.updated_at) - Date.parse(b.updated_at);
    case 'updated_by':
      return collator.compare(a.updated_by?.name ?? '', b.updated_by?.name ?? '');
    case 'size':
      return (a.size ?? -1) - (b.size ?? -1);
  }
}

export function sortNodes<T extends TreeNode>(nodes: T[], sort: Sort): T[] {
  return [...nodes].sort((a, b) => {
    const folders = Number(b.kind === 'folder') - Number(a.kind === 'folder');
    if (folders !== 0) return folders;
    const order = compare(a, b, sort.key) || collator.compare(a.title, b.title);
    return sort.descending ? -order : order;
  });
}

export function between<T>(ordered: T[], from: T, to: T): T[] {
  const start = ordered.indexOf(from);
  const end = ordered.indexOf(to);
  if (start < 0 || end < 0) return [to];
  return ordered.slice(Math.min(start, end), Math.max(start, end) + 1);
}

const UNITS = ['B', 'kB', 'MB', 'GB', 'TB'];

export function formatSize(bytes: number, formatNumber: (value: number) => string): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < UNITS.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${formatNumber(unit === 0 ? value : Math.round(value * 10) / 10)} ${UNITS[unit]}`;
}
