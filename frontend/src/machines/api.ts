import {
  QueryClient,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';
import { createContext, useContext } from 'react';

/** A machine's API (ponistra-os `agent/API.md`), reached at `base`: `/api` on the machine's own
 * page, a path through Ponistra in the Computers module. */
export interface MachineApi {
  base: string;
  get<T>(path: string): Promise<T>;
  send<T>(method: 'POST' | 'DELETE', path: string, body?: unknown): Promise<T>;
  /** A file sent as it is, telling `progress` the share sent so far. */
  upload<T>(path: string, file: Blob, progress: (share: number) => void): Promise<T>;
}

export class MachineError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** `unauthorized` hears every 401, so the page can ask for the sign-in again. */
export function machineApi(base: string, unauthorized: () => void = () => {}): MachineApi {
  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetch(`${base}${path}`, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 401) unauthorized();
    if (!response.ok) {
      const answer = await response.json().catch(() => null);
      const message =
        answer && typeof answer.error === 'string' ? answer.error : response.statusText;
      throw new MachineError(response.status, message || String(response.status));
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }
  return {
    base,
    get: (path) => call('GET', path),
    send: (method, path, body) => call(method, path, body),
    upload: (path, file, progress) =>
      new Promise((resolve, reject) => {
        // fetch reports no upload progress; an ISO takes minutes.
        const request = new XMLHttpRequest();
        request.open('POST', `${base}${path}`);
        request.setRequestHeader('Content-Type', 'application/octet-stream');
        request.upload.onprogress = (event) => {
          if (event.lengthComputable) progress(event.loaded / event.total);
        };
        request.onerror = () => reject(new MachineError(0, request.statusText || 'network error'));
        request.onload = () => {
          if (request.status === 401) unauthorized();
          let answer: { error?: unknown } | null = null;
          try {
            answer = JSON.parse(request.responseText);
          } catch {
            answer = null;
          }
          if (request.status >= 200 && request.status < 300) resolve(answer as never);
          else {
            const message = typeof answer?.error === 'string' ? answer.error : request.statusText;
            reject(new MachineError(request.status, message || String(request.status)));
          }
        };
        request.send(file);
      }),
  };
}

export function newMachineQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (count, error) =>
          count < 2 && !(error instanceof MachineError && error.status < 500),
      },
    },
  });
}

export const MachineContext = createContext<MachineApi | null>(null);

export function useMachineApi(): MachineApi {
  const api = useContext(MachineContext);
  if (!api) throw new Error('useMachineApi called outside MachineContext');
  return api;
}

export interface Machine {
  hostname: string;
  machine_id: string;
  boot_id: string;
  booted_at: string;
  os: { name: string; image: string; version: string; variant: 'base' | 'desktop'; kernel: string };
  hardware: {
    vendor: string;
    product: string;
    version: string;
    serial: string;
    chassis: string;
    cpu: string;
    cpus: number;
    memory: number;
  };
  security: { secure_boot: boolean | null; tpm: string };
}

export type HealthState = 'checking' | 'green' | 'red' | 'waiting';

export interface Health {
  state: HealthState;
  failed_units: string[];
  faults: { name: string; text: string }[];
}

export interface Stall {
  avg10: number;
  avg60: number;
  avg300: number;
  total: number;
}

export interface Resources {
  load: [number, number, number];
  pressure: Partial<Record<Resource, { some: Stall; full: Stall }>>;
  memory: { total: number; available: number; swap_total: number; swap_free: number };
  filesystems: { path: string; size: number; free: number; avail: number }[];
  interfaces: {
    name: string;
    kind: string;
    mac: string;
    state: string;
    speed?: number;
    addresses: string[];
  }[];
}

export interface Deployment {
  image: string;
  version: string;
  digest: string;
  timestamp: string;
  pinned: boolean;
}

export type ImageAction = 'check' | 'update' | 'rollback' | 'role';

export type Role = 'server' | 'workstation';

export interface ImageJob {
  action: ImageAction;
  started_at: string;
  finished_at: string | null;
  target?: string;
  error?: string;
}

export interface ImageStatus {
  follows: string;
  role: Role;
  staged_role?: Role;
  booted: Deployment | null;
  staged: Deployment | null;
  rollback: Deployment | null;
  rollback_queued: boolean;
  available: Deployment | null;
  job: ImageJob | null;
}

export const GROUPS = ['workspaces', 'services', 'build'] as const;
export type RecipeGroup = (typeof GROUPS)[number];

