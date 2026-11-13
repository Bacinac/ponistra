import {
  CaseSensitive,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Search,
  WholeWord,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { getJson } from '../api';
import { useI18n } from '../i18n';
import { button, iconButton, primaryButton, smallField } from '../styles';
import type { Context } from './command';
import { firstFrom, goToHit, hitPlace, markHits, type Found } from './finding';
import { outerOf } from './tableBase';
import { tablesOf } from './tablesPlugin';

const NONE: Found = { hits: [], more: false };
const WAIT_MS = 250;

/** Find and replace over the tab: its text, notes and every row of its tables, as the server
 * reads them, the hits marked in the text and the current one brought into view. */
export function FindBar({
  context,
  replacing,
  onClose,
}: {
  context: Context;
  replacing: boolean;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const view = outerOf(context.view);
  const { doc } = context;
  const fail = useRef(context.fail);
  fail.current = context.fail;
  const { write, grids } = tablesOf(view.state);
  const tab = context.place.tab;
  const input = useRef<HTMLInputElement>(null);
  const shownFor = useRef('');
  const [text, setText] = useState(() => {
    const { from, to } = view.state.selection;
    const chosen = view.state.doc.textBetween(from, to);
    return chosen.includes('\n') ? '' : chosen;
  });
  const [by, setBy] = useState('');
  const [replace, setReplace] = useState(replacing && write !== null);
  const [cased, setCased] = useState(false);
  const [words, setWords] = useState(false);
  const [found, setFound] = useState<Found & { sought: string }>({ ...NONE, sought: '' });
  const [current, setCurrent] = useState(0);
  const [changes, setChanges] = useState(0);
  const sought = `${text}\n${cased}\n${words}`;
  const total = found.hits.length;
  const at = Math.min(current, total - 1);
  const hit = at >= 0 ? found.hits[at] : undefined;

  useEffect(() => setReplace(replacing && write !== null), [replacing, write]);

  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, [replacing]);

  useEffect(() => {
    const changed = () => setChanges((count) => count + 1);
    doc.on('update', changed);
    const unsubscribe = grids.subscribe(null, changed);
    return () => {
      doc.off('update', changed);
      unsubscribe();
    };
  }, [doc, grids]);

  useEffect(() => {
    if (!text || !tab) {
      shownFor.current = '';
      setFound({ ...NONE, sought });
      return;
    }
    let live = true;
    const timer = setTimeout(() => {
      const query = new URLSearchParams({ text });
      if (cased) query.set('case', '1');
      if (words) query.set('words', '1');
      getJson<Found>(`/api/tabs/${tab}/found?${query}`).then((next) => {
        if (!live) return;
        if (shownFor.current !== sought) {
          shownFor.current = sought;
          const first = firstFrom(view.state.doc, next.hits, view.state.selection.from);
          setCurrent(first);
          if (next.hits[first]) goToHit(view, next.hits[first]);
        }
        setFound({ ...next, sought });
      }, fail.current);
    }, WAIT_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [text, cased, words, changes, tab, sought, view]);

  useEffect(() => {
    if (!view.isDestroyed) markHits(view, found.hits, at);
  }, [view, found, at]);

  useEffect(
    () => () => {
      if (!view.isDestroyed) markHits(view, [], -1);
    },
    [view],
  );

  function go(step: number) {
    if (!total) return;
    const next = (at + step + total) % total;
    setCurrent(next);
    goToHit(view, found.hits[next]);
  }

  function substitute(place: object) {
    if (!write || !text) return;
    write([{ op: 'substitute', find: text, by, case: cased, words, ...place }]);
    // The button pressed is disabled once no hit is left, which would drop the focus out of the bar.
    if (document.activeElement instanceof HTMLButtonElement) input.current?.focus();
  }

  function close() {
    onClose();
    view.focus();
  }

  function escaped(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  }

  const count = !text
    ? ''
    : total
      ? `${formatNumber(at + 1)} / ${formatNumber(total)}${found.more ? '+' : ''}`
      : found.sought === sought
        ? t('find.none')
        : '';

  return (
    <div
      role="search"
      onKeyDown={escaped}
      className="mt-2 flex flex-wrap items-center gap-1 rounded-2xl bg-panel px-3 py-1"
    >
      {write && (
        <button
          type="button"
          aria-label={t('find.showReplace')}
          aria-expanded={replace}
          onClick={() => setReplace(!replace)}
          className={iconButton}
        >
          {replace ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </button>
      )}
      <Search size={16} aria-hidden className="text-muted" />
      <input
        ref={input}
        type="search"
        aria-label={t('find.label')}
        placeholder={t('find.label')}
        autoComplete="off"
        spellCheck={false}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            go(event.shiftKey ? -1 : 1);
          }
        }}
        className={`${smallField} w-48`}
      />
      <span aria-live="polite" className="min-w-16 text-center text-sm text-muted">
        {count}
      </span>
      <button
        type="button"
        aria-label={t('find.previous')}
        disabled={!total}
        onClick={() => go(-1)}
        className={`${iconButton} disabled:opacity-40`}
      >
        <ChevronUp size={16} />
      </button>
      <button
        type="button"
        aria-label={t('find.next')}
        disabled={!total}
        onClick={() => go(1)}
        className={`${iconButton} disabled:opacity-40`}
      >
        <ChevronDown size={16} />
      </button>
      <button
        type="button"
        aria-label={t('find.case')}
        title={t('find.case')}
        aria-pressed={cased}
        onClick={() => setCased(!cased)}
        className={`${iconButton} aria-pressed:bg-selected aria-pressed:text-accent`}
      >
        <CaseSensitive size={16} />
      </button>
      <button
        type="button"
        aria-label={t('find.words')}
        title={t('find.words')}
        aria-pressed={words}
        onClick={() => setWords(!words)}
        className={`${iconButton} aria-pressed:bg-selected aria-pressed:text-accent`}
      >
        <WholeWord size={16} />
      </button>
      {replace && (
        <>
          <span aria-hidden className="mx-1 h-5 w-px bg-line" />
          <input
            aria-label={t('find.by')}
            placeholder={t('find.by')}
            autoComplete="off"
            spellCheck={false}
            value={by}
            onChange={(event) => setBy(event.target.value.replace(/\n/g, ''))}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && hit && !hit.formula) {
                event.preventDefault();
                substitute(hitPlace(hit));
              }
            }}
            className={`${smallField} w-48`}
          />
          <button
            type="button"
            disabled={!hit || hit.formula}
            onClick={() => hit && substitute(hitPlace(hit))}
            className={button}
          >
            {t('find.replace')}
          </button>
          <button
            type="button"
            disabled={!total}
            onClick={() => substitute({})}
            className={primaryButton}
          >
            {t('find.replaceAll')}
          </button>
        </>
      )}
      <button
        type="button"
        aria-label={t('find.close')}
        onClick={close}
        className={`${iconButton} ml-auto`}
      >
        <X size={16} />
      </button>
    </div>
  );
}
