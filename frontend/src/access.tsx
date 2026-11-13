import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Copy, Download, History, Link2, Share2, UserPlus, X } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { useSession } from './auth';
import { Close, Modal } from './dialogs';
import { Panel } from './frame';
import { useI18n } from './i18n';
import { Badge, granteeName, reaches, usePeople } from './people';
import { button, field, iconButton, primaryButton } from './styles';
import {
  errorMessage,
  nodeHref,
  PlaceLink,
  TREE,
  type Grantee,
  type ListedNode,
  type Role,
  type TreeNode,
} from './tree';

const ROLES: Role[] = ['read', 'edit', 'own'];

interface Grant {
  id: string;
  grantee: Grantee;
  role: Role;
  /** Whether whoever it gives the node to may take it out of the browser (D39). */
  download: boolean;
  from?: { id: string | null; title: string | null } | null;
}

interface Access {
  role: Role;
  grants: Grant[];
  below: { node: TreeNode; path: string[]; grants: Grant[] }[];
}

interface Entry {
  node: Pick<TreeNode, 'id' | 'kind' | 'title' | 'href'>;
  user: { id: number; name: string } | null;
  kind: 'opened' | 'downloaded' | 'shared' | 'uploaded';
  detail: {
    format?: string;
    grantee?: Grantee;
    role?: Role | 'upload' | null;
    link?: string;
    sender?: string;
  };
  at: string;
}

