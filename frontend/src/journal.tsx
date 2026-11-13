import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Navigate } from 'react-router';
import { getJson } from './api';
import { useSession } from './auth';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { problemText } from './problems';
import { SettingsFrame } from './settings';
import { button, field } from './styles';
import { errorMessage } from './tree';

const GROUPS = ['sign_ins', 'accounts', 'settings', 'health'] as const;
type Group = (typeof GROUPS)[number];

interface Person {
  id: number;
  name: string;
  email: string;
}

interface Detail {
  way?: 'password' | 'passkey' | 'oidc' | 'saml';
  agent?: string;
  email?: string;
  name?: string;
  was?: string;
  changed?: string[];
  admin?: boolean;
  active?: boolean;
  setting?: string;
  change?: 'added' | 'changed' | 'removed';
  enabled?: boolean;
  problem?: string;
}

interface Entry {
  id: number;
  at: string;
  kind: string;
  actor: Person | null;
  subject: Person | null;
  address: string | null;
  detail: Detail;
}

interface Page {
  entries: Entry[];
  next: number | null;
}

type Translate = (key: MessageKey) => string;

function changes(detail: Detail, t: Translate): string {
  return (detail.changed ?? [])
    .map((field) => {
      const named = t(`journal.field.${field}` as MessageKey);
      if (field === 'admin') return `${named}: ${t(detail.admin ? 'journal.yes' : 'journal.no')}`;
      if (field === 'active') return `${named}: ${t(detail.active ? 'journal.yes' : 'journal.no')}`;
      return named;
    })
    .join(', ');
}

function setting(detail: Detail, t: Translate): string {
  const parts = [t(`journal.setting.${detail.setting}` as MessageKey)];
  if (detail.change) parts.push(t(`journal.change.${detail.change}`));
  if (detail.enabled !== undefined) parts.push(t(detail.enabled ? 'journal.on' : 'journal.off'));
  if (detail.name) parts.push(detail.name);
  return parts.join(', ');
}

/** What the entry says beside its kind. */
function told(entry: Entry, t: Translate): string {
  const { detail, subject } = entry;
  const whom = subject && subject.id !== entry.actor?.id ? subject.name : '';
  switch (entry.kind) {
    case 'signed_in':
      return detail.way ? t(`journal.way.${detail.way}`) : '';
    case 'sign_in_failed':
    case 'locked_out':
      return detail.email ?? '';
    case 'user_changed':
      return [whom, changes(detail, t)].filter(Boolean).join(': ');
    case 'user_erased':
      return subject ? `${t('journal.heir')}: ${subject.name}` : '';
    case 'group_renamed':
      return `${detail.was} → ${detail.name}`;
    case 'setting_changed':
      return setting(detail, t);
    case 'problem':
    case 'resolved':
      return problemText(detail.problem!, t);
    default:
      return [whom, detail.name].filter(Boolean).join(': ');
  }
}

function Entries({ group, person }: { group: Group | ''; person: number | null }) {
  const { t, formatDate } = useI18n();
  const journal = useInfiniteQuery({
    queryKey: ['journal', group, person],
    queryFn: ({ pageParam }) => {
      const asked = new URLSearchParams();
      if (group) asked.set('group', group);
      if (person !== null) asked.set('user', String(person));
      if (pageParam !== null) asked.set('before', String(pageParam));
      return getJson<Page>(`/api/journal?${asked}`);
    },
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next,
  });
  const entries = journal.data?.pages.flatMap((page) => page.entries) ?? [];
  const cell = 'px-2 py-2';
  if (journal.isError)
    return <p className="text-sm text-danger">{errorMessage(journal.error, t)}</p>;
  if (journal.isPending) return null;
  if (entries.length === 0) return <p className="text-sm">{t('journal.none')}</p>;
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead className="text-left text-sm text-muted">
            <tr className="border-b border-line">
              <th className={`${cell} font-normal whitespace-nowrap`}>{t('log.when')}</th>
              <th className={`${cell} font-normal`}>{t('log.who')}</th>
              <th className={`${cell} w-full font-normal`}>{t('log.what')}</th>
              <th className={`${cell} font-normal`}>{t('journal.address')}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => {
              const shown = told(entry, t);
              const kind = t(`journal.kind.${entry.kind}` as MessageKey);
              const warns = ['sign_in_failed', 'locked_out', 'problem'].includes(entry.kind);
              return (
                <tr key={entry.id} className="border-b border-line align-top text-sm">
                  <td className={`${cell} whitespace-nowrap text-muted`}>{formatDate(entry.at)}</td>
                  <td className={`${cell} whitespace-nowrap`}>
                    {entry.actor?.name ??
                      (entry.kind === 'problem' || entry.kind === 'resolved' ? 'Ponistra' : '–')}
                  </td>
                  <td className={`${cell} max-w-0`} title={entry.detail.agent}>
                    <p className={`truncate ${warns ? 'text-danger' : ''}`}>
                      {shown ? `${kind}: ${shown}` : kind}
                    </p>
                  </td>
                  <td className={`${cell} whitespace-nowrap text-muted tabular-nums`}>
                    {entry.address ?? ''}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {journal.hasNextPage && (
        <div>
          <button
            type="button"
            className={button}
            disabled={journal.isFetchingNextPage}
            onClick={() => void journal.fetchNextPage()}
          >
            {t('journal.more')}
          </button>
        </div>
      )}
    </>
  );
}

function Journal() {
  const { t } = useI18n();
  const [group, setGroup] = useState<Group | ''>('');
  const [person, setPerson] = useState<number | null>(null);
  const people = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getJson<{ users: Person[] }>('/api/users'),
  });
  return (
    <SettingsFrame title={t('journal.title')}>
      <div className="flex w-full max-w-5xl flex-col gap-4">
        <div className="flex flex-wrap gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('journal.group')}
            <select
              className={field}
              value={group}
              onChange={(event) => setGroup(event.target.value as Group | '')}
            >
              <option value="">{t('journal.group.all')}</option>
              {GROUPS.map((each) => (
                <option key={each} value={each}>
                  {t(`journal.group.${each}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('journal.person')}
            <select
              className={field}
              value={person ?? ''}
              onChange={(event) =>
                setPerson(event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">{t('journal.everyone')}</option>
              {people.data?.users.map((each) => (
                <option key={each.id} value={each.id}>
                  {each.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <Entries group={group} person={person} />
      </div>
    </SettingsFrame>
  );
}

export function JournalPage() {
  const me = useSession().data?.user;
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return <Journal />;
}
