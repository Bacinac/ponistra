import { useQuery } from '@tanstack/react-query';
import type { Awareness } from 'y-protocols/awareness';
import { getJson, postJson } from '../api';
import type { TreeNode } from '../tree';

/** Where an action applies, by the ids of its table and the parts of it, of proposals or of the
 * blocks of the text. */
export type Addressed = Record<string, string | string[] | { row: string; col: string }>;

/** The part of a tab an action applies to. */
export type TabTarget = 'document' | 'table' | 'column' | 'range' | 'proposals' | 'text';

/** An action the backend defines (D14): the kind of target it applies to, a part of a tab or
 * documents and PDF files, the JSON Schema of its parameters, how its result is reviewed, the
 * model that carries it out, if one does. */
export interface Action {
  id: string;
  target: TabTarget | 'nodes' | 'messages';
  parameters: object;
  review: 'apply' | 'propose';
  model: string | null;
}

/** A document or PDF file a run over several missed, and why. */
export interface Missed {
  title: string;
  error: string;
}

export interface Run {
  id: string;
  action: string;
  /** The model that carried the run out, where one did. */
  model: string | null;
  target: Addressed;
  state: 'running' | 'stopping' | 'stopped' | 'interrupted' | 'done' | 'failed' | 'undone';
  error: string;
  started_at: string;
  finished_at: string | null;
  /** What the run's model said at the end, where it answered instead of acting or besides. */
  reply: string;
  /** The answers the run's model offered the user to choose from, where it asked how a request
   * is meant. */
  offers: string[];
  /** The outside agent that started it, where one did (D18). */
  via: string | null;
  /** Whether the run changed anything, which Undo would take back. */
  changed: boolean;
  /** Of a run over several documents, how many it has gone through and those it missed. */
  items: { of: number; through: number; missed: Missed[] } | null;
}

/** How the user lets a model's action send its target out: this once, or from now on in the
 * document. */
export type Consent = 'once' | 'always';

/** A run under way in the room, as the server's presence there shows it. */
export interface Running {
  run: string;
  action: string;
  user: { id: number; name: string } | null;
  /** The outside agent that started it, where one did (D18). */
  via?: string | null;
  model?: string | null;
  /** Of a run over several documents, how many it has gone through of how many. */
  through?: number;
  of?: number;
}

export const UNDER_WAY: ReadonlySet<Run['state']> = new Set(['running', 'stopping']);
const CHECK_EVERY = 5000;

export async function startRun(
  tab: string,
  action: string,
  target: Addressed,
  parameters: object = {},
  consent?: 'once',
): Promise<Run> {
  const path = `/api/tabs/${tab}/runs`;
  return (await postJson<{ run: Run }>(path, { action, target, parameters, consent })).run;
}

/** Starts the action over the documents and PDF files, and those in the folders among them,
 * which writes what it finds into the document it makes beside them. */
export async function startOnNodes(
  action: string,
  nodes: readonly string[],
  parameters: object,
): Promise<{ run: Run; document: TreeNode }> {
  return postJson('/api/runs', { action, target: { nodes }, parameters, consent: 'once' });
}

export async function stopRun(run: string): Promise<Run> {
  return (await postJson<{ run: Run }>(`/api/runs/${run}/stop`, {})).run;
}

export async function undoRun(run: string): Promise<Run> {
  return (await postJson<{ run: Run }>(`/api/runs/${run}/undo`, {})).run;
}

/** The run once it is over: a model's run works on in the background and leaves the room's
 * presence when it ends, which the server is asked about then, and now and then besides. */
export function ended(run: Run, awareness: Awareness): Promise<Run> {
  if (!UNDER_WAY.has(run.state)) return Promise.resolve(run);
  return new Promise((resolve, reject) => {
    const check = () => {
      if (runningIn(awareness).some((each) => each.run === run.id)) return;
      getJson<{ run: Run }>(`/api/runs/${run.id}`).then(({ run: found }) => {
        if (UNDER_WAY.has(found.state)) return;
        stop();
        resolve(found);
      }, fail);
    };
    const fail = (error: unknown) => {
      stop();
      reject(error);
    };
    const timer = setInterval(check, CHECK_EVERY);
    const stop = () => {
      awareness.off('change', check);
      clearInterval(timer);
    };
    awareness.on('change', check);
    check();
  });
}

export function runningIn(awareness: Awareness): Running[] {
  const found: Running[] = [];
  for (const state of awareness.getStates().values()) {
    const runs = state.runs as Record<string, Omit<Running, 'run'>> | undefined;
    for (const [run, each] of Object.entries(runs ?? {})) found.push({ run, ...each });
  }
  return found;
}

export function useAi() {
  return useQuery({
    queryKey: ['actions', 'ai'],
    queryFn: async () => (await getJson<{ ai: boolean }>('/api/actions')).ai,
    staleTime: Infinity,
  });
}
