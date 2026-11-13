import { useQuery } from '@tanstack/react-query';
import { Globe } from 'lucide-react';
import { getJson } from './api';
import type { User } from './auth';
import type { MessageKey } from './i18n/hr';
import type { Grantee } from './tree';

export interface Person extends User {
  groups: number[];
}

export interface GroupRef {
  id: number;
  name: string;
}

interface People {
  users: Person[];
  groups: GroupRef[];
}

export function usePeople() {
  return useQuery({ queryKey: ['people'], queryFn: () => getJson<People>('/api/people') });
}

export function initials(name: string): string {
  return name
    .split(/[\s.@_-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');
}

export function granteeName(grantee: Grantee, t: (key: MessageKey) => string): string {
  return grantee.kind === 'everyone' ? t('access.everyone') : grantee.name!;
}

export function reaches(grantee: Grantee, person: Person | undefined): boolean {
  if (!person || grantee.kind === 'everyone') return true;
  if (grantee.kind === 'user') return grantee.id === person.id;
  return person.groups.includes(grantee.id!);
}

export function Badge({ grantee, small }: { grantee: Grantee; small?: boolean }) {
  const size = small ? 'size-6 text-[0.625rem]' : 'size-8 text-xs';
  const shape = grantee.kind === 'user' ? 'rounded-full' : 'rounded';
  return (
    <span
      aria-hidden
      className={`flex shrink-0 items-center justify-center bg-selected font-semibold text-ink ${size} ${shape}`}
    >
      {grantee.kind === 'everyone' ? <Globe size={small ? 12 : 16} /> : initials(grantee.name!)}
    </span>
  );
}
