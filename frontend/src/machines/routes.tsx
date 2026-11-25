import type { ReactNode } from 'react';
import type { RouteObject } from 'react-router';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { useMachine } from './api';
import { Guest } from './Guest';
import { Guests } from './Guests';
import { Hardware } from './Hardware';
import { Image } from './Image';
import { Overview } from './Overview';
import { Loaded } from './parts';
import { Pressure } from './Pressure';
import { SnapshotFiles } from './SnapshotFiles';
import { Tasks } from './Tasks';

/** The pages of one machine, in the order its menu shows them; `base` ones exist only on the
 * hypervisor, as the desktop has no Incus, ZFS or snapshots. */
export const MACHINE_PAGES: { path: string; label: MessageKey; base?: boolean }[] = [
  { path: '', label: 'machine.page.overview' },
  { path: 'pressure', label: 'machine.page.pressure' },
  { path: 'hardware', label: 'machine.page.hardware' },
  { path: 'image', label: 'machine.page.image' },
  { path: 'guests', label: 'machine.page.guests', base: true },
  { path: 'tasks', label: 'machine.page.tasks' },
];

function OnBase({ children }: { children: (base: boolean) => ReactNode }) {
  const machine = useMachine();
  return <Loaded query={machine}>{(data) => children(data.os.variant === 'base')}</Loaded>;
}

function BaseOnly({ children }: { children: ReactNode }) {
  return <OnBase>{(base) => (base ? children : <Missing />)}</OnBase>;
}

function Missing() {
  const { t } = useI18n();
  return <p className="text-sm text-muted">{t('machine.desktop.none')}</p>;
}

/** The routes under a machine's root: `/` on its own page, the machine's place in Computers. */
export const MACHINE_ROUTES: RouteObject[] = [
  { index: true, element: <Overview /> },
  { path: 'pressure', element: <Pressure /> },
  { path: 'hardware', element: <OnBase>{(base) => <Hardware pools={base} />}</OnBase> },
  { path: 'image', element: <Image /> },
  {
    path: 'guests',
    element: (
      <BaseOnly>
        <Guests />
      </BaseOnly>
    ),
  },
  {
    path: 'guests/:name',
    element: (
      <BaseOnly>
        <Guest />
      </BaseOnly>
    ),
  },
  {
    path: 'guests/:name/snapshots/:snapshot',
    element: (
      <BaseOnly>
        <SnapshotFiles />
      </BaseOnly>
    ),
  },
  { path: 'tasks', element: <Tasks /> },
];
