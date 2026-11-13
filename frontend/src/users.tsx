import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Download,
  FolderPlus,
  LifeBuoy,
  Lock,
  MonitorSmartphone,
  Pencil,
  Plus,
  Trash2,
  UserCheck,
  UserX,
  Users,
} from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { useSession } from './auth';
import { DevicesDialog } from './devices';
import {
  FILE_SERVER_LOOKS,
  FileServerDialog,
  FileServerLine,
  fileServerActions,
  useFileServerChange,
  type FileServer,
  type FileServerAction,
} from './fileServer';
import { Cancel, ConfirmDialog, Modal, NameDialog } from './dialogs';
import { Loaded, PrimaryAction } from './frame';
import { saveJob } from './jobs';
import { SettingsFrame } from './settings';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { ActionsMenu, MenuItem, MenuSeparator } from './menu';
import type { GroupRef } from './people';
import { button, dangerButton, field, primaryButton } from './styles';
import { errorMessage, TREE, type Role } from './tree';
import { ProvidersSection } from './identityProviders';
import { RecoverDialog, RecoverySection } from './vault/admin';

interface Account {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  name: string;
  is_admin: boolean;
  is_active: boolean;
  groups: number[];
  last_login: string | null;
  /** The directory that keeps the account's address, name, password and whether it is active. */
  kept_by: string | null;
  providers: string[];
}

interface AccountGroup extends GroupRef {
  /** The provider whose group it is, which alone names it and says who is in it. */
  kept_by: string | null;
}

interface Accounts {
  users: Account[];
  groups: AccountGroup[];
}

/** A company folder of documents, or a company collection of the vault, which the
    administrator lays out for groups. */
interface CompanyPlace {
  id: string;
  name: string;
  confined?: boolean;
  grants: { group: GroupRef | null; role: Role }[];
  share?: FileServer | null;
}

type CompanyLabel =
  'title' | 'note' | 'none' | 'new' | 'edit' | 'delete' | 'deleteTitle' | 'deleteWarning';

interface CompanyKind {
  path: string;
  queryKey: string[];
  /** The queries a change to one of its places makes stale. */
  touches: string[][];
  /** Whether a place may be closed to all but those it names, as a folder may. */
  confinable: boolean;
  /** Whether a place may be connected to a folder on a file server, as a folder may (D37). */
  connectable: boolean;
  read: (data: unknown) => CompanyPlace[];
  body: (given: {
    name: string;
    confined: boolean;
    grants: { group: number | null; role: Role }[];
  }) => object;
  labels: Record<CompanyLabel, MessageKey>;
}

type Passkeys = 'nobody' | 'administrators' | 'everyone';

const ROLES: Role[] = ['read', 'edit', 'own'];
const PASSKEYS: Passkeys[] = ['nobody', 'administrators', 'everyone'];
type Outside = 'nobody' | 'administrators' | 'everyone';
const OUTSIDE: Outside[] = ['nobody', 'administrators', 'everyone'];
const COMPANY = ['company'];
const POLICY = ['policy'];

const FOLDERS: CompanyKind = {
  path: '/api/company',
  queryKey: COMPANY,
  touches: [COMPANY, TREE],
  confinable: true,
  connectable: true,
  read: (data) =>
    (data as { folders: (Omit<CompanyPlace, 'name'> & { title: string })[] }).folders.map(
      ({ title, ...folder }) => ({ ...folder, name: title }),
    ),
  body: ({ name, confined, grants }) => ({ title: name, confined, grants }),
  labels: {
    title: 'company.title',
    note: 'company.note',
    none: 'company.none',
    new: 'company.new',
    edit: 'company.edit',
    delete: 'company.delete',
    deleteTitle: 'company.deleteTitle',
    deleteWarning: 'company.deleteWarning',
  },
};

const VAULT: CompanyKind = {
  path: '/api/vault/company',
  queryKey: ['vault', 'company'],
  touches: [['vault']],
  confinable: false,
  connectable: false,
  read: (data) => (data as { collections: CompanyPlace[] }).collections,
  body: ({ name, grants }) => ({ name, grants }),
  labels: {
    title: 'vault.company.title',
    note: 'vault.company.note',
    none: 'vault.company.none',
    new: 'vault.company.new',
    edit: 'vault.company.edit',
    delete: 'vault.company.delete',
    deleteTitle: 'vault.company.deleteTitle',
    deleteWarning: 'vault.company.deleteWarning',
  },
};

