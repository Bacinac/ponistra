import { useCallback, useState } from 'react';
import type { TreeNode } from './tree';

/** How a document shows: one column of text, the pages it prints on, or its slides. */
export const VIEWS = ['text', 'pages', 'slides'] as const;
export type View = (typeof VIEWS)[number];

/** How large pages and slides show: as printed, though never wider than the pane, or as wide as
 * it. */
export const ZOOMS = ['page', 'width'] as const;
export type Zoom = (typeof ZOOMS)[number];

function stored<T extends string>(key: string, values: readonly T[]): T {
  try {
    const value = localStorage.getItem(key);
    return values.find((each) => each === value) ?? values[0];
  } catch {
    return values[0];
  }
}

/** A choice of the reader's own, kept in their browser for every document they open. */
function useStored<T extends string>(key: string, values: readonly T[]): [T, (value: T) => void] {
  const [value, setValue] = useState(() => stored(key, values));
  const choose = useCallback(
    (next: T) => {
      setValue(next);
      try {
        localStorage.setItem(key, next);
      } catch {
        return;
      }
    },
    [key],
  );
  return [value, choose];
}

const VIEWS_KEPT = 'ponistra.views';

function kept(): Record<string, unknown> {
  try {
    const found: unknown = JSON.parse(localStorage.getItem(VIEWS_KEPT) ?? '{}');
    return found && typeof found === 'object' ? (found as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

const NATIVE: Partial<Record<NonNullable<TreeNode['original']>, View>> = {
  pptx: 'slides',
  xlsx: 'text',
};

/** The view the reader chose for the document; for one they have not, the view of what it came
 * from, a presentation's slides and a workbook's sheets, else its pages. */
export function viewFor(documentId: string, original: TreeNode['original']): View {
  const chosen = VIEWS.find((each) => each === kept()[documentId]);
  return chosen ?? (original && NATIVE[original]) ?? 'pages';
}

export function keepView(documentId: string, view: View) {
  try {
    localStorage.setItem(VIEWS_KEPT, JSON.stringify({ ...kept(), [documentId]: view }));
  } catch {
    return;
  }
}

/** The document's view, kept in the reader's browser. */
export function useView(
  documentId: string,
  original: TreeNode['original'],
): [View, (view: View) => void] {
  const [view, setView] = useState(() => viewFor(documentId, original));
  const choose = useCallback(
    (next: View) => {
      setView(next);
      keepView(documentId, next);
    },
    [documentId],
  );
  return [view, choose];
}
export const useZoom = () => useStored('ponistra.zoom', ZOOMS);
