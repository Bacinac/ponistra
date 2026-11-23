import { useQuery } from '@tanstack/react-query';
import { HardDrive, Server } from 'lucide-react';
import { getJson } from './api';
import type { FileEntry } from './files';
import type { Role } from './tree';

export type Kind = 'smb' | 'sftp';
export type Auth = 'password' | 'key';

export interface Tunnel {
  id: number;
  name: string;
}

export interface Location {
  id: string;
  name: string;
  kind: Kind;
  address: string;
  role: Role;
  owner: { id: number; name: string };
  tunnel: Tunnel | null;
  /** What only its owner is told. */
  host?: string;
  port?: number;
  path?: string;
  username?: string;
  auth?: Auth;
  public_key?: string;
  jump?: string;
}

export interface Locations {
  locations: Location[];
  /** Whether the user may add one, as the installation's policy has it. */
  adds: boolean;
  /** The installation's tunnels switched on, which a location may go through. */
  tunnels: Tunnel[];
}

export const LOCATIONS = ['locations'];
export const LOCATION_ICONS = { smb: HardDrive, sftp: Server };

export const useLocations = ({ enabled = true } = {}) =>
  useQuery({
    queryKey: LOCATIONS,
    queryFn: () => getJson<Locations>('/api/locations'),
    enabled,
  });

export const asked = (path: string, more: Record<string, string> = {}) =>
  new URLSearchParams({ path, ...more }).toString();

/** The key of a location as a file source, under which its listings are cached. */
export const sourceKey = (id: string) => `location:${id}`;

export const listed = (id: string, path: string) =>
  getJson<{ path: string; entries: FileEntry[] }>(`/api/locations/${id}/files?${asked(path)}`);

/** The page of Files showing a source's folder, and a file of it opened in its place. */
export const filesHref = (source: string, path = '', file?: string | null) => {
  const query = new URLSearchParams();
  if (path) query.set('path', path);
  if (file) query.set('file', file);
  const asked = query.toString();
  return `/files/${encodeURIComponent(source)}${asked ? `?${asked}` : ''}`;
};
