import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ApiError,
  deleteJson,
  getFreshJson,
  getJson,
  postJson,
  putJson,
  uploadThrough,
} from '../api';
import { isMessageKey } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { MachineError, type MachineApi } from '../machines/api';
import { errorMessage } from '../tree';

export type Severity = 'info' | 'warning' | 'critical';

export interface Alert {
  key: string;
  severity: Severity;
  text: string;
  raised_at: string;
  cleared_at?: string | null;
}

export interface Computer {
  id: string;
  name: string;
  connected: boolean;
  connected_at: string | null;
  seen_at: string | null;
  agent: string;
  facts: { image?: { variant?: string; version?: string } } & Record<string, unknown>;
  alerts: Alert[];
  enrolled_at: string;
  left_at: string | null;
  recovery_key_at: string | null;
  backup_password_at: string | null;
}

export interface Code {
  id: number;
  hint: string;
  made_at: string;
  expires_at: string;
}

export interface Listed {
  computers: Computer[];
  orphaned: Computer[];
  codes: Code[];
  can_add: boolean;
}

export interface Person {
  id: number;
  name: string;
  email: string;
}

export type Secret = 'recovery_key' | 'backup_password';

export interface Opening {
  secret: Secret;
  by: Person | null;
  at: string;
  address: string | null;
}

export interface Detail extends Computer {
  managers: Person[];
  openings: Opening[];
}

export interface Answers {
  language: 'hr' | 'en';
  keyboard: '' | 'us' | 'hr';
  role: '' | 'server' | 'workstation';
  hostname: string;
  network: string;
  wifi: string;
  wifi_password: string;
  ssh_key: string[];
  password: string;
  erase: boolean;
}

export interface Made extends Code {
  code: string;
  conf: string;
}

export interface Stick {
  url: string;
  size: number;
  sha256: string;
}

export interface Sticks {
  version: string;
  network: Stick;
  full: Stick;
}

const LIST = ['computers'] as const;

export function useComputers(enabled = true) {
  return useQuery({
    queryKey: LIST,
    queryFn: () => getJson<Listed>('/api/computers'),
    enabled,
  });
}

export function useComputer(id: string) {
  return useQuery({
    queryKey: ['computers', id],
    queryFn: () => getFreshJson<Detail>(`/api/computers/${id}`),
  });
}

export function useSticks(enabled: boolean) {
  return useQuery({
    queryKey: ['computers', 'sticks'],
    queryFn: () => getFreshJson<Sticks>('/api/computers/sticks'),
    enabled,
    staleTime: 10 * 60_000,
  });
}

function useChanged<A, R>(change: (given: A) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: change,
    onSuccess: () => client.invalidateQueries({ queryKey: LIST }),
  });
}

export const useInstall = () =>
  useChanged((answers: Answers) => postJson<Made>('/api/computers/install', answers));

export const useCodeDeleted = () =>
  useChanged((id: number) => deleteJson(`/api/computers/codes/${id}`));

export const useRemoved = () => useChanged((id: string) => deleteJson(`/api/computers/${id}`));

export const useTakenOver = () =>
  useChanged((id: string) => postJson<void>(`/api/computers/${id}/take`));

export const useManagerAdded = (id: string) =>
  useChanged((user: number) => postJson<void>(`/api/computers/${id}/managers`, { user }));

export const useManagerRemoved = (id: string) =>
  useChanged((user: number) => deleteJson(`/api/computers/${id}/managers/${user}`));

export const useSecretOpened = (id: string) =>
  useChanged((secret: Secret) =>
    postJson<{ value: string; at: string }>(
      `/api/computers/${id}/secrets/${secret.replace('_', '-')}`,
    ),
  );

/** The text of a refusal, in the module's own words where Ponistra's general ones would mislead,
 * as a name taken is a computer's here. */
export function refusalText(error: Error, t: (key: MessageKey) => string): string {
  if (error instanceof ApiError && error.code) {
    const key = `computers.error.${error.code}`;
    if (isMessageKey(key)) return t(key);
  }
  return errorMessage(error, t);
}

function machineError(error: unknown, t: (key: MessageKey) => string): never {
  if (error instanceof ApiError) {
    const key = `computers.error.${error.code}`;
    throw new MachineError(
      error.status,
      isMessageKey(key) ? t(key) : (error.code ?? error.message),
    );
  }
  throw error;
}

/** The machine's API through Ponistra (C4.8), as the person signed in. A read is never answered
 * from what the device kept: a machine offline says so rather than show what it last was. */
export function computerApi(id: string, t: (key: MessageKey) => string): MachineApi {
  const base = `/api/computers/${id}/agent`;
  const methods = { POST: postJson, PUT: putJson } as const;
  return {
    base,
    throughPonistra: true,
    get: <T>(path: string) =>
      getFreshJson<T>(`${base}${path}`).catch((error) => machineError(error, t)),
    send: <T>(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown) =>
      (method === 'DELETE'
        ? (deleteJson(`${base}${path}`) as Promise<T>)
        : methods[method]<T>(`${base}${path}`, body ?? {})
      ).catch((error) => machineError(error, t)),
    upload: async <T>(path: string, file: Blob, progress: (share: number) => void) => {
      try {
        const upload = await uploadThrough('/api/uploads', file, (sent) =>
          progress(file.size ? sent / file.size : 1),
        );
        return await postJson<T>(`/api/computers/${id}/upload${path}`, { upload });
      } catch (error) {
        return machineError(error, t);
      }
    },
  };
}