export interface Recipe {
  id: string;
  title: string;
  description: string;
  group: RecipeGroup;
  kind: 'lxc' | 'vm';
  class: GuestClass;
  memory: string;
  cpus: number;
  disk: string;
  /** `iso` takes an ISO's name, `path` a directory of the host mounted into the guest. */
  inputs: { name: string; title: string; type: 'iso' | 'path' }[] | null;
}

export interface Network {
  name: string;
  type: string;
  managed: boolean;
}

export interface Iso {
  name: string;
  size: number;
  created_at: string;
}

/** An ISO's name: letters, digits, dots, underscores and dashes, at most 63. */
export const ISO_NAME = /^[A-Za-z0-9._-]{1,63}$/;

export const CLASSES = ['production', 'work', 'build'] as const;
export type GuestClass = (typeof CLASSES)[number];

export interface Guest {
  name: string;
  kind: 'lxc' | 'vm';
  recipe: string;
  status: string;
  description: string;
  profiles: string[];
  autostart: boolean;
  created_at: string;
  last_used_at: string;
  memory_limit: string;
  cpu_limit: string;
  memory: number;
  memory_peak: number;
  cpu_time: number;
  disk: Record<string, number> | null;
  addresses: { interface: string; address: string }[] | null;
  processes: number;
  snapshots: number;
  snapshot_policy: string;
  restored_from?: string;
  previous?: string;
  replaced_at?: string;
  error?: string;
}

export interface Snapshot {
  name: string;
  created_at: string;
  expires_at: string | null;
  stateful: boolean;
  size: number;
}

export interface Values {
  cpu_wait: number;
  memory_wait: number;
  memory_stall: number;
  io_wait: number;
  io_stall: number;
  cpu: number;
  memory: number;
  read: number;
  write: number;
  receive: number;
  send: number;
}

export type Resource = 'cpu' | 'memory' | 'io';

export interface PressureNow {
  at: string;
  machine: Values;
  guests: {
    name: string;
    kind: string;
    memory_limit: string;
    cpu_limit: string;
    values: Values;
    share: { cpu: number; memory: number; disk: number; network: number };
  }[];
  causes: {
    resource: Resource;
    level: 'busy' | 'congested';
    wait: number;
    guests: string[] | null;
    text: string;
  }[];
}

export const SPANS = ['90m', '24h', '7d', '30d'] as const;
export type Span = (typeof SPANS)[number];

export interface History {
  guest?: string;
  step: number;
  points: { at: string; values: Values }[];
}

export interface HardwareState {
  temperatures: { sensor: string; label: string; celsius: number; critical?: number }[];
  disks: {
    name: string;
    model: string;
    serial: string;
    transport: string;
    size: number;
    rotational: boolean;
    smart: {
      passed: boolean | null;
      temperature?: number;
      power_on_hours?: number;
      percent_used?: number;
      media_errors?: number;
      reallocated_sectors?: number;
      pending_sectors?: number;
      error?: string;
    };
  }[];
  pools?: {
    name: string;
    state: string;
    read_errors: number;
    write_errors: number;
    checksum_errors: number;
    scrub: {
      state: 'scanning' | 'finished' | 'canceled';
      started_at: string | null;
      ended_at: string | null;
      examined: number;
      to_examine: number;
      errors: number;
    } | null;
  }[];
  batteries: { name: string; status: string; capacity: number; health?: number; cycles?: number }[];
  errors: string[];
}

export interface Alert {
  id: string;
  kind: string;
  subject: string;
  severity: 'warning' | 'critical';
  text: string;
  raised_at: string;
  cleared_at?: string;
}

export interface Pool {
  name: string;
  health: string;
  size: number;
  allocated: number;
  free: number;
  capacity: number;
  fragmentation: number;
}

export interface Task {
  id: string;
  action: string;
  target: string;
  by: string;
  via: 'page' | 'socket' | 'schedule' | 'system';
  started_at: string;
  finished_at: string | null;
  status: 'running' | 'ok' | 'error';
  error?: string;
}

export interface SnapshotFile {
  name: string;
  type: 'file' | 'dir' | 'link' | 'other';
  size: number;
  mode: string;
  uid: number;
  gid: number;
  modified_at: string;
  target?: string;
}

export type GuestAction = 'start' | 'stop' | 'restart';

/** A guest's name is a hostname label: letters, digits and dashes, at most 63, not a number. */
export const GUEST_NAME = /^(?!\d+$)[A-Za-z0-9-]{1,63}$/;

/** A guest the agent is still making: from a recipe, its setup, or an import. */
export const UNDERWAY = ['Creating', 'Setting up', 'Importing'];

