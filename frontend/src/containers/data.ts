import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, answered, csrfToken, deleteJson, getJson, postJson } from '../api';
import type { MessageKey } from '../i18n/hr';
import { errorMessage } from '../tree';

/** A Docker host as the administrator sees it: the location it is, and the line its account's
 * `authorized_keys` takes for Ponistra's key. */
export interface DockerHost {
  location: string;
  name: string;
  address: string;
  public_key: string;
  authorized: string;
}

export interface Reached extends DockerHost {
  version: string;
  api: string;
  os: string;
  arch: string;
  cpus: number | null;
  memory: number | null;
  containers: { running: number; stopped: number; paused: number };
  images: number;
}

export interface Container {
  id: string;
  name: string;
  image: string;
  state: string;
  status: string;
  created?: string | null;
  project?: string;
  service: string;
  folder?: string;
  health?: string;
  ports: string[];
}

export interface Image {
  id: string;
  tags: string[];
  size: number | null;
  created: string | null;
  used: boolean;
}

export interface Volume {
  id: string;
  name: string;
  driver: string;
  created: string | null;
  project: string;
  used: boolean;
}

export interface Network {
  id: string;
  name: string;
  driver: string;
  scope: string;
  created: string | null;
  project: string;
  used: boolean;
  built_in: boolean;
}

export interface Stack {
  file: string | null;
  containers: Container[];
  said: string[];
}

export const KINDS = ['containers', 'images', 'volumes', 'networks'] as const;
export type Kind = (typeof KINDS)[number];
export type Held = { containers: Container[] } & { images: Image[] } & { volumes: Volume[] } & {
  networks: Network[];
};
export const VERBS = ['up', 'pull', 'restart', 'stop', 'down'] as const;
export type Verb = (typeof VERBS)[number];
export const PRUNED = ['containers', 'images', 'volumes', 'networks', 'builder'] as const;
export type Pruned = (typeof PRUNED)[number];

/** Every query of this module begins so, which the live area `containers` reads again. */
export const CONTAINERS = 'containers';
export const HOSTS = [CONTAINERS, 'hosts'];
const base = (location: string) => `/api/containers/hosts/${location}`;

export function useDockerHosts(enabled = true) {
  return useQuery({
    queryKey: HOSTS,
    queryFn: () =>
      getJson<{ hosts: DockerHost[]; candidates: { id: string; name: string }[] }>(
        '/api/containers/hosts',
      ),
    enabled,
    retry: false,
  });
}

export function useReached(location: string) {
  return useQuery({
    queryKey: [CONTAINERS, 'host', location],
    queryFn: () => getJson<Reached>(base(location)),
    retry: false,
  });
}

export function useHeld<K extends Kind>(location: string, kind: K) {
  return useQuery({
    queryKey: [CONTAINERS, 'held', location, kind],
    queryFn: () => getJson<Pick<Held, K>>(`${base(location)}/${kind}`),
    retry: false,
  });
}

export function useStack(location: string, path: string, enabled: boolean) {
  return useQuery({
    queryKey: [CONTAINERS, 'stack', location, path],
    queryFn: () =>
      getJson<Stack>(`${base(location)}/stack?${new URLSearchParams({ path }).toString()}`),
    enabled,
    retry: false,
  });
}

/** A change on a host; what it changed comes back through the live area as the daemon tells. */
export function useDockerChange<V, R>(mutationFn: (variables: V) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [CONTAINERS] }),
  });
}

export const act = (location: string, container: string, action: string) =>
  postJson(`${base(location)}/containers/${encodeURIComponent(container)}/${action}`);

export const removeHeld = (location: string, kind: Kind, ref: string) =>
  deleteJson(`${base(location)}/${kind}/${encodeURIComponent(ref)}`);

export const prune = (location: string, kind: Pruned) =>
  postJson<{ removed: number; reclaimed: number }>(`${base(location)}/prune`, { kind });

export const logsPath = (location: string, container: string, tail: number) =>
  `${base(location)}/containers/${encodeURIComponent(container)}/logs?tail=${tail}`;

export const stackPath = (location: string, path: string) =>
  `${base(location)}/stack?${new URLSearchParams({ path }).toString()}`;

/** Reads what the response sends as it comes, each piece of text to `heard`, until it ends or
 * `signal` aborts it. A change asks the confirmation first, as the streamed request cannot. */
export async function streamed(
  path: string,
  heard: (text: string) => void,
  signal: AbortSignal,
  body?: unknown,
): Promise<void> {
  if (body !== undefined) await postJson('/api/containers/confirm');
  const response = await answered(path, {
    method: body === undefined ? 'GET' : 'POST',
    signal,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const refused = await response.json().catch(() => ({}));
    throw new ApiError(path, response.status, refused.error, refused.detail);
  }
  const reader = response.body!.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    heard(value);
  }
}

/** The error as the page says it, and below it what Docker or compose said in its own words. */
export function dockerError(error: Error, t: (key: MessageKey) => string): string {
  const said = errorMessage(error, t);
  return error instanceof ApiError && error.detail ? `${said}\n${error.detail}` : said;
}
