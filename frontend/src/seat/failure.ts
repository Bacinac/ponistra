import type { MessageKey } from '../i18n/hr';
import { SeatError } from './api';

const STATUSES: Record<number, MessageKey> = {
  400: 'seat.error.refused',
  401: 'seat.error.unauthorised',
  404: 'seat.error.gone',
  409: 'seat.error.busy',
};

/** What went wrong, in words: `own` names what a status means for the action that met it. */
export function failure(
  error: Error,
  t: (key: MessageKey) => string,
  own: Partial<Record<number, MessageKey>> = {},
): string {
  if (!(error instanceof SeatError)) return `${t('seat.error.unexpected')}: ${error.message}`;
  const key = own[error.status] ?? STATUSES[error.status];
  if (!key) return `${t('seat.error.unexpected')}: ${error.message}`;
  // A 409 covers several cases the agent tells apart only in its reason.
  return error.status === 409 && !own[409] && error.reason ? `${t(key)}: ${error.reason}` : t(key);
}

export function unauthorised(error: Error | null): boolean {
  return error instanceof SeatError && error.status === 401;
}
