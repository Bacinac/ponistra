import { useQuery } from '@tanstack/react-query';
import { Brand } from '../Brand';
import { useI18n } from '../i18n';
import { EVERY, read, type Status } from './api';
import { BluetoothSection } from './bluetooth';
import { unauthorised } from './failure';
import { Reason } from './network';
import { WifiSection } from './wifi';

export const NETWORK = ['seat', 'network'] as const;

/** The desktop's screen while Ponistra does not answer: why, and the network and devices the
 * seat can set up meanwhile. The session leaves it for Ponistra once the network says `ok`. */
export function Seat() {
  const { t } = useI18n();
  const status = useQuery({
    queryKey: NETWORK,
    queryFn: () => read<Status>('network'),
    refetchInterval: EVERY,
    retry: false,
  });
  if (unauthorised(status.error)) {
    return (
      <main className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col justify-center gap-4 px-6">
        <Brand />
        <h1 className="text-2xl font-semibold">{t('seat.unauthorised')}</h1>
        <p>{t('seat.unauthorised.text')}</p>
      </main>
    );
  }
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-2xl flex-col gap-10 px-6 py-12">
      <Brand />
      <Reason status={status} />
      <WifiSection />
      <BluetoothSection />
    </main>
  );
}
