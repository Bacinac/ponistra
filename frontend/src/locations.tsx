import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, Pencil, Share2, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { AddGrant } from './access';
import { deleteJson, getJson, patchJson, postJson, upload } from './api';
import type { Opened, Written } from './codeEditor';
import { ConfirmDialog, Modal } from './dialogs';
import { segment, type FileSource, type FileStat, type Listed } from './files';
import { Loading } from './frame';
import { Headed, inline, inlineField } from './headed';
import { useI18n } from './i18n';
import { runJob } from './jobs';
import {
  asked,
  filesHref,
  LOCATION_ICONS,
  LOCATIONS,
  sourceKey,
  useLocations,
  type Auth,
  type Kind,
  type Location,
} from './locationsData';
import { RemoveButton } from './mailParts';
import { ActionsMenu, MenuItem, MenuSeparator } from './menu';
import { Badge, granteeName } from './people';
import { ContainersAside } from './containers/aside';
import { button, field, primaryButton } from './styles';
import { errorMessage, type Grantee, type Role } from './tree';
import { CopyButton } from './vault/parts';

interface Grant {
  id: number;
  role: Role;
  grantee: Grantee;
}

const ROLES: Role[] = ['read', 'edit', 'own'];

const nameOf = (path: string) => path.split('/').pop() ?? path;

/** Files of a server as the backend reaches them below one address: a location of the network,
 * or a guest of a machine the user manages. */
export function servedSource(
  key: string,
  name: string,
  at: string,
  { writable, unix }: { writable: boolean; unix: boolean },
): FileSource {
  return {
    key,
    name,
    writable,
    list: (path) => getJson<Listed>(`${at}/files?${asked(path)}`),
    rawHref: (path, download) => `${at}/raw?${asked(path, download ? { download: '1' } : {})}`,
    pictureHref: (path) => `${at}/picture?${asked(path)}`,
    heldBase: (path) => `${at}/held/${segment(path)}`,
    zipHref: (paths) =>
      `${at}/zip?${new URLSearchParams(paths.map((path) => ['path', path])).toString()}`,
    read: (path) => getJson<Opened>(`${at}/text?${asked(path)}`),
    write: (path, text, hash) => postJson<Written>(`${at}/text`, { path, text, hash }),
    folder: (path, name) => postJson(`${at}/folder`, { path, name }),
    rename: (path, to) => postJson(`${at}/rename`, { path, to }),
    remove: (paths) => postJson(`${at}/remove`, { paths }),
    put: async (path, name, file) =>
      postJson(`${at}/put`, { path, name, blob: (await upload(file)).sha256 }),
    stat: (path) => getJson<FileStat>(`${at}/stat?${asked(path)}`),
    ...(writable && unix
      ? {
          mode: (path: string, mode: number) => postJson<FileStat>(`${at}/mode`, { path, mode }),
          owner: (path: string, uid: number, gid: number) =>
            postJson<FileStat>(`${at}/owner`, { path, uid, gid }),
        }
      : {}),
    search: (path, query) => getJson(`${at}/search?${asked(path, { q: query })}`),
    folderSize: (path) => getJson(`${at}/size?${asked(path)}`),
    checksum: (path, algorithm) =>
      runJob('checksum', { source: key, path, algorithm }, nameOf(path)),
  };
}

/** A location on the network as a file browser reads and changes it. */
export function locationSource(location: Location): FileSource {
  return {
    ...servedSource(sourceKey(location.id), location.name, `/api/locations/${location.id}`, {
      writable: location.role !== 'read',
      unix: location.kind !== 'smb',
    }),
    aside: (path, listedAt) => (
      <ContainersAside location={location.id} path={path} listedAt={listedAt} />
    ),
  };
}

function useLocationChange<V>(mutationFn: (variables: V) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: LOCATIONS }),
  });
}

