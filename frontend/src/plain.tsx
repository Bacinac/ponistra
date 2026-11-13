import type { ReactNode } from 'react';

const LINK = /\bhttps?:\/\/[^\s<>"']*[^\s<>"'.,;:!?)\]]/g;

/** Text as it was written, each web link in it opening in a tab of its own. */
export function PlainBody({ text }: { text: string }) {
  const pieces: ReactNode[] = [];
  let at = 0;
  for (const found of text.matchAll(LINK)) {
    pieces.push(text.slice(at, found.index));
    pieces.push(
      <a
        key={found.index}
        href={found[0]}
        target="_blank"
        rel="noopener noreferrer"
        className="text-link underline"
      >
        {found[0]}
      </a>,
    );
    at = found.index + found[0].length;
  }
  pieces.push(text.slice(at));
  return <div className="break-words whitespace-pre-wrap">{pieces}</div>;
}
