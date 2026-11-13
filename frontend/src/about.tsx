import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { getJson, type Revision } from './api';
import { Brand } from './Brand';
import { Close, Modal } from './dialogs';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';

const SOURCE = 'https://github.com/Bacinac/ponistra';
const AUTHOR = 'Ivo Bošković';
const CONTACT = 'ivo.boskovic.zg@gmail.com';
const LICENCE = 'https://polyformproject.org/licenses/noncommercial/1.0.0';
const FEATURES: MessageKey[] = [
  'about.documents',
  'about.together',
  'about.mail',
  'about.calendar',
  'about.meetings',
  'about.vault',
  'about.notes',
  'about.phone',
  'about.search',
  'about.agents',
];

export function useRevision() {
  return useQuery({
    queryKey: ['version'],
    queryFn: () => getJson<Revision>('/api/version'),
  });
}

/** Who made it, which build it runs and the way to About: one line at the foot of the side column. */
export function Signature() {
  const { t } = useI18n();
  const revision = useRevision();
  const [open, setOpen] = useState(false);
  return (
    <>
      <p className="flex gap-2 overflow-hidden text-xs whitespace-nowrap text-muted tabular-nums">
        <button
          type="button"
          title={t('about.title')}
          onClick={() => setOpen(true)}
          className="text-accent hover:underline"
        >
          {AUTHOR}
        </button>
        {revision.isSuccess && <span>v{revision.data.version}</span>}
        <span>© {new Date().getFullYear()}</span>
      </p>
      {open && <AboutDialog onClose={() => setOpen(false)} />}
    </>
  );
}

export function AboutDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const revision = useRevision();
  return (
    <Modal heading={t('about.title')} onClose={onClose}>
      <Brand compact />
      <div className="space-y-2 text-sm">
        <p>{t('about.summary')}</p>
        <ul className="list-disc space-y-1 pl-5">
          {FEATURES.map((key) => (
            <li key={key}>{t(key)}</li>
          ))}
        </ul>
      </div>
      <div className="space-y-2 text-sm">
        <p className="text-muted">
          {revision.isSuccess && `${t('status.version')} ${revision.data.version}`}
          {revision.isError && t('status.versionUnknown')}
        </p>
        <p>Copyright © 2026 {AUTHOR}</p>
        <p>
          {t('about.contact')}:{' '}
          <Link
            to={`/mail?${new URLSearchParams({ to: CONTACT, name: AUTHOR })}`}
            onClick={onClose}
            className="underline"
          >
            {CONTACT}
          </Link>
        </p>
        <p>{t('about.licence')}</p>
        <p className="flex gap-4">
          <a href={LICENCE} target="_blank" rel="noreferrer" className="underline">
            {t('about.licenceLink')}
          </a>
          <a href={SOURCE} target="_blank" rel="noreferrer" className="underline">
            {t('about.source')}
          </a>
        </p>
      </div>
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}