export const underway = (guest: Guest) => UNDERWAY.includes(guest.status);

export function guestClass(guest: Guest): GuestClass | undefined {
  return CLASSES.find((each) => guest.profiles?.includes(each));
}

const key = (api: MachineApi, path: string) => ['machine', api.base, path];

function useMachineQuery<T>(
  path: string,
  options: Omit<UseQueryOptions<T, Error, T>, 'queryKey' | 'queryFn'> = {},
) {
  const api = useMachineApi();
  return useQuery<T, Error, T>({
    queryKey: key(api, path),
    queryFn: () => api.get<T>(path),
    ...options,
  });
}

// Polling watches what runs on the machine (a health check, an image job, a guest being made, a
// task) and the agent's minute samples, which change by the minute and announce nothing.
const WATCH = 2000;
const MINUTE = 60_000;

export const useMachine = () => useMachineQuery<Machine>('/v1/machine');

export const useHealth = () =>
  useMachineQuery<Health>('/v1/machine/health', {
    refetchInterval: (query) => (query.state.data?.state === 'checking' ? WATCH : MINUTE),
  });

export const useResources = () =>
  useMachineQuery<Resources>('/v1/resources', { refetchInterval: MINUTE });

export const useImage = () =>
  useMachineQuery<ImageStatus>('/v1/image', {
    refetchInterval: (query) => {
      const job = query.state.data?.job;
      return job && !job.finished_at ? WATCH : false;
    },
  });

export const useRecipes = () => useMachineQuery<Recipe[]>('/v1/recipes');

export const useNetworks = () => useMachineQuery<Network[]>('/v1/guest-networks');

export const useIsos = () => useMachineQuery<Iso[]>('/v1/isos');

export const useImportKey = () =>
  useMachineQuery<{ public_key: string }>('/v1/imports/proxmox/key');

export const useGuests = () =>
  useMachineQuery<Guest[]>('/v1/guests', {
    refetchInterval: (query) => (query.state.data?.some(underway) ? WATCH : false),
  });

export const useGuest = (name: string) =>
  useMachineQuery<Guest>(`/v1/guests/${encodeURIComponent(name)}`, {
    refetchInterval: (query) => (query.state.data && underway(query.state.data) ? WATCH : false),
  });

export const useSnapshots = (name: string) =>
  useMachineQuery<Snapshot[]>(`/v1/guests/${encodeURIComponent(name)}/snapshots`);

export const useAgent = () => useMachineQuery<{ status: string; version: string }>('/v1/health');

/** 503 until the agent has two samples: the page says it is still gathering. */
export const usePressure = () =>
  useMachineQuery<PressureNow>('/v1/pressure', { refetchInterval: MINUTE });

export const useHistory = (span: Span, guest?: string) =>
  useMachineQuery<History>(
    `/v1/pressure/history?${new URLSearchParams({ span, ...(guest ? { guest } : {}) })}`,
    { refetchInterval: MINUTE },
  );

export const useHardware = () => useMachineQuery<HardwareState>('/v1/hardware');

export const useAlerts = () => useMachineQuery<Alert[]>('/v1/alerts', { refetchInterval: MINUTE });

export const usePools = () => useMachineQuery<Pool[]>('/v1/pools');

export const useTasks = (target?: string) =>
  useMachineQuery<Task[]>(
    `/v1/tasks?${new URLSearchParams({ limit: '200', ...(target ? { target } : {}) })}`,
    {
      refetchInterval: (query) =>
        query.state.data?.some((task) => task.status === 'running') ? WATCH : false,
    },
  );

export const useSnapshotFiles = (guest: string, snapshot: string, path: string) =>
  useMachineQuery<SnapshotFile[]>(
    `${snapshotPath(guest, snapshot)}/files?${new URLSearchParams({ path })}`,
  );

/** A write to the machine, after which every query of this machine is read again. */
export function useMachineWrite<V, R = unknown>(
  write: (api: MachineApi, variables: V) => Promise<R>,
  onDone?: () => void,
) {
  const api = useMachineApi();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (variables: V) => write(api, variables),
    onSuccess: onDone,
    onSettled: () => client.invalidateQueries({ queryKey: ['machine', api.base] }),
  });
}

export const guestPath = (name: string) => `/v1/guests/${encodeURIComponent(name)}`;

export const snapshotPath = (guest: string, snapshot: string) =>
  `${guestPath(guest)}/snapshots/${encodeURIComponent(snapshot)}`;
