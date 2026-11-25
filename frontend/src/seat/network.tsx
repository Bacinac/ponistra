import type { UseQueryResult } from '@tanstack/react-query';
import { Cable, ExternalLink, Globe, Wifi } from 'lucide-react';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { primaryButton } from '../styles';
import type { Cause, Interface, Status } from './api';
import { failure } from './failure';

const CAUSES: Record<Cause, [MessageKey, MessageKey]> = {
  ok: ['seat.cause.ok', 'seat.cause.ok.text'],
  'not-configured': ['seat.cause.notConfigured', 'seat.cause.notConfigured.text'],
  'no-link': ['seat.cause.noLink', 'seat.cause.noLink.text'],
  'no-address': ['seat.cause.noAddress', 'seat.cause.noAddress.text'],
  'no-dns': ['seat.cause.noDns', 'seat.cause.noDns.text'],
  portal: ['seat.cause.portal', 'seat.cause.portal.text'],
  unreachable: ['seat.cause.unreachable', 'seat.cause.unreachable.text'],
};

function host(address: string | undefined): string {
  try {
    return address ? new URL(address).host : '';
  } catch {
    return address ?? '';
  }
}

function Link({ link }: { link: Interface }) {
  const { t } = useI18n();
  const Icon = link.wireless ? Wifi : Cable;
  // Link-local addresses come with every link and tell nothing about the network.
  const addresses = (link.addresses ?? []).filter((address) => !address.startsWith('fe80:'));
  const state = !link.carrier
    ? t('seat.link.down')
    : addresses.length
      ? addresses.join(', ')
      : t('seat.link.noAddress');
  return (
    <li className="flex min-w-0 items-center gap-2">
      <Icon size={16} aria-hidden className="shrink-0" />
      <span>
        {t(link.wireless ? 'seat.link.wireless' : 'seat.link.cable')} ({link.name})
      </span>
      <span className="min-w-0 truncate text-muted">{state}</span>
    </li>
  );
}

/** Why Ponistra has not opened, with what the person at the seat can do about it. */
export function Reason({ status }: { status: UseQueryResult<Status, Error> }) {
  const { t } = useI18n();
  if (status.error && !status.data) {
    return (
      <section className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">{t('seat.agentDown')}</h1>
        <p role="alert" className="text-danger">
          {failure(status.error, t)}
        </p>
      </section>
    );
  }
  if (!status.data) return <p className="text-muted">{t('seat.checking')}</p>;
  const { cause, ponistra, portal_url, detail } = status.data;
  const [heading, text] = CAUSES[cause] ?? ['seat.cause.unknown', 'seat.cause.unknown.text'];
  const links = status.data.interfaces ?? [];
  return (
    <section className="flex flex-col gap-3" aria-live="polite">
      <h1 className="text-2xl font-semibold">{t(heading)}</h1>
      <p>{t(text).replace('{address}', host(ponistra) || 'Ponistra')}</p>
      {cause === 'portal' && portal_url && (
        <a
          className={`${primaryButton} self-start`}
          href={portal_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink size={16} aria-hidden />
          {t('seat.portal')}
        </a>
      )}
      {detail && <p className="text-sm break-words text-muted">{detail}</p>}
      {(links.length > 0 || ponistra) && (
        <ul className="flex flex-col gap-1 text-sm">
          {links.map((link) => (
            <Link key={link.name} link={link} />
          ))}
          {ponistra && (
            <li className="flex min-w-0 items-center gap-2">
              <Globe size={16} aria-hidden className="shrink-0" />
              <span>Ponistra</span>
              <span className="min-w-0 truncate text-muted">{host(ponistra)}</span>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
