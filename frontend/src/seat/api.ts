export type Cause =
  'ok' | 'not-configured' | 'no-link' | 'no-address' | 'no-dns' | 'portal' | 'unreachable';

export interface Interface {
  name: string;
  wireless: boolean;
  carrier: boolean;
  addresses: string[] | null;
}

export interface Status {
  cause: Cause;
  ponistra?: string;
  portal_url?: string;
  detail?: string;
  interfaces: Interface[] | null;
  checked_at: string;
}

export interface WifiNetwork {
  id: string;
  name: string;
  security: 'open' | 'psk' | '8021x' | 'wep';
  signal: number;
  connected: boolean;
  known: boolean;
}

export interface WifiDevice {
  name: string;
  powered: boolean;
  state: string;
  scanning: boolean;
  connected?: string;
  networks: WifiNetwork[] | null;
}

export interface BluetoothAdapter {
  id: string;
  address: string;
  powered: boolean;
  discovering: boolean;
}

export interface BluetoothDevice {
  id: string;
  address: string;
  name: string;
  icon?: string;
  paired: boolean;
  trusted: boolean;
  connected: boolean;
  rssi?: number;
}

export interface BluetoothState {
  adapters: BluetoothAdapter[] | null;
  devices: BluetoothDevice[] | null;
}

/** An answer of the seat's agent other than success: its status and the reason it wrote. */
export class SeatError extends Error {
  constructor(
    readonly status: number,
    readonly reason: string,
  ) {
    super(reason || `HTTP ${status}`);
  }
}

async function answered(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`/v1/seat/${path}`, { credentials: 'same-origin', ...init });
  if (response.ok) return response;
  const body = await response.json().catch(() => null);
  throw new SeatError(response.status, typeof body?.error === 'string' ? body.error : '');
}

export async function read<T>(path: string): Promise<T> {
  return (await answered(path, { cache: 'no-store' })).json();
}

export async function act(path: string, body: object): Promise<void> {
  await answered(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/** How often the screen reads the agent again: the network's status is at most 3 s old. */
export const EVERY = 3000;