function SharingDialog({ location, onClose }: { location: Location; onClose: () => void }) {
  const { t } = useI18n();
  const path = `/api/locations/${location.id}/grants`;
  const queryClient = useQueryClient();
  const key = [...LOCATIONS, 'grants', location.id];
  const grants = useQuery({
    queryKey: key,
    queryFn: () => getJson<{ grants: Grant[] }>(path),
    select: (data) => data.grants,
  });
  const told = () => queryClient.invalidateQueries({ queryKey: key });
  const give = useMutation({
    mutationFn: (grant: { kind: Grantee['kind']; id: number | null; role: Role }) =>
      postJson(path, grant),
    onSuccess: told,
  });
  const take = useMutation({
    mutationFn: (id: number) => deleteJson(`${path}/${id}`),
    onSuccess: told,
  });
  const failure = grants.error ?? give.error ?? take.error;
  return (
    <Modal heading={`${t('access.share')} ${location.name}`} onClose={onClose}>
      <AddGrant onAdd={(grantee, role) => give.mutate({ ...grantee, role })} />
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {grants.isPending ? (
        <Loading />
      ) : (
        <ul aria-label={t('access.title')} className="flex flex-col gap-2">
          {grants.data?.map((grant) => (
            <li key={grant.id} className="flex items-center gap-2">
              <Badge grantee={grant.grantee} />
              <span className="min-w-0 flex-1 truncate text-sm">
                {granteeName(grant.grantee, t)}
              </span>
              <select
                value={grant.role}
                aria-label={t('access.role')}
                disabled={give.isPending}
                onChange={(event) =>
                  give.mutate({
                    kind: grant.grantee.kind,
                    id: grant.grantee.id,
                    role: event.target.value as Role,
                  })
                }
                className="rounded border border-line bg-surface px-1 py-1 text-sm"
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {t(`access.role.${role}`)}
                  </option>
                ))}
              </select>
              <RemoveButton
                label={`${t('access.remove')} ${granteeName(grant.grantee, t)}`}
                disabled={take.isPending}
                onClick={() => take.mutate(grant.id)}
              />
            </li>
          ))}
        </ul>
      )}
      <div className="flex justify-end">
        <button type="button" onClick={onClose} className={button}>
          {t('frame.close')}
        </button>
      </div>
    </Modal>
  );
}

