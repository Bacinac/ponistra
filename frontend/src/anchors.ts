/** A stretch of a tab's text: the JSON of the Yjs relative positions of its first character
 * and of its end, after its last one. */
export interface Anchor {
  from: object;
  to: object;
}

/** A cell of one of a tab's tables, by the ids of the table, its row and its column. */
export interface CellAnchor {
  table: string;
  row: string;
  col: string;
}

export function inCell(anchor: object): anchor is CellAnchor {
  return 'table' in anchor;
}

/** The tab's threads as its text has them. */
export interface InText {
  order: readonly string[];
  lost: readonly string[];
}