function LogDialog({ node, onClose }: { node: TreeNode; onClose: () => void }) {
  const { t, formatDate } = useI18n();
  const log = useQuery({
    queryKey: ['access', node.id, 'log'],
    queryFn: () => getJson<{ entries: Entry[] }>(`/api/nodes/${node.id}/log`),
  });
  const entries = log.data?.entries ?? [];
  const what = ({ kind, detail }: Entry) => {
    if (kind === 'opened') return t(detail.link ? 'log.openedThroughLink' : 'log.kind.opened');
    if (kind === 'uploaded') return `${t('log.kind.uploaded')}: ${detail.sender}`;
    if (detail.link) {
      if (detail.role === 'upload') return t('log.uploadLinkMade');
      return t(detail.role ? 'log.linkMade' : 'log.linkEnded');
    }
    if (kind === 'downloaded')
      return `${t('log.kind.downloaded')} (${detail.format?.toUpperCase()})`;
    const whom = granteeName(detail.grantee!, t);
    const role = detail.role === 'upload' ? null : detail.role;
    return role
      ? `${t('log.kind.shared')}: ${whom} · ${t(`access.role.${role}`)}`
      : `${t('log.unshared')}: ${whom}`;
  };
  const cell = 'px-2 py-2';

  return (
    <Modal heading={`${t('log.title')}: ${node.title}`} wide onClose={onClose}>
      {node.kind === 'folder' && <p className="text-sm text-muted">{t('log.note')}</p>}
      {log.isError && <p className="text-sm text-danger">{errorMessage(log.error, t)}</p>}
      {log.isSuccess && entries.length === 0 && <p className="text-sm">{t('log.none')}</p>}
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
                  {entry.user?.name ?? t(entry.detail.link ? 'log.outsider' : 'log.formerUser')}
                </td>
                <td className={`${cell} max-w-0`}>
                  <p className="truncate">{what(entry)}</p>
                  {entry.node.id !== node.id && (
                    <PlaceLink
                      to={nodeHref(entry.node)}
                      className="block truncate text-xs text-muted hover:underline"
                    >
                      {entry.node.title}
                    </PlaceLink>
                  )}
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

export function Audience({ node }: { node: ListedNode }) {
  const { t, formatNumber } = useI18n();
  const me = useSession().data?.user;
  const everyone = node.audience.some((who) => who.kind === 'everyone');
  const others = node.audience.filter((who) => !(who.kind === 'user' && who.id === me?.id));
  const details = node.audience
    .map((who) => `${granteeName(who, t)}: ${t(`access.role.${who.role}`)}`)
    .join('\n');
  return (
    <span title={details} className="flex items-center gap-1">
      {node.wider && (
        <Share2 size={14} role="img" aria-label={t('access.wider')} className="shrink-0 text-ink" />
      )}
      {everyone ? (
        t('access.everyone')
      ) : others.length === 0 ? (
        t('access.onlyMe')
      ) : (
        <>
          {others.slice(0, 3).map((who) => (
            <Badge key={`${who.kind}-${who.id}`} grantee={who} small />
          ))}
          {others.length > 3 && `+${formatNumber(others.length - 3)}`}
        </>
      )}
    </span>
  );
}

export function AddGrant({
  onAdd,
}: {
  onAdd: (grantee: Pick<Grantee, 'kind' | 'id'>, role: Role) => void;
}) {
  const { t } = useI18n();
  const people = usePeople();
  const [grantee, setGrantee] = useState('');
  const [role, setRole] = useState<Role>('read');

  function submit(event: FormEvent) {
    event.preventDefault();
    const [kind, id] = grantee.split(':') as [Grantee['kind'], string?];
    onAdd({ kind, id: id ? Number(id) : null }, role);
    setGrantee('');
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <select
        required
        value={grantee}
        onChange={(event) => setGrantee(event.target.value)}
        aria-label={t('access.who')}
        className={field}
      >
        <option value="" disabled>
          {t('access.who')}
        </option>
        <option value="everyone">{t('access.everyone')}</option>
        <optgroup label={t('access.people')}>
          {people.data?.users.map((user) => (
            <option key={user.id} value={`user:${user.id}`}>
              {user.name}
            </option>
          ))}
        </optgroup>
        {!!people.data?.groups.length && (
          <optgroup label={t('access.groups')}>
            {people.data.groups.map((group) => (
              <option key={group.id} value={`group:${group.id}`}>
                {group.name}
              </option>
            ))}
          </optgroup>
        )}
      </select>
      <div className="flex gap-2">
        <select
          value={role}
          onChange={(event) => setRole(event.target.value as Role)}
          aria-label={t('access.role')}
          className={`${field} flex-1`}
        >
          {ROLES.map((option) => (
            <option key={option} value={option}>
              {t(`access.role.${option}`)}
            </option>
          ))}
        </select>
        <button type="submit" className={primaryButton}>
          {t('access.add')}
        </button>
      </div>
    </form>
  );
}

interface OutsideLink {
  id: string;
  kind: 'open' | 'people' | 'upload';
  download: boolean;
  /** Those a mail carried the link to, who come in by a code to their address. */
  addresses: string[];
  url: string;
  password: boolean;
  expires_at: string | null;
}

const OUTSIDE_ROLES = ['read', 'edit'] as const;

/** Shares the node with someone outside the installation by their address, who reads or edits
    it under their own name by a link mailed to them from the user's account (D39). */
function ShareOutside({ node, onDone }: { node: TreeNode; onDone: () => void }) {
  const { t, language } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [role, setRole] = useState<(typeof OUTSIDE_ROLES)[number]>('read');
  const [download, setDownload] = useState(true);
  const share = useMutation({
    mutationFn: () =>
      postJson(`/api/nodes/${node.id}/visitors`, { name, address, role, download, language }),
    onSuccess: onDone,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['access'] }),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    share.mutate();
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <input
        required
        autoFocus
        autoComplete="off"
        placeholder={t('outside.name')}
        aria-label={t('outside.name')}
        value={name}
        onChange={(event) => setName(event.target.value)}
        className={field}
      />
      <input
        type="email"
        required
        autoComplete="off"
        placeholder={t('outside.address')}
        aria-label={t('outside.address')}
        value={address}
        onChange={(event) => setAddress(event.target.value)}
        className={field}
      />
      <select
        value={role}
        onChange={(event) => setRole(event.target.value as typeof role)}
        aria-label={t('access.role')}
        className={field}
      >
        {OUTSIDE_ROLES.map((option) => (
          <option key={option} value={option}>
            {t(`access.role.${option}`)}
          </option>
        ))}
      </select>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={download}
          onChange={(event) => setDownload(event.target.checked)}
        />
        {t('outside.download')}
      </label>
      {share.isError && <p className="text-sm text-danger">{errorMessage(share.error, t)}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={share.isPending} className={primaryButton}>
          {t('outside.share')}
        </button>
        <button type="button" onClick={onDone} className={button}>
          {t('tree.cancel')}
        </button>
      </div>
    </form>
  );
}

function linkDetails(
  link: OutsideLink,
  t: ReturnType<typeof useI18n>['t'],
  formatDate: (at: string) => string,
) {
  return [
    t(`outside.kind.${link.kind}`),
    link.kind === 'people' && link.addresses.join(', '),
    link.expires_at ? `${t('outside.until')}: ${formatDate(link.expires_at)}` : t('outside.always'),
    link.password && t('outside.withPassword'),
    link.kind !== 'upload' && !link.download && t('outside.noDownload'),
  ]
    .filter(Boolean)
    .join(' · ');
}

/** Whom outside the installation the node reaches: by their address under their own name, by a
    link anyone holding it reads by, or, for a folder, one that asks for files (D39). */
function Outside({ node }: { node: TreeNode }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const key = ['access', node.id, 'outside'];
  const links = useQuery({
    queryKey: key,
    queryFn: () =>
      getJson<{ allowed: boolean; links: OutsideLink[] }>(`/api/nodes/${node.id}/outside-links`),
  });
  const [making, setMaking] = useState<'link' | 'person' | null>(null);
  const [kind, setKind] = useState<'open' | 'upload'>('open');
  const [until, setUntil] = useState('');
  const [password, setPassword] = useState('');
  const [download, setDownload] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: (request: () => Promise<unknown>) => request(),
    onSuccess: () => {
      setMaking(null);
      setUntil('');
      setPassword('');
      setDownload(true);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
  const copy = (link: OutsideLink) =>
    void navigator.clipboard.writeText(link.url).then(() => setCopied(link.id));
  const made = links.data?.links ?? [];
  if (!links.data?.allowed && made.length === 0) return null;

  const make = (event: FormEvent) => {
    event.preventDefault();
    const given =
      kind === 'upload'
        ? { kind, expires_on: until || null }
        : { kind, expires_on: until || null, password, download };
    change.mutate(() => postJson(`/api/nodes/${node.id}/outside-links`, given));
  };

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold">{t('outside.title')}</h3>
      {made.length > 0 && (
        <ul className="flex flex-col gap-2">
          {made.map((link) => (
            <li key={link.id} className="flex items-center gap-1">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{link.url}</p>
                <p className="truncate text-xs text-muted">{linkDetails(link, t, formatDate)}</p>
              </div>
              <button
                type="button"
                aria-label={t('outside.copy')}
                onClick={() => copy(link)}
                className={iconButton}
              >
                {copied === link.id ? <Check size={16} /> : <Copy size={16} />}
              </button>
              <button
                type="button"
                aria-label={t('outside.end')}
                onClick={() => change.mutate(() => deleteJson(`/api/outside-links/${link.id}`))}
                className={iconButton}
              >
                <X size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {change.isError && <p className="text-sm text-danger">{errorMessage(change.error, t)}</p>}
      {links.data?.allowed && making === 'person' && (
        <ShareOutside node={node} onDone={() => setMaking(null)} />
      )}
      {links.data?.allowed && making === 'link' && (
        <form onSubmit={make} className="flex flex-col gap-2">
          {node.kind === 'folder' && (
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as typeof kind)}
              aria-label={t('outside.kind')}
              className={field}
            >
              <option value="open">{t('outside.kind.open')}</option>
              <option value="upload">{t('outside.kind.upload')}</option>
            </select>
          )}
          <label className="flex flex-col gap-1 text-sm text-muted">
            {t('outside.until')}
            <input
              type="date"
              value={until}
              onChange={(event) => setUntil(event.target.value)}
              className={field}
            />
          </label>
          {kind === 'open' && (
            <>
              <label className="flex flex-col gap-1 text-sm text-muted">
                {t('outside.password')}
                <input
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className={field}
                />
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={download}
                  onChange={(event) => setDownload(event.target.checked)}
                />
                {t('outside.download')}
              </label>
            </>
          )}
          <div className="flex gap-2">
            <button type="submit" disabled={change.isPending} className={primaryButton}>
              {t('outside.make')}
            </button>
            <button type="button" onClick={() => setMaking(null)} className={button}>
              {t('tree.cancel')}
            </button>
          </div>
        </form>
      )}
      {links.data?.allowed && making === null && (
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => setMaking('person')} className={button}>
            <UserPlus size={16} aria-hidden />
            {t('outside.person')}
          </button>
          <button type="button" onClick={() => setMaking('link')} className={button}>
            <Link2 size={16} aria-hidden />
            {t('outside.make')}
          </button>
        </div>
      )}
    </section>
  );
}

export function AccessPanel({ node, onClose }: { node: TreeNode; onClose: () => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const access = useQuery({
    queryKey: ['access', node.id],
    queryFn: () => getJson<Access>(`/api/nodes/${node.id}/access`),
  });
  const people = usePeople();
  const [personId, setPersonId] = useState('');
  const [logOpen, setLogOpen] = useState(false);
  const change = useMutation({
    mutationFn: (request: () => Promise<unknown>) => request(),
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['access'] }),
        queryClient.invalidateQueries({ queryKey: TREE }),
      ]),
  });

  const person = people.data?.users.find((user) => String(user.id) === personId);
  const owner = access.data?.role === 'own';
  const managed = owner && !node.company;
  const grants = access.data?.grants.filter((grant) => reaches(grant.grantee, person)) ?? [];
  const below =
    access.data?.below.filter((item) =>
      item.grants.some((grant) => reaches(grant.grantee, person)),
    ) ?? [];

  const source = (grant: Grant) => {
    if (!grant.from) return t('access.direct');
    const { id, title } = grant.from;
    if (!id) return t('access.fromAbove');
    return (
      <>
        {t('access.from')}{' '}
        <Link to={nodeHref({ id, title: title ?? '', kind: 'folder' })} className="underline">
          {title}
        </Link>
      </>
    );
  };

  return (
    <Panel title={t('access.title')} onClose={onClose}>
      <p className="truncate font-semibold">{node.title}</p>
      {access.isError && <p className="text-sm text-danger">{errorMessage(access.error, t)}</p>}
      {managed && (
        <AddGrant
          onAdd={(grantee, role) =>
            change.mutate(() => postJson(`/api/nodes/${node.id}/grants`, { grantee, role }))
          }
        />
      )}
      {owner && node.kind === 'folder' && (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={node.confined}
            disabled={change.isPending}
            onChange={(event) => {
              const confined = event.target.checked;
              change.mutate(() => patchJson(`/api/nodes/${node.id}`, { confined }));
            }}
            className="mt-0.5"
          />
          <span className="flex flex-col">
            {t('confined.label')}
            <span className="text-xs text-muted">{t('confined.note')}</span>
          </span>
        </label>
      )}
      {change.isError && <p className="text-sm text-danger">{errorMessage(change.error, t)}</p>}
      <label className="flex flex-col gap-1 text-sm text-muted">
        {t('access.filter')}
        <select
          value={personId}
          onChange={(event) => setPersonId(event.target.value)}
          className={field}
        >
          <option value="">{t('access.anyone')}</option>
          {people.data?.users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.name}
            </option>
          ))}
        </select>
      </label>
      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">{t('access.here')}</h3>
        <ul className="flex flex-col gap-2">
          {grants.map((grant) => (
            <li key={grant.id} className="flex items-center gap-2">
              <Badge grantee={grant.grantee} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{granteeName(grant.grantee, t)}</p>
                <p className="truncate text-xs text-muted">
                  {grant.grantee.outside ? (
                    <>
                      {t('access.outside')} · {grant.grantee.email}
                    </>
                  ) : (
                    source(grant)
                  )}
                </p>
              </div>
              {managed && !grant.from && grant.grantee.outside && (
                <label
                  title={t('outside.download')}
                  className="flex items-center gap-1 text-xs text-muted"
                >
                  <input
                    type="checkbox"
                    checked={grant.download}
                    onChange={(event) => {
                      const download = event.target.checked;
                      change.mutate(() => patchJson(`/api/grants/${grant.id}`, { download }));
                    }}
                  />
                  <span className="sr-only">{t('outside.download')}</span>
                  <Download size={14} aria-hidden />
                </label>
              )}
              {managed && !grant.from ? (
                <>
                  <select
                    value={grant.role}
                    aria-label={t('access.role')}
                    onChange={(event) =>
                      change.mutate(() =>
                        patchJson(`/api/grants/${grant.id}`, { role: event.target.value }),
                      )
                    }
                    className="rounded border border-line bg-surface px-1 py-1 text-sm"
                  >
                    {(grant.grantee.outside ? OUTSIDE_ROLES : ROLES).map((option) => (
                      <option key={option} value={option}>
                        {t(`access.role.${option}`)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    aria-label={t('access.remove')}
                    onClick={() => change.mutate(() => deleteJson(`/api/grants/${grant.id}`))}
                    className={iconButton}
                  >
                    <X size={16} />
                  </button>
                </>
              ) : (
                <span className="text-sm text-muted">{t(`access.role.${grant.role}`)}</span>
              )}
            </li>
          ))}
        </ul>
      </section>
      {below.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">{t('access.below')}</h3>
          <ul className="flex flex-col gap-2">
            {below.map((item) => (
              <li key={item.node.id} className="flex flex-col">
                <PlaceLink to={nodeHref(item.node)} className="truncate text-sm hover:underline">
                  {item.path.join(' / ')}
                </PlaceLink>
                <span className="text-xs text-muted">
                  {item.grants
                    .map(
                      (grant) =>
                        `+ ${granteeName(grant.grantee, t)}: ${t(`access.role.${grant.role}`)}`,
                    )
                    .join(', ')}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {owner && node.kind !== 'link' && <Outside node={node} />}
      {owner && (
        <button type="button" onClick={() => setLogOpen(true)} className={`${button} self-start`}>
          <History size={16} aria-hidden />
          {t('log.title')}
        </button>
      )}
      {logOpen && <LogDialog node={node} onClose={() => setLogOpen(false)} />}
    </Panel>
  );
}
