import { useQueries, useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useMemo } from 'react';
import * as Y from 'yjs';
import { getBytes, getJson } from './api';
import { WholeGrids, type GridSource, type Wholes } from './editor/grids';
import { heldState } from './room';
import { useNode, type Placement } from './tree';

/** The state the server keeps, with what this browser wrote that may not have reached it yet. */
async function stateOf(path: string, room: string | null): Promise<Uint8Array> {
  const saved = await getBytes(path);
  const held = room && heldState(room);
  return held ? Y.mergeUpdates([saved, held]) : saved;
}

function combined<T>(results: UseQueryResult<T>[]) {
  return {
    data: results.every((each) => each.data) ? results.map((each) => each.data!) : null,
    error: results.find((each) => each.error)?.error ?? null,
  };
}

/** The document as saved, its own state and each tab's in reading order, with the grids of all
 * their tables whole, as read for `purpose`, which keeps its reading apart from another's. */
export function useSaved(
  nodeId: string,
  purpose: string,
): {
  placement: Placement | undefined;
  own: Uint8Array | undefined;
  states: Uint8Array[] | null;
  grids: GridSource | null;
  error: Error | null;
} {
  const placement = useNode(nodeId || null);
  const room = placement.data?.room;
  const own = useQuery({
    queryKey: [purpose, nodeId],
    queryFn: () => stateOf(`/api/nodes/${nodeId}/state`, room ?? null),
    enabled: Boolean(nodeId) && room !== undefined,
  });
  const parts = useQuery({
    queryKey: [purpose, nodeId, 'grids'],
    queryFn: () => getJson<Wholes>(`/api/nodes/${nodeId}/grids`),
    enabled: Boolean(nodeId),
  });
  const tabs = placement.data?.tabs ?? [];
  const states = useQueries({
    queries: tabs.map((tab) => ({
      queryKey: [purpose, nodeId, tab.id],
      queryFn: () => stateOf(`/api/tabs/${tab.id}/state`, tab.room),
    })),
    combine: combined,
  });
  const sheets = useQueries({
    queries: tabs.map((tab) => ({
      queryKey: [purpose, nodeId, tab.id, 'grids'],
      queryFn: () => getJson<Wholes>(`/api/tabs/${tab.id}/grids`),
    })),
    combine: combined,
  });
  const grids = useMemo(
    () => (parts.data && sheets.data ? new WholeGrids(parts.data, ...sheets.data) : null),
    [parts.data, sheets.data],
  );
  return {
    placement: placement.data,
    own: own.data,
    states: placement.data ? states.data : null,
    grids: placement.data ? grids : null,
    error: placement.error ?? own.error ?? parts.error ?? states.error ?? sheets.error,
  };
}