/** The fields of a location being added or changed; its password is sent only when typed. */
function LocationForm({
  location,
  onDone,
  onClose,
}: {
  location: Location | null;
  onDone: (saved: Location) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [kind, setKind] = useState<Kind>(location?.kind ?? 'smb');
  const [name, setName] = useState(location?.name ?? '');
  const [address, setAddress] = useState(location?.kind === 'smb' ? location.address : '');
  const [host, setHost] = useState(location?.host ?? '');
  const [port, setPort] = useState(String(location?.port ?? ''));
  const [path, setPath] = useState(location?.path ?? '');
  const [username, setUsername] = useState(location?.username ?? '');
  const [auth, setAuth] = useState<Auth>(location?.auth ?? 'password');
  const [password, setPassword] = useState('');
  const [jump, setJump] = useState(location?.jump ?? '');
  const was = location?.tunnel?.id ?? null;
  const [tunnel, setTunnel] = useState<number | null>(was);
  const tunnels = useLocations().data?.tunnels ?? [];
  const save = useLocationChange(() => {
    const shared = {
      name,
      username,
      ...(port ? { port: Number(port) } : {}),
      ...(password && auth === 'password' ? { password } : {}),
      ...(tunnel !== was ? { tunnel } : {}),
    };
    const given = kind === 'smb' ? { ...shared, address } : { ...shared, host, path, auth, jump };
    return location
      ? patchJson<Location>(`/api/locations/${location.id}`, given)
      : postJson<Location>('/api/locations', { kind, ...given });
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: (saved) => onDone(saved as Location) });
  };
  const text = (
    label: string,
    value: string,
    set: (value: string) => void,
    props: { required?: boolean; type?: string; placeholder?: string; narrow?: boolean } = {},
  ) => (
    <label className={props.narrow ? 'flex w-24 flex-col gap-1 text-sm' : inlineField}>
      {label}
      <input
        value={value}
        onChange={(event) => set(event.target.value)}
        required={props.required}
        type={props.type ?? 'text'}
        placeholder={props.placeholder}
        autoComplete="off"
        className={field}
      />
    </label>
  );
  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <div className={inline}>
        {!location && (
          <label className="flex flex-col gap-1 text-sm">
            {t('explorer.kind')}
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as Kind)}
              className={field}
            >
              <option value="smb">{t('locations.kind.smb')}</option>
              <option value="sftp">{t('locations.kind.sftp')}</option>
            </select>
          </label>
        )}
        {text(t('tree.name'), name, setName, { required: true })}
        {kind === 'smb' ? (
          text(t('locations.address'), address, setAddress, {
            required: true,
            placeholder: '\\\\server\\share',
          })
        ) : (
          <>
            {text(t('locations.host'), host, setHost, { required: true })}
            {text(t('locations.port'), port, setPort, {
              type: 'number',
              placeholder: '22',
              narrow: true,
            })}
            {text(t('locations.path'), path, setPath)}
          </>
        )}
      </div>
      <div className={inline}>
        {text(t('locations.username'), username, setUsername, { required: true })}
        {kind === 'sftp' && (
          <label className="flex flex-col gap-1 text-sm">
            {t('locations.auth')}
            <select
              value={auth}
              onChange={(event) => setAuth(event.target.value as Auth)}
              className={field}
            >
              <option value="password">{t('locations.auth.password')}</option>
              <option value="key">{t('locations.auth.key')}</option>
            </select>
          </label>
        )}
        {(kind === 'smb' || auth === 'password') &&
          text(t('locations.auth.password'), password, setPassword, {
            type: 'password',
            required: !location || location.auth !== 'password',
          })}
        {kind === 'sftp' &&
          text(t('locations.jump'), jump, setJump, { placeholder: 'user@host:22' })}
        {(tunnels.length > 0 || was !== null) && (
          <label className="flex flex-col gap-1 text-sm">
            {t('locations.tunnel')}
            <select
              value={tunnel ?? ''}
              onChange={(event) =>
                setTunnel(event.target.value ? Number(event.target.value) : null)
              }
              className={field}
            >
              <option value="">{t('locations.tunnelNone')}</option>
              {location?.tunnel && !tunnels.some((each) => each.id === was) && (
                <option value={location.tunnel.id}>{location.tunnel.name}</option>
              )}
              {tunnels.map((each) => (
                <option key={each.id} value={each.id}>
                  {each.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <button type="submit" disabled={save.isPending} className={primaryButton}>
          {t('tree.save')}
        </button>
        <button type="button" onClick={onClose} className={button}>
          {t('tree.cancel')}
        </button>
      </div>
      {save.error && (
        <p role="alert" className="text-sm text-danger">
          {errorMessage(save.error, t)}
        </p>
      )}
    </form>
  );
}

/** The key a location signs in with, for its server's authorized_keys. */
function PublicKey({ location }: { location: Location }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2 text-sm">
      <KeyRound size={14} aria-hidden className="shrink-0 text-muted" />
      <code className="min-w-0 flex-1 truncate font-mono text-xs">{location.public_key}</code>
      <CopyButton text={location.public_key!} label={t('locations.copyKey')} />
    </div>
  );
}

type Open =
  | { type: 'add' }
  | { type: 'edit'; id: string }
  | { type: 'share'; location: Location }
  | { type: 'remove'; location: Location };

/** Settings → Network locations: the locations the user set up, added, changed, shared and
 * removed here; their files are in Documents → Network. */
export function LocationSettings() {
  const { t } = useI18n();
  const found = useLocations();
  const [open, setOpen] = useState<Open | null>(null);
  const remove = useLocationChange((id: string) => deleteJson(`/api/locations/${id}`));
  const close = () => setOpen(null);
  const failure = found.error ?? remove.error;
  const locations = found.data?.locations ?? [];
  return (
    <Headed
      heading={t('locations.settings')}
      action={
        found.data?.adds &&
        open?.type !== 'add' && (
          <button type="button" onClick={() => setOpen({ type: 'add' })} className={button}>
            {t('locations.add')}
          </button>
        )
      }
    >
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {open?.type === 'add' && <LocationForm location={null} onDone={close} onClose={close} />}
      {found.isSuccess && locations.length === 0 && open?.type !== 'add' && (
        <p className="text-sm">{t('locations.none')}</p>
      )}
      <ul className="flex flex-col">
        {locations.map((each) => {
          const Icon = LOCATION_ICONS[each.kind];
          const mine = each.role === 'own';
          return (
            <li key={each.id} className="flex flex-col gap-2 border-b border-line py-2">
              <div className="flex items-center gap-3">
                <Icon size={18} aria-hidden className="shrink-0 text-muted" />
                <Link to={filesHref(`location:${each.id}`)} className="min-w-0 flex-1 truncate">
                  {each.name}
                  <span className="ml-2 text-sm text-muted">
                    {each.tunnel ? `${each.address} · ${each.tunnel.name}` : each.address}
                  </span>
                </Link>
                {!mine && <span className="text-sm text-muted">{each.owner.name}</span>}
                {mine && (
                  <ActionsMenu>
                    <MenuItem
                      icon={Pencil}
                      label={t('locations.edit')}
                      onSelect={() => setOpen({ type: 'edit', id: each.id })}
                    />
                    <MenuItem
                      icon={Share2}
                      label={t('access.share')}
                      onSelect={() => setOpen({ type: 'share', location: each })}
                    />
                    <MenuSeparator />
                    <MenuItem
                      icon={Trash2}
                      label={t('locations.remove')}
                      onSelect={() => setOpen({ type: 'remove', location: each })}
                    />
                  </ActionsMenu>
                )}
              </div>
              {mine && each.auth === 'key' && <PublicKey location={each} />}
              {open?.type === 'edit' && open.id === each.id && (
                <LocationForm location={each} onDone={close} onClose={close} />
              )}
            </li>
          );
        })}
      </ul>
      {open?.type === 'share' && <SharingDialog location={open.location} onClose={close} />}
      {open?.type === 'remove' && (
        <ConfirmDialog
          heading={`${t('locations.remove')} ${open.location.name}`}
          confirmLabel={t('locations.remove')}
          onConfirm={() => remove.mutate(open.location.id)}
          onClose={close}
        >
          {t('locations.removeBody')}
        </ConfirmDialog>
      )}
    </Headed>
  );
}
