import { useQuery } from '@tanstack/react-query';
import { Box, Monitor, type LucideIcon } from 'lucide-react';
import { ApiError, getJson } from './api';
import type { FileSource } from './files';
import { servedSource } from './locations';

export interface Guest {
  name: string;
  /** lxc for a container, vm for a virtual machine. */
  kind: string;
  status: string;
}

/** A machine the user manages, with the guests it offers them, or why it listed none. */
export interface GuestsOf {
  id: string;
  name: string;
  guests: Guest[];
  error?: string;
}

export const GUESTS = ['guests'];

export const useGuests = ({ enabled = true } = {}) =>
  useQuery({
    queryKey: GUESTS,
    queryFn: () => getJson<{ computers: GuestsOf[] }>('/api/guests'),
    select: (data) => data.computers,
    enabled,
    staleTime: 60_000,
  });

export const guestKey = (computer: string, guest: string) => `computer:${computer}/${guest}`;

export const guestIcon = (guest: Guest): LucideIcon => (guest.kind === 'vm' ? Monitor : Box);

/** Why a machine listed no guests, as the tree shows a failure. */
export const guestsFailure = (computer: GuestsOf) =>
  computer.error ? new ApiError('/api/guests', 503, computer.error) : null;

/** A guest's files, root's in the guest, from its top. */
export const guestSource = (computer: GuestsOf, guest: Guest): FileSource =>
  servedSource(
    guestKey(computer.id, guest.name),
    guest.name,
    `/api/guests/${computer.id}/${encodeURIComponent(guest.name)}`,
    { writable: true, unix: true },
  );
