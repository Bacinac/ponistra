import { useQueryClient, type QueryKey } from '@tanstack/react-query';
import { useCallback, useEffect, useRef } from 'react';
import { useChanges } from './live';

/** For each area the server says changed, whether a query reads from it. */
const AREAS: Record<string, (key: QueryKey) => boolean> = {
  contacts: ([root, part]) =>
    root === 'contacts' || root === 'people' || (root === 'mail' && part === 'people'),
  calendar: ([root]) => root === 'calendar' || root === 'calendar-event',
  tasks: ([root]) => root === 'tasks',
  conversations: ([root]) => root === 'conversations' || root === 'channels' || root === 'peek',
  nodes: ([root]) => root === 'tree' || root === 'access' || root === 'company',
  vault: ([root]) => root === 'vault',
  // A message and a draft are read once and kept: their lists say what changed of them.
  mail: ([root, part]) => root === 'mail' && part !== 'message' && part !== 'draft',
  away: ([root, part]) =>
    root === 'away' ||
    (root === 'mail' && part === 'away') ||
    (root === 'calendar' && part === 'free'),
  account: ([root]) => root === 'app-passwords' || root === 'passkeys',
  users: ([root]) =>
    root === 'accounts' || root === 'policy' || root === 'people' || root === 'session',
  applications: ([root]) => root === 'identity',
  journal: ([root]) => root === 'journal',
  // A rule or a hold changes what may be deleted wherever content is listed.
  retention: ([root, part]) =>
    root === 'retention' ||
    (root === 'tree' && part === 'trash') ||
    root === 'conversations' ||
    (root === 'mail' && part !== 'message' && part !== 'draft'),
  health: ([root]) => root === 'health',
  workspace: ([root]) => root === 'workspace',
  memory: ([root]) => root === 'memory',
  drive: ([root]) => root === 'drive',
  meetings: ([root]) => root === 'meeting-recordings' || root === 'meeting-relay',
  // A board's page reads what it keeps by itself, once `BoardView` tells it this area changed.
  boards: () => false,
};
/** One thing opened by its id, only marked to be read when it is next opened: deleted while open,
    as its own tab deletes it, it would be asked for once more and answer not found. */
function opened([root, part]: QueryKey): boolean {
  return root === 'calendar-event' || (root === 'contacts' && typeof part === 'number');
}

// The least time between two readings, so a sync that changes a row at a time is read once a second.
const QUIET = 1000;

function readsOf(area: string): ((key: QueryKey) => boolean)[] {
  if (area === '*') return Object.values(AREAS);
  const reads = AREAS[area];
  if (!reads) throw new Error(`No queries follow the area ${area}`);
  return [reads];
}

/** Reads again the queries on screen whose data changed on the server; the others are read when
    they are next shown. */
export function useFollowed(): void {
  const queryClient = useQueryClient();
  const waiting = useRef(new Set<string>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flush = useCallback(() => {
    const reads = [...waiting.current].flatMap(readsOf);
    waiting.current.clear();
    if (!reads.length) {
      timer.current = null;
      return;
    }
    const followed = (key: QueryKey) => reads.some((each) => each(key));
    void queryClient.invalidateQueries({
      predicate: ({ queryKey }) => followed(queryKey) && !opened(queryKey),
    });
    void queryClient.invalidateQueries({
      predicate: ({ queryKey }) => followed(queryKey) && opened(queryKey),
      refetchType: 'none',
    });
    timer.current = setTimeout(flush, QUIET);
  }, [queryClient]);
  const told = useCallback(
    (areas: string[]) => {
      for (const area of areas) waiting.current.add(area);
      if (!timer.current) flush();
    },
    [flush],
  );
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  useChanges(told);
}
