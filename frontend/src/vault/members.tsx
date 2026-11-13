import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Clock, LogOut, UserCheck, X } from 'lucide-react';
import { useNavigate } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from '../api';
import { useSession, type User } from '../auth';
import { AddGrant } from '../access';
import { Close, Modal } from '../dialogs';
import { Panel } from '../frame';
import { useI18n } from '../i18n';
import { Badge, granteeName, usePeople } from '../people';
import { button, iconButton, primaryButton } from '../styles';
import { errorMessage, type Grantee, type Role } from '../tree';
import { fromBase64, sealTo, toBase64 } from './crypto';
import {
  collectionKey,
  COLLECTIONS,
  useOpenedItems,
  type Collection,
  type Unlocked,
} from './state';

const ROLES: Role[] = ['read', 'edit', 'own'];

interface Member {
  id: number;
  grantee: Grantee;
  role: Role;
}

interface Waiting extends User {
  public_key: string;
}

interface Members {
  role: Role;
  members: Member[];
  /** For owners: whom the collection reaches who have a vault and no key to it yet. */
  waiting?: Waiting[];
  /** For owners: whom it reaches who have no vault yet. */
  unset?: User[];
}

export function MembersPanel({
  collection,
  unlocked,
  onClose,
}: {
  collection: Collection;
  unlocked: Unlocked;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const me = useSession().data?.user;
  const people = usePeople();
  const queryKey = ['vault', 'members', collection.id];
  const path = `/api/vault/collections/${collection.id}`;
  const members = useQuery({ queryKey, queryFn: () => getJson<Members>(`${path}/members`) });

  async function confirmed(users: Waiting[]): Promise<Members> {
    const key = await collectionKey(unlocked, collection.key!);
    const keys = await Promise.all(
      users.map(async (user) => ({
        user: user.id,
        sealed: toBase64(await sealTo(fromBase64(user.public_key), key)),
      })),
    );
    return postJson<Members>(`${path}/keys`, { keys });
  }

  const reachedBy = (grantee: Pick<Grantee, 'kind' | 'id'>, user: User) =>
    grantee.kind === 'everyone' ||
    (grantee.kind === 'user'
      ? grantee.id === user.id
      : !!people.data?.users.find((person) => person.id === user.id)?.groups.includes(grantee.id!));

  const change = useMutation({
    mutationFn: (request: () => Promise<Members | void>) => request(),
    onSuccess: (now) => {
      if (now) queryClient.setQueryData(queryKey, now);
      else navigate('/vault');
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const add = (grantee: Pick<Grantee, 'kind' | 'id'>, role: Role) =>
    change.mutate(async () => {
      const now = await postJson<Members>(`${path}/members`, { grantee, role });
      const reached = (now.waiting ?? []).filter((user) => reachedBy(grantee, user));
      return reached.length && collection.key ? confirmed(reached) : now;
    });

  const data = members.data;
  const owner = data?.role === 'own';
  const managed = owner && collection.kind === 'shared';
  const mine = data?.members.find(
    (member) => member.grantee.kind === 'user' && member.grantee.id === me?.id,
  );

  return (
    <Panel title={t('vault.members')} onClose={onClose}>
      <p className="truncate font-semibold">{collection.name}</p>
      {members.isError && <p className="text-sm text-danger">{errorMessage(members.error, t)}</p>}
      {collection.kind === 'company' && (
        <p className="text-sm text-muted">{t('vault.companyMembers')}</p>
      )}
      {managed && <AddGrant onAdd={add} />}
      {change.isError && <p className="text-sm text-danger">{errorMessage(change.error, t)}</p>}
      {!!data?.waiting?.length && (
        <section className="flex flex-col gap-2 rounded border border-line p-2">
          <div className="flex items-center gap-2">
            <h3 className="flex-1 text-sm font-semibold">{t('vault.waiting')}</h3>
            {data.waiting.length > 1 && (
              <button
                type="button"
                disabled={change.isPending || !collection.key}
                onClick={() => change.mutate(() => confirmed(data.waiting!))}
                className={primaryButton}
              >
                {t('vault.confirmAll')}
              </button>
            )}
          </div>
          <p className="text-xs text-muted">{t('vault.confirmNote')}</p>
          <ul className="flex flex-col gap-2">
            {data.waiting.map((user) => (
              <li key={user.id} className="flex items-center gap-2">
                <Badge grantee={{ kind: 'user', id: user.id, name: user.name }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{user.name}</p>
                  <p className="truncate text-xs text-muted">{user.email}</p>
                </div>
                <button
                  type="button"
                  disabled={change.isPending || !collection.key}
                  onClick={() => change.mutate(() => confirmed([user]))}
                  className={button}
                >
                  <UserCheck size={16} aria-hidden />
                  {t('vault.confirm')}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {!!data?.unset?.length && (
        <p className="flex items-start gap-2 text-sm text-muted">
          <Clock size={16} aria-hidden className="mt-0.5 shrink-0" />
          <span>
            {t('vault.unset')}: {data.unset.map((user) => user.name).join(', ')}
          </span>
        </p>
      )}
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">{t('access.here')}</h3>
        <ul className="flex flex-col gap-2">
          {data?.members.map((member) => (
            <li key={member.id} className="flex items-center gap-2">
              <Badge grantee={member.grantee} />
              <p className="min-w-0 flex-1 truncate text-sm">{granteeName(member.grantee, t)}</p>
              {managed ? (
                <>
                  <select
                    value={member.role}
                    aria-label={t('access.role')}
                    onChange={(event) =>
                      change.mutate(() =>
                        patchJson<Members>(`/api/vault/members/${member.id}`, {
                          role: event.target.value,
                        }),
                      )
                    }
                    className="rounded border border-line bg-surface px-1 py-1 text-sm"
                  >
                    {ROLES.map((option) => (
                      <option key={option} value={option}>
                        {t(`access.role.${option}`)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    aria-label={t('access.remove')}
                    onClick={() =>
                      change.mutate(async () => {
                        await deleteJson(`/api/vault/members/${member.id}`);
                        return member === mine ? undefined : getJson<Members>(`${path}/members`);
                      })
                    }
                    className={iconButton}
                  >
                    <X size={16} />
                  </button>
                </>
              ) : (
                <span className="text-sm text-muted">{t(`access.role.${member.role}`)}</span>
              )}
            </li>
          ))}
        </ul>
      </section>
      {collection.kind === 'shared' && mine && (
        <button
          type="button"
          disabled={change.isPending}
          onClick={() =>
            change.mutate(async () => {
              await deleteJson(`/api/vault/members/${mine.id}`);
            })
          }
          className={`${button} self-start`}
        >
          <LogOut size={16} aria-hidden />
          {t('vault.leave')}
        </button>
      )}
    </Panel>
  );
}

interface Entry {
  kind: 'opened' | 'seen' | 'shared' | 'confirmed' | 'exported';
  user: User | null;
  subject: User | null;
  item: string | null;
  detail: { field?: 'password' | 'totp'; grantee?: Grantee; role?: Role | null };
  at: string;
}

export function LogDialog({
  collection,
  unlocked,
  onClose,
}: {
  collection: Collection;
  unlocked: Unlocked;
  onClose: () => void;
}) {
  const { t, formatDate } = useI18n();
  const log = useQuery({
    queryKey: ['vault', 'log', collection.id],
    queryFn: () => getJson<{ events: Entry[] }>(`/api/vault/collections/${collection.id}/log`),
  });
  const items = useOpenedItems(unlocked, collection);
  const named = new Map(items.data?.map((item) => [item.id, item.secret.name]));
  const entries = log.data?.events ?? [];
  const what = ({ kind, detail, item, subject }: Entry) => {
    if (kind === 'seen') {
      const name = (item && named.get(item)) ?? t('vault.log.gone');
      return `${t(detail.field === 'totp' ? 'vault.log.totp' : 'vault.log.password')}: ${name}`;
    }
    if (kind === 'confirmed')
      return `${t('vault.log.confirmed')}: ${subject?.name ?? t('log.formerUser')}`;
    if (kind === 'shared') {
      const whom = granteeName(detail.grantee!, t);
      return detail.role
        ? `${t('log.kind.shared')}: ${whom} · ${t(`access.role.${detail.role}`)}`
        : `${t('log.unshared')}: ${whom}`;
    }
    return t(`vault.log.${kind}`);
  };
  const cell = 'px-2 py-2';

  return (
    <Modal heading={`${t('log.title')}: ${collection.name}`} wide onClose={onClose}>
      {log.isError && <p className="text-sm text-danger">{errorMessage(log.error, t)}</p>}
      {log.isSuccess && entries.length === 0 && <p className="text-sm">{t('vault.log.none')}</p>}
      {entries.length > 0 && (
        <table className="w-full border-collapse">
          <thead className="text-left text-sm text-muted">
            <tr className="border-b border-line">
              <th className="px-2 py-2 font-normal whitespace-nowrap">{t('log.when')}</th>
              <th className="px-2 py-2 font-normal">{t('log.who')}</th>
              <th className="w-full px-2 py-2 font-normal">{t('log.what')}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              <tr key={index} className="border-b border-line align-top text-sm">
                <td className={`${cell} whitespace-nowrap text-muted`}>{formatDate(entry.at)}</td>
                <td className={`${cell} whitespace-nowrap`}>
                  {entry.user?.name ?? t('log.formerUser')}
                </td>
                <td className={`${cell} max-w-0`}>
                  <p className="truncate">{what(entry)}</p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}
