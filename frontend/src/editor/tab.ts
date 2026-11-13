import * as Y from 'yjs';

/** What a chart shows, as the server computed it from its range: each series' name (none where
 * the range names none), its values as numbers (none where a cell holds no number) and as the
 * cells show them, the categories as their cells show them, and a scatter's x values. */
export interface Drawn {
  series: { name: string | null; values: (number | null)[]; texts: string[] }[];
  labels: string[] | null;
  x?: (number | null)[];
}

/** A chart whose table or range is gone, or whose table could not be computed. */
export type Undrawn = { missing: true } | { failed: true };

/** The tab's text, as y-prosemirror lays it out. */
export function bodyOf(doc: Y.Doc): Y.XmlFragment {
  return doc.getXmlFragment('body');
}

/** What each chart shows, by the chart's id, written only by the server. */
export function chartsOf(doc: Y.Doc): Y.Map<Drawn | Undrawn> {
  return doc.getMap<Drawn | Undrawn>('charts');
}
