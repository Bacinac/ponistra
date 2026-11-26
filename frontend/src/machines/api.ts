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
  /** Through Ponistra (C4.8): what only the machine's own page may do, enrolling it in a Ponistra
   * or leaving one, is left out. */
  throughPonistra?: boolean;
  get<T>(path: string): Promise<T>;
  send<T>(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown): Promise<T>;
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

export type ImageAction = 'check' | 'update' | 'rollback' | 'role' | 'channel';

export type Role = 'server' | 'workstation';

export interface ImageJob {
  action: ImageAction;
  started_at: string;
  finished_at: string | null;
  target?: string;
  error?: string;
}

export const CHANNELS = ['stable', 'test'] as const;
export type Channel = (typeof CHANNELS)[number];

export interface ImageStatus {
  follows: string;
  /** Empty for an image followed by its version or digest. */
  channel: Channel | '';
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
  inputs: RecipeInput[] | null;
  /** What the guest's firewall lets in from its first start: `tcp/443 udp/51820`, or `any`. */
  open?: string;
  network?: string;
}

/** `iso` takes an ISO's name, `path` a directory of the host mounted into the guest, `port` a
 * wired port set aside for guests, `text` and `secret` one line matching `pattern`. An input with
 * a `default`, even an empty one, may be left out. */
export interface RecipeInput {
  name: string;
  title: string;
  type: 'iso' | 'path' | 'port' | 'text' | 'secret';
  pattern?: string;
  default?: string;
}

/** Only a recipe of this group takes an `owner`, the account its console and files open for. */
export const OWNED: RecipeGroup = 'workspaces';

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
  result?: string;
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
  via: 'page' | 'socket' | 'schedule' | 'system' | 'ponistra';
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

export interface NetworkAddress {
  mode: 'dhcp' | 'static' | 'none';
  address?: string;
  gateway?: string;
  dns?: string[];
}

export interface NetworkConfig {
  /** The MAC address of the wired port the machine uses; empty for every wired port. */
  uplink: string;
  bridge: boolean;
  address: NetworkAddress;
  vlans: { id: number; bridge: boolean; address: NetworkAddress }[] | null;
  guest_ports: string[] | null;
}

export interface NetworkLink {
  name: string;
  kind: 'port' | 'bridge' | 'vlan';
  mac: string;
  carrier: boolean;
  addresses: string[] | null;
}

export interface NetworkState {
  config: NetworkConfig;
  links: NetworkLink[] | null;
  /** A change on trial, undone at `deadline` unless confirmed; `reach` is the machine's address
   * after it, when the change moves it. */
  pending?: { deadline: string; previous: NetworkConfig; reach?: string };
}

export const RULE_ACTIONS = ['allow', 'drop', 'reject'] as const;
export type RuleAction = (typeof RULE_ACTIONS)[number];
export const PROTOCOLS = ['', 'tcp', 'udp', 'icmp4', 'icmp6'] as const;
export type Protocol = (typeof PROTOCOLS)[number];

export interface Rule {
  action: RuleAction;
  protocol?: Protocol;
  source?: string;
  destination?: string;
  port?: string;
  description?: string;
}

export interface Firewall {
  ingress_default: RuleAction;
  egress_default: RuleAction;
  ingress: Rule[] | null;
  egress: Rule[] | null;
  /** A macvlan or physical NIC carries no firewall; `reason` says why. */
  nics: { name: string; network: string; attached: boolean; reason?: string }[] | null;
}

export type LinkState = 'not-enrolled' | 'connecting' | 'connected' | 'offline' | 'revoked';

export interface PonistraLink {
  state: LinkState;
  url?: string;
  id?: string;
  enrolled_at?: string;
  since?: string;
  error?: string;
  /** `machine` while the disk's recovery key is still on the machine, `ponistra` once Ponistra
   * holds it. */
  recovery_key?: 'machine' | 'ponistra' | '';
  backup_password?: 'machine' | 'ponistra' | '';
}

export type ConsoleType = 'vga' | 'console';

export interface ConsoleTicket {
  id: string;
  guest: string;
  type: ConsoleType;
  path: string;
  expires_at: string;
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

export const useNetwork = (enabled = true) =>
  useMachineQuery<NetworkState>('/v1/network', {
    enabled,
    refetchInterval: (query) => (query.state.data?.pending ? WATCH : false),
  });

export const useFirewall = (name: string) =>
  useMachineQuery<Firewall>(`${guestPath(name)}/firewall`);

export const usePonistra = () =>
  useMachineQuery<PonistraLink>('/v1/ponistra', {
    refetchInterval: (query) => (query.state.data?.state === 'connecting' ? WATCH : MINUTE),
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

/** A WebSocket's address for a path of the machine's API, on the page's own origin. */
export function socketUrl(api: MachineApi, path: string): string {
  const url = new URL(`${api.base}${path}`, window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.href;
}

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
