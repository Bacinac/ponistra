import { useQuery } from '@tanstack/react-query';
import { HardDrive, Server } from 'lucide-react';
import { getJson } from './api';
import { compact } from './address';
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

/** The addresses of the places of Ponistra's own tree, each a page of Files. */
export const PONISTRA_HREFS: Record<string, string> = {
  mine: '/documents',
  company: '/company',
  shared: '/shared',
  sharing: '/shared?by=me',
  favourites: '/favourites',
  boards: '/boards',
};

/** The page of Files showing a source's folder, and a file of it opened in its place; a folder
 * of Ponistra's own tree keeps its own address. */
export const filesHref = (source: string, path = '', file?: string | null) => {
  if (source.startsWith('ponistra:')) {
    const root = source.slice('ponistra:'.length);
    const last = path.split('/').pop();
    return last ? `/${root === 'boards' ? 'boards' : 'f'}/${compact(last)}` : PONISTRA_HREFS[root];
  }
  const query = new URLSearchParams();
  if (path) query.set('path', path);
  if (file) query.set('file', file);
  const asked = query.toString();
  return `/files/${encodeURIComponent(source)}${asked ? `?${asked}` : ''}`;
};