type Dialog =
  | { type: 'account'; account?: Account }
  | { type: 'group'; group?: GroupRef }
  | { type: 'deactivate'; account: Account }
  | { type: 'erase'; account: Account }
  | { type: 'devices'; account: Account }
  | { type: 'deleteGroup'; group: GroupRef }
  | { type: 'company'; kind: CompanyKind; place?: CompanyPlace }
  | { type: 'deleteCompany'; kind: CompanyKind; place: CompanyPlace }
  | { type: 'fileServer'; kind: CompanyKind; place: CompanyPlace; action: FileServerAction }
  | { type: 'recover'; account: Account };

function useAccountChange<V>(mutationFn: (variables: V) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () =>
      Promise.all(
        [['accounts'], ['people'], ['access'], TREE].map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      ),
  });
}

function AccountDialog({
  account,
  groups,
  onClose,
}: {
  account?: Account;
  groups: AccountGroup[];
  onClose: () => void;
}) {
  const { t } = useI18n();
  const me = useSession().data?.user;
  const kept = !!account?.kept_by;
  const [form, setForm] = useState({
    first_name: account?.first_name ?? '',
    last_name: account?.last_name ?? '',
    email: account?.email ?? '',
    password: '',
    is_admin: account?.is_admin ?? false,
    groups: new Set(account?.groups ?? []),
  });
  const save = useAccountChange(() => {
    const { password, ...fields } = { ...form, groups: [...form.groups] };
    const body = password ? { ...fields, password } : fields;
    return account ? patchJson(`/api/users/${account.id}`, body) : postJson('/api/users', body);
  });
  const set = (changes: Partial<typeof form>) => setForm({ ...form, ...changes });
  const toggle = (group: number) => {
    const next = new Set(form.groups);
    if (!next.delete(group)) next.add(group);
    set({ groups: next });
  };

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: onClose });
  }

  const text = (name: 'first_name' | 'last_name' | 'email', label: string, type = 'text') => (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <input
        type={type}
        required={name === 'email'}
        disabled={kept}
        maxLength={name === 'email' ? 254 : 150}
        value={form[name]}
        onChange={(event) => set({ [name]: event.target.value })}
        className={field}
      />
    </label>
  );

  return (
    <Modal heading={t(account ? 'users.edit' : 'users.new')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3">
          {text('first_name', t('users.firstName'))}
          {text('last_name', t('users.lastName'))}
        </div>
        {text('email', t('auth.email'), 'email')}
        <label className="flex flex-col gap-1 text-sm">
          {t(account ? 'password.new' : 'auth.password')}
          <input
            type="password"
            autoComplete="new-password"
            required={!account}
            disabled={kept}
            placeholder={account?.kept_by ?? (account ? t('users.keepPassword') : undefined)}
            value={form.password}
            onChange={(event) => set({ password: event.target.value })}
            className={field}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_admin}
            disabled={account?.id === me?.id}
            onChange={(event) => set({ is_admin: event.target.checked })}
          />
          {t('users.admin')}
        </label>
        {groups.length > 0 && (
          <fieldset className="flex flex-col gap-1 text-sm">
            <legend className="mb-1">{t('access.groups')}</legend>
            {groups.map((group) => (
              <label key={group.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.groups.has(group.id)}
                  disabled={!!group.kept_by}
                  onChange={() => toggle(group.id)}
                />
                {group.name}
              </label>
            ))}
          </fieldset>
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t(account ? 'tree.save' : 'tree.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** The account erased for good, the documents only it owns passing to the heir chosen. */
function EraseDialog({
  account,
  accounts,
  onClose,
}: {
  account: Account;
  accounts: Account[];
  onClose: () => void;
}) {
  const { t } = useI18n();
  const me = useSession().data?.user;
  const heirs = accounts.filter((each) => each.is_active && each.id !== account.id);
  const [heir, setHeir] = useState(me?.id);
  const erase = useAccountChange(() => deleteJson(`/api/users/${account.id}?heir=${heir ?? ''}`));

  function submit(event: FormEvent) {
    event.preventDefault();
    erase.mutate(undefined, { onSuccess: onClose });
  }

  return (
    <Modal heading={t('users.eraseTitle')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <p className="text-sm">
          <strong>{account.name}</strong> {t('users.eraseWarning')}
        </p>
        <label className="flex flex-col gap-1 text-sm">
          {t('users.heir')}
          <select
            value={heir ?? ''}
            onChange={(event) => setHeir(Number(event.target.value))}
            className={field}
          >
            {heirs.map((each) => (
              <option key={each.id} value={each.id}>
                {each.name}
              </option>
            ))}
          </select>
        </label>
        {erase.isError && <p className="text-sm text-danger">{errorMessage(erase.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={erase.isPending} className={dangerButton}>
            {t('users.erase')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** A company folder laid out and given to groups, everyone standing in for the null group. */
function CompanyDialog({
  kind,
  place,
  groups,
  onClose,
}: {
  kind: CompanyKind;
  place?: CompanyPlace;
  groups: GroupRef[];
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(place?.name ?? '');
  const [confined, setConfined] = useState(place?.confined ?? false);
  const [roles, setRoles] = useState(
    () => new Map(place?.grants.map((grant) => [grant.group?.id ?? null, grant.role])),
  );
  const save = useMutation({
    mutationFn: () => {
      const grants = [...roles].map(([id, role]) => ({ group: id, role }));
      const body = kind.body({ name: title, confined, grants });
      return place ? patchJson(`${kind.path}/${place.id}`, body) : postJson(kind.path, body);
    },
    onSuccess: () => {
      for (const queryKey of kind.touches) void queryClient.invalidateQueries({ queryKey });
      onClose();
    },
  });
  const choose = (group: number | null, role: string) => {
    const next = new Map(roles);
    if (role) next.set(group, role as Role);
    else next.delete(group);
    setRoles(next);
  };

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  const audience: [number | null, string][] = [
    [null, t('access.everyone')],
    ...groups.map((group): [number, string] => [group.id, group.name]),
  ];

  return (
    <Modal heading={t(kind.labels[place ? 'edit' : 'new'])} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('tree.name')}
          <input
            required
            maxLength={200}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className={field}
          />
        </label>
        <fieldset className="flex flex-col gap-2 text-sm">
          <legend className="mb-1">{t('access.here')}</legend>
          {audience.map(([group, name]) => (
            <label key={group ?? 'everyone'} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate">{name}</span>
              <select
                value={roles.get(group) ?? ''}
                onChange={(event) => choose(group, event.target.value)}
                className={field}
              >
                <option value="">{t('company.noRole')}</option>
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {t(`access.role.${role}`)}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </fieldset>
        {kind.confinable && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={confined}
              onChange={(event) => setConfined(event.target.checked)}
              className="mt-0.5"
            />
            <span className="flex flex-col">
              {t('confined.label')}
              <span className="text-xs text-muted">{t('confined.note')}</span>
            </span>
          </label>
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="submit"
            disabled={save.isPending || ![...roles.values()].includes('own')}
            className={primaryButton}
          >
            {t(place ? 'tree.save' : 'tree.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function CompanySection({
  kind,
  onEdit,
  onDelete,
  onFileServer,
}: {
  kind: CompanyKind;
  onEdit: (place?: CompanyPlace) => void;
  onDelete: (place: CompanyPlace) => void;
  onFileServer: (place: CompanyPlace, action: FileServerAction) => void;
}) {
  const { t } = useI18n();
  const places = useQuery({
    queryKey: kind.queryKey,
    queryFn: async () => kind.read(await getJson<unknown>(kind.path)),
  });
  const given = (place: CompanyPlace) =>
    place.grants
      .map(
        (grant) =>
          `${grant.group?.name ?? t('access.everyone')}: ${t(`access.role.${grant.role}`)}`,
      )
      .join(' · ');

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h2 className="flex-1 font-semibold">{t(kind.labels.title)}</h2>
        <button type="button" className={button} onClick={() => onEdit()}>
          <FolderPlus size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t(kind.labels.new)}</span>
        </button>
      </div>
      <p className="text-sm text-muted">{t(kind.labels.note)}</p>
      {places.isError && <p className="text-sm text-danger">{errorMessage(places.error, t)}</p>}
      {places.data?.length === 0 && <p className="text-sm text-muted">{t(kind.labels.none)}</p>}
      {!!places.data?.length && (
        <ul className="divide-y divide-line rounded border border-line">
          {places.data.map((place) => (
            <li key={place.id} className="flex items-center gap-2 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2">
                  <span className="truncate">{place.name}</span>
                  {place.confined && (
                    <Lock
                      size={14}
                      role="img"
                      aria-label={t('confined.label')}
                      className="shrink-0 text-muted"
                    />
                  )}
                </p>
                <p className="truncate text-xs text-muted">{given(place)}</p>
                {place.share && <FileServerLine share={place.share} />}
              </div>
              <ActionsMenu>
                <MenuItem
                  icon={Pencil}
                  label={t(kind.labels.edit)}
                  onSelect={() => onEdit(place)}
                />
                {kind.connectable && (
                  <>
                    <MenuSeparator />
                    {fileServerActions(place.share).map((action) => (
                      <MenuItem
                        key={action}
                        icon={FILE_SERVER_LOOKS[action].icon}
                        label={t(FILE_SERVER_LOOKS[action].label)}
                        onSelect={() => onFileServer(place, action)}
                      />
                    ))}
                  </>
                )}
                <MenuSeparator />
                <MenuItem
                  icon={Trash2}
                  label={t(kind.labels.delete)}
                  onSelect={() => onDelete(place)}
                />
              </ActionsMenu>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OutsidePolicySection() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const policy = useQuery({
    queryKey: POLICY,
    queryFn: () => getJson<{ passkeys: Passkeys; outside: Outside }>('/api/policy'),
  });
  const change = useMutation({
    mutationFn: (outside: Outside) => patchJson('/api/policy', { outside }),
    onSuccess: (changed) => queryClient.setQueryData(POLICY, changed),
  });
  const failure = policy.error ?? change.error;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">{t('policy.outside.title')}</h2>
      <label className="flex flex-col gap-1 text-sm sm:max-w-xs">
        {t('policy.outside')}
        <select
          value={policy.data?.outside ?? ''}
          disabled={!policy.isSuccess || change.isPending}
          onChange={(event) => change.mutate(event.target.value as Outside)}
          className={field}
        >
          {OUTSIDE.map((option) => (
            <option key={option} value={option}>
              {t(`policy.outside.${option}`)}
            </option>
          ))}
        </select>
      </label>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
    </section>
  );
}

function PolicySection() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const policy = useQuery({
    queryKey: POLICY,
    queryFn: () => getJson<{ passkeys: Passkeys; outside: Outside }>('/api/policy'),
  });
  const change = useMutation({
    mutationFn: (passkeys: Passkeys) => patchJson('/api/policy', { passkeys }),
    onSuccess: (changed) => queryClient.setQueryData(POLICY, changed),
  });
  const failure = policy.error ?? change.error;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-semibold">{t('policy.title')}</h2>
      <label className="flex flex-col gap-1 text-sm sm:max-w-xs">
        {t('policy.passkeys')}
        <select
          value={policy.data?.passkeys ?? ''}
          disabled={!policy.isSuccess || change.isPending}
          onChange={(event) => change.mutate(event.target.value as Passkeys)}
          className={field}
        >
          {PASSKEYS.map((option) => (
            <option key={option} value={option}>
              {t(`policy.passkeys.${option}`)}
            </option>
          ))}
        </select>
      </label>
      <p className="text-sm text-muted">{t('policy.note')}</p>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
    </section>
  );
}

function Directory({ accounts }: { accounts: Accounts }) {
  const { t, formatDate, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const me = useSession().data?.user;
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const activate = useAccountChange((account: Account) =>
    patchJson(`/api/users/${account.id}`, { is_active: true }),
  );
  const deactivate = useAccountChange((account: Account) =>
    patchJson(`/api/users/${account.id}`, { is_active: false }),
  );
  const removeGroup = useAccountChange((group: GroupRef) => deleteJson(`/api/groups/${group.id}`));
  const exportData = useMutation({
    mutationFn: (account: Account) =>
      saveJob('personal', { user: account.id }, `${account.email}.zip`),
  });
  const removeCompany = useMutation({
    mutationFn: ({ kind, place }: { kind: CompanyKind; place: CompanyPlace }) =>
      deleteJson(`${kind.path}/${place.id}`),
    onSuccess: (_, { kind }) =>
      Promise.all(kind.touches.map((queryKey) => queryClient.invalidateQueries({ queryKey }))),
  });
  const fileServer = useFileServerChange(FOLDERS.touches);
  const close = () => setDialog(null);
  const named = new Map(accounts.groups.map((group) => [group.id, group.name]));
  const members = (group: GroupRef) =>
    accounts.users.filter((account) => account.groups.includes(group.id)).length;
  const failure =
    activate.error ??
    deactivate.error ??
    removeGroup.error ??
    exportData.error ??
    removeCompany.error ??
    fileServer.error;
  const cell = 'px-2 py-2 whitespace-nowrap';

  return (
    <SettingsFrame
      title={t('users.title')}
      actions={
        <button type="button" className={button} onClick={() => setDialog({ type: 'group' })}>
          <Users size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('users.newGroup')}</span>
        </button>
      }
      primary={
        <PrimaryAction
          icon={Plus}
          label={t('users.new')}
          onClick={() => setDialog({ type: 'account' })}
        />
      }
    >
      <div className="flex w-full max-w-5xl flex-col gap-8">
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        <table className="w-full border-collapse">
          <thead className="text-left text-sm text-muted">
            <tr className="border-b border-line">
              <th className="w-full px-2 py-2 font-normal">{t('tree.name')}</th>
              <th className="hidden px-2 py-2 font-normal md:table-cell">{t('auth.email')}</th>
              <th className="hidden px-2 py-2 font-normal lg:table-cell">{t('access.groups')}</th>
              <th className="hidden px-2 py-2 font-normal sm:table-cell">{t('users.lastLogin')}</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {accounts.users.map((account) => (
              <tr
                key={account.id}
                className={`border-b border-line ${account.is_active ? '' : 'text-muted'}`}
              >
                <td className={`${cell} max-w-0`}>
                  <p className="truncate">{account.name}</p>
                  <p className="truncate text-xs text-muted">
                    {[
                      account.is_admin && t('users.admin'),
                      !account.is_active && t('users.inactive'),
                      ...account.providers,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                </td>
                <td className={`${cell} hidden text-sm md:table-cell`}>{account.email}</td>
                <td className={`${cell} hidden text-sm text-muted lg:table-cell`}>
                  {account.groups.map((group) => named.get(group)).join(', ')}
                </td>
                <td className={`${cell} hidden text-sm text-muted sm:table-cell`}>
                  {account.last_login ? formatDate(account.last_login) : t('users.never')}
                </td>
                <td className="pr-2">
                  <ActionsMenu>
                    <MenuItem
                      icon={Pencil}
                      label={t('users.edit')}
                      onSelect={() => setDialog({ type: 'account', account })}
                    />
                    <MenuItem
                      icon={MonitorSmartphone}
                      label={t('devices.title')}
                      onSelect={() => setDialog({ type: 'devices', account })}
                    />
                    <MenuItem
                      icon={LifeBuoy}
                      label={t('recovery.recover')}
                      onSelect={() => setDialog({ type: 'recover', account })}
                    />
                    <MenuItem
                      icon={account.is_active ? UserX : UserCheck}
                      label={t(account.is_active ? 'users.deactivate' : 'users.activate')}
                      disabled={account.id === me?.id || !!account.kept_by}
                      onSelect={() =>
                        account.is_active
                          ? setDialog({ type: 'deactivate', account })
                          : activate.mutate(account)
                      }
                    />
                    <MenuItem
                      icon={Download}
                      label={t('users.export')}
                      onSelect={() => exportData.mutate(account)}
                    />
                    <MenuSeparator />
                    <MenuItem
                      icon={Trash2}
                      label={t('users.erase')}
                      disabled={account.id === me?.id}
                      onSelect={() => setDialog({ type: 'erase', account })}
                    />
                  </ActionsMenu>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <section className="flex flex-col gap-2">
          <h2 className="font-semibold">{t('access.groups')}</h2>
          {accounts.groups.length === 0 ? (
            <p className="text-sm text-muted">{t('users.noGroups')}</p>
          ) : (
            <ul className="divide-y divide-line rounded border border-line">
              {accounts.groups.map((group) => (
                <li key={group.id} className="flex items-center gap-2 px-3 py-2">
                  <span className="min-w-0 flex-1 truncate">{group.name}</span>
                  {group.kept_by && (
                    <span className="hidden truncate text-sm text-muted sm:inline">
                      {group.kept_by}
                    </span>
                  )}
                  <span className="text-sm text-muted">
                    {t('users.members')}: {formatNumber(members(group))}
                  </span>
                  <ActionsMenu>
                    <MenuItem
                      icon={Pencil}
                      label={t('tree.rename')}
                      disabled={!!group.kept_by}
                      onSelect={() => setDialog({ type: 'group', group })}
                    />
                    <MenuSeparator />
                    <MenuItem
                      icon={Trash2}
                      label={t('users.deleteGroup')}
                      disabled={!!group.kept_by}
                      onSelect={() => setDialog({ type: 'deleteGroup', group })}
                    />
                  </ActionsMenu>
                </li>
              ))}
            </ul>
          )}
        </section>
        {[FOLDERS, VAULT].map((kind) => (
          <CompanySection
            key={kind.path}
            kind={kind}
            onEdit={(place) => setDialog({ type: 'company', kind, place })}
            onDelete={(place) => setDialog({ type: 'deleteCompany', kind, place })}
            onFileServer={(place, action) =>
              action === 'refresh'
                ? fileServer.mutate({ place, action })
                : setDialog({ type: 'fileServer', kind, place, action })
            }
          />
        ))}
        <PolicySection />
        <ProvidersSection />
        <OutsidePolicySection />
        <RecoverySection />
      </div>
      {dialog?.type === 'account' && (
        <AccountDialog account={dialog.account} groups={accounts.groups} onClose={close} />
      )}
      {dialog?.type === 'deactivate' && (
        <ConfirmDialog
          heading={t('users.deactivateTitle')}
          confirmLabel={t('users.deactivate')}
          onConfirm={() => deactivate.mutate(dialog.account)}
          onClose={close}
        >
          <strong>{dialog.account.name}</strong> {t('users.deactivateWarning')}
        </ConfirmDialog>
      )}
      {dialog?.type === 'erase' && (
        <EraseDialog account={dialog.account} accounts={accounts.users} onClose={close} />
      )}
      {dialog?.type === 'devices' && <DevicesDialog user={dialog.account} onClose={close} />}
      {dialog?.type === 'company' && (
        <CompanyDialog
          kind={dialog.kind}
          place={dialog.place}
          groups={accounts.groups}
          onClose={close}
        />
      )}
      {dialog?.type === 'deleteCompany' && (
        <ConfirmDialog
          heading={t(dialog.kind.labels.deleteTitle)}
          confirmLabel={t(dialog.kind.labels.delete)}
          onConfirm={() => removeCompany.mutate(dialog)}
          onClose={close}
        >
          <strong>{dialog.place.name}</strong> {t(dialog.kind.labels.deleteWarning)}
        </ConfirmDialog>
      )}
      {dialog?.type === 'fileServer' && (
        <FileServerDialog
          action={dialog.action}
          place={dialog.place}
          touches={dialog.kind.touches}
          onChange={(action) => fileServer.mutate({ place: dialog.place, action })}
          onClose={close}
        />
      )}
      {dialog?.type === 'recover' && <RecoverDialog user={dialog.account} onClose={close} />}
      {dialog?.type === 'group' && (
        <NameDialog
          heading={t(dialog.group ? 'tree.rename' : 'users.newGroup')}
          submitLabel={t(dialog.group ? 'tree.save' : 'tree.create')}
          initial={dialog.group?.name}
          onSubmit={(name) =>
            dialog.group
              ? patchJson(`/api/groups/${dialog.group.id}`, { name })
              : postJson('/api/groups', { name })
          }
          onDone={() => {
            queryClient.invalidateQueries({ queryKey: ['accounts'] });
            queryClient.invalidateQueries({ queryKey: ['people'] });
            close();
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'deleteGroup' && (
        <ConfirmDialog
          heading={t('users.deleteGroupTitle')}
          confirmLabel={t('users.deleteGroup')}
          onConfirm={() => removeGroup.mutate(dialog.group)}
          onClose={close}
        >
          <strong>{dialog.group.name}</strong> {t('users.deleteGroupWarning')}
        </ConfirmDialog>
      )}
    </SettingsFrame>
  );
}

export function UsersPage() {
  const me = useSession().data?.user;
  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getJson<Accounts>('/api/users'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return <Loaded query={accounts}>{(data) => <Directory accounts={data} />}</Loaded>;
}
