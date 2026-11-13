import type { QueryClient } from '@tanstack/react-query';
import { postJson } from './api';
import { cameWith } from './release';

export interface CrashReport {
  path: string;
  message: string;
  stack: string;
  components: string;
  queries: string;
}

const TRAIL = 40;
const TRAILED = new Set(['success', 'error', 'setState']);
const KEY_SHOWN = 160;
const trail: string[] = [];

function shapeOf(data: unknown): string {
  if (Array.isArray(data)) return `[${data.length}]`;
  if (data !== null && typeof data === 'object') return `{${Object.keys(data).join(',')}}`;
  return typeof data;
}

/** Keeps what the latest answers did to the queries for a crash report: when which query took
    data of which shape. A page that crashed on data it did not expect tells nothing else of it. */
export function followQueries(client: QueryClient): () => void {
  return client.getQueryCache().subscribe((event) => {
    if (event.type !== 'updated' && event.type !== 'removed') return;
    const action = event.type === 'updated' ? event.action : null;
    if (action && !TRAILED.has(action.type)) return;
    const manual = action?.type === 'success' && action.manual;
    trail.push(
      [
        Math.round(performance.now()),
        action?.type ?? 'removed',
        manual ? 'manual' : '',
        event.query.queryHash.slice(0, KEY_SHOWN),
        shapeOf(event.query.state.data),
      ]
        .filter(Boolean)
        .join(' '),
    );
    if (trail.length > TRAIL) trail.shift();
  });
}

export function queriesTrail(): string {
  const came = cameWith() ?? 'unknown';
  return [`release ${came}, crashed at ${Math.round(performance.now())}`, ...trail].join('\n');
}

const TRIES = 5;
const RETRY = 5000;

/** Tells the server's log what broke the page. A page that breaks as the device wakes may have no
    network yet, so the report waits for it. */
export function reportCrash(report: CrashReport, tries = TRIES): void {
  postJson('/api/crashes', report).catch((error: unknown) => {
    if (!(error instanceof TypeError) || tries <= 1) throw error;
    const again = () => reportCrash(report, tries - 1);
    if (navigator.onLine) setTimeout(again, RETRY);
    else window.addEventListener('online', again, { once: true });
  });
}
