import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router';
import { compact, idIn } from './address';
import { ApiError } from './api';
import type { MeasuredSlide } from './editor/deck';
import { useSaved } from './saved';
import { Failure, nodeHref } from './tree';

const PrintedDocument = lazy(() => import('./editor/Printed'));
const LaidSlides = lazy(() => import('./editor/Laid'));

/** What the print page tells the page it is framed in: its pages are ready, or why they are not. */
export interface Printed {
  printed: string;
  error?: { path: string; status: number; code?: string } | { message: string };
}

function sent(error: Error): NonNullable<Printed['error']> {
  return error instanceof ApiError
    ? { path: error.path, status: error.status, code: error.code }
    : { message: error.message };
}

function received(error: NonNullable<Printed['error']>): Error {
  return 'status' in error
    ? new ApiError(error.path, error.status, error.code)
    : new Error(error.message);
}

export function printHref(nodeId: string): string {
  return `/print/${compact(nodeId)}`;
}

const READY = 'ready';

/** Tells a headless browser waiting on the print page that its pages will not come. */
export function unprinted(): void {
  document.body.dataset.printed = 'failed';
}

/** The document's pages for the browser to print, without the app's frame: the page it is framed
 * in hears when they are laid out, and so does a headless browser saving or counting them, from the
 * body's `data-printed`, with each tab's count of pages in its `data-pages`; one saving a long
 * document a run of pages at a time names the run in its `data-range`. */
export function PrintPage() {
  const nodeId = idIn(useParams().node) ?? '';
  const { placement, own, states, grids, error } = useSaved(nodeId, 'print');
  const tell = useCallback((message: Printed) => {
    if (window.parent !== window) window.parent.postMessage(message, location.origin);
  }, []);
  const title = placement?.node.title;

  useEffect(() => {
    if (title !== undefined) document.title = title;
  }, [title]);

  useEffect(() => {
    if (!error) return;
    unprinted();
    tell({ printed: nodeId, error: sent(error) });
  }, [error, nodeId, tell]);

  const ready = useCallback(
    (pages: Record<string, number>) => {
      if (document.body.dataset.printed === READY) return;
      document.body.dataset.pages = JSON.stringify(pages);
      document.body.dataset.printed = READY;
      tell({ printed: nodeId });
    },
    [nodeId, tell],
  );

  if (error) return <Failure error={error} />;
  if (!placement || !own || !states || !grids) return null;
  const { node, tabs } = placement;
  return (
    <Suspense fallback={null}>
      <PrintedDocument
        own={own}
        tabs={tabs}
        states={states}
        grids={grids}
        home={nodeHref(node)}
        title={node.title}
        locale={node.locale}
        onReady={ready}
      />
    </Suspense>
  );
}

/** The document's slides laid out for the printer to read where each box and block shows, for a
 * PowerPoint file: the body's `data-printed` tells when, and `data-slides` each tab's slides
 * measured, by the tab's id. */
export function SlidesPrintPage() {
  const nodeId = idIn(useParams().node) ?? '';
  const { placement, own, states, grids, error } = useSaved(nodeId, 'slides');

  useEffect(() => {
    if (error) unprinted();
  }, [error]);

  const ready = useCallback((slides: Record<string, MeasuredSlide[]>) => {
    if (document.body.dataset.printed === READY) return;
    document.body.dataset.slides = JSON.stringify(slides);
    document.body.dataset.printed = READY;
  }, []);

  if (error) return <Failure error={error} />;
  if (!placement || !own || !states || !grids) return null;
  return (
    <Suspense fallback={null}>
      <LaidSlides
        own={own}
        tabs={placement.tabs}
        states={states}
        grids={grids}
        locale={placement.node.locale}
        onReady={ready}
      />
    </Suspense>
  );
}

/** Prints the document through the browser's own dialog, from its print page in a frame laid over
 * the page, unseen, until its pages are ready. */
export function usePrint(nodeId: string): {
  print: () => void;
  pending: boolean;
  error: Error | null;
} {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const stop = useRef<(() => void) | null>(null);
  useEffect(() => () => stop.current?.(), []);
  const print = useCallback(() => {
    stop.current?.();
    const frame = document.createElement('iframe');
    frame.className = 'ponistra-printing';
    frame.tabIndex = -1;
    frame.setAttribute('aria-hidden', 'true');
    frame.src = printHref(nodeId);
    const heard = ({ source, data }: MessageEvent<Printed>) => {
      if (source !== frame.contentWindow || data?.printed !== nodeId) return;
      window.removeEventListener('message', heard);
      setPending(false);
      if (data.error) {
        setError(received(data.error));
        frame.remove();
        return;
      }
      frame.contentWindow!.addEventListener('afterprint', () => frame.remove(), { once: true });
      frame.contentWindow!.print();
    };
    stop.current = () => {
      window.removeEventListener('message', heard);
      frame.remove();
    };
    window.addEventListener('message', heard);
    setError(null);
    setPending(true);
    document.body.append(frame);
  }, [nodeId]);
  return { print, pending, error };
}
