import { useQuery } from '@tanstack/react-query';
import { getJson } from './api';
import { TREE, type FoundNode, type Role } from './tree';

export interface Listed extends FoundNode {
  role: Role;
}

export interface Links {
  /** The user's own folder of links, made the first time something goes into it. */
  folder: string | null;
  /** The user's groups, each level as they laid it out. */
  groups: Listed[];
  links: Listed[];
}

export const LINKS = [...TREE, 'links'];

export function useLinks() {
  return useQuery({
    queryKey: LINKS,
    queryFn: () => getJson<Links>('/api/links'),
  });
}
