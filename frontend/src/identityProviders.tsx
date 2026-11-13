import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { KeyRound, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { Cancel, Close, ConfirmDialog, Modal, Picker } from './dialogs';
import { useI18n } from './i18n';
import { ActionsMenu, MenuItem, MenuSeparator } from './menu';
import { button, field, primaryButton } from './styles';
import { codeText, errorMessage } from './tree';
import { CopyButton } from './vault/parts';

const KINDS = ['oidc', 'saml', 'ldap', 'scim'] as const;
type Kind = (typeof KINDS)[number];

type FieldName =
  | 'issuer'
  | 'client_id'
  | 'secret'
  | 'scopes'
  | 'groups_claim'
  | 'metadata_url'
  | 'metadata'
  | 'email_attribute'
  | 'groups_attribute'
  | 'url'
  | 'starttls'
  | 'bind_dn'
  | 'base_dn'
  | 'user_filter'
  | 'group_base_dn'
  | 'group_filter'
  | 'sign_in'
  | 'every'
  | 'ca';

interface Setting {
  name: FieldName;
  label?: 'password';
  type: 'text' | 'url' | 'secret' | 'flag' | 'minutes' | 'long';
  required?: boolean;
  advanced?: boolean;
  placeholder?: string;
}

const FIELDS: Record<Kind, Setting[]> = {
  oidc: [
    { name: 'issuer', type: 'url', required: true, placeholder: 'https://' },
    { name: 'client_id', type: 'text' },
    { name: 'secret', type: 'secret' },
    { name: 'scopes', type: 'text', advanced: true, placeholder: 'openid email profile' },
    { name: 'groups_claim', type: 'text', advanced: true, placeholder: 'groups' },
  ],
  saml: [
    { name: 'metadata_url', type: 'url', placeholder: 'https://' },
    { name: 'metadata', type: 'long' },
    { name: 'email_attribute', type: 'text', advanced: true },
    { name: 'groups_attribute', type: 'text', advanced: true },
  ],
  ldap: [
    { name: 'url', type: 'url', required: true, placeholder: 'ldaps://' },
    { name: 'starttls', type: 'flag' },
    { name: 'bind_dn', type: 'text', required: true },
    { name: 'secret', type: 'secret', label: 'password' },
    { name: 'base_dn', type: 'text', required: true },
    { name: 'sign_in', type: 'flag' },
    { name: 'every', type: 'minutes' },
    { name: 'user_filter', type: 'long', advanced: true },
    { name: 'group_base_dn', type: 'text', advanced: true },
    { name: 'group_filter', type: 'long', advanced: true },
    { name: 'email_attribute', type: 'text', advanced: true },
    { name: 'ca', type: 'long', advanced: true },
  ],
  scim: [],
};

/** Read from the provider as the settings are saved, so changed only by giving them anew. */
const GIVEN_AGAIN: FieldName[] = ['secret', 'metadata'];

type Here = 'redirect_uri' | 'entity_id' | 'acs_url' | 'metadata_url' | 'scim_url';

interface Provider {
  id: number;
  name: string;
  kind: Kind;
  enabled: boolean;
  creates: boolean;
  groups: boolean;
  domains: string[];
  settings: Partial<Record<FieldName, string | boolean | number>>;
  certificates: number;
  has_secret: boolean;
  people: number;
  here: Partial<Record<Here, string>>;
  created_at: string;
  synced_at: string | null;
  error: string;
}

interface Made extends Provider {
  token?: string;
}

const PROVIDERS = ['accounts', 'providers'];

type Values = Record<FieldName, string | boolean>;

function valuesOf(provider?: Provider): Values {
  const kept = provider?.settings ?? {};
  const values = {} as Values;
  for (const setting of Object.values(FIELDS).flat()) {
    const value = GIVEN_AGAIN.includes(setting.name) ? undefined : kept[setting.name];
    values[setting.name] =
      setting.type === 'flag' ? value === true : value === undefined ? '' : String(value);
  }
  if (!values.every) values.every = '60';
  return values;
}

/** Whether a provider is first saved off, to learn the addresses it is told before the rest. */
function namedFirst(kind: Kind): boolean {
  return kind === 'oidc' || kind === 'saml';
}

function useProviderChange<V, R = unknown>(mutationFn: (variables: V) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () =>
      Promise.all(
        [PROVIDERS, ['accounts']].map((queryKey) => queryClient.invalidateQueries({ queryKey })),
      ),
  });
}

function Copied({ rows }: { rows: [string, string][] }) {
  const { t } = useI18n();
  return (
    <dl className="flex flex-col gap-2 text-sm">
      {rows.map(([label, value]) => (
        <div key={label} className="flex flex-col gap-1">
          <dt className="text-muted">{label}</dt>
          <dd className="flex items-center gap-2">
            <span className="min-w-0 flex-1 rounded border border-line bg-panel px-2 py-1.5 font-mono break-all select-all">
              {value}
            </span>
            <CopyButton text={value} label={`${t('identity.copy')}: ${label}`} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function HereRows({ provider }: { provider: Provider }) {
  const { t } = useI18n();
  const rows = (Object.entries(provider.here) as [Here, string][]).map(
    ([name, value]) => [t(`sources.here.${name}`), value] as [string, string],
  );
  return rows.length > 0 && <Copied rows={rows} />;
}

function Token({ made }: { made: Made }) {
  const { t } = useI18n();
  return (
    <section aria-label={made.name} className="flex flex-col gap-3">
      <p className="text-sm">{t('sources.tokenOnce')}</p>
      <Copied
        rows={[
          [t('sources.here.scim_url'), made.here.scim_url ?? ''],
          [t('sources.token'), made.token ?? ''],
        ]}
      />
      <div className="flex justify-end">
        <Close />
      </div>
    </section>
  );
}

function SettingField({
  setting,
  value,
  provider,
  onChange,
}: {
  setting: Setting;
  value: string | boolean;
  provider?: Provider;
  onChange: (value: string | boolean) => void;
}) {
  const { t } = useI18n();
  const label = t(`sources.field.${setting.label ?? setting.name}`);
  if (setting.type === 'flag')
    return (
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
        />
        {label}
      </label>
    );
  const placeholder =
    setting.type === 'secret' && provider?.has_secret
      ? t('sources.keepSecret')
      : setting.name === 'metadata' && provider?.certificates
        ? t('sources.keepMetadata')
        : setting.placeholder;
  return (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      {setting.type === 'long' ? (
        <textarea
          rows={3}
          value={String(value)}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          className={`${field} font-mono`}
        />
      ) : (
        <input
          type={
            setting.type === 'secret'
              ? 'password'
              : setting.type === 'minutes'
                ? 'number'
                : setting.type === 'url'
                  ? 'url'
                  : 'text'
          }
          autoComplete={setting.type === 'secret' ? 'new-password' : 'off'}
          required={setting.required}
          min={setting.type === 'minutes' ? 5 : undefined}
          max={setting.type === 'minutes' ? 1440 : undefined}
          value={String(value)}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          className={field}
        />
      )}
    </label>
  );
}

function ProviderDialog({ provider, onClose }: { provider?: Provider; onClose: () => void }) {
  const { t } = useI18n();
  const [current, setCurrent] = useState(provider);
  const [kind, setKind] = useState<Kind>(provider?.kind ?? 'oidc');
  const [name, setName] = useState(provider?.name ?? '');
  const [enabled, setEnabled] = useState(provider?.enabled ?? true);
  const [chosen, setCreates] = useState(provider?.creates);
  const [groups, setGroups] = useState(provider?.groups ?? false);
  const [domains, setDomains] = useState(provider?.domains.join(', ') ?? '');
  const [values, setValues] = useState(() => valuesOf(provider));
  const [token, setToken] = useState<Made | null>(null);
  const creates = chosen ?? kind === 'scim';
  const first = !current && namedFirst(kind);
  const shown = FIELDS[kind].filter(
    (setting) => !first || (setting.required && setting.type !== 'secret'),
  );
  const save = useProviderChange(() => {
    const settings = Object.fromEntries(
      shown
        .filter((setting) => !GIVEN_AGAIN.includes(setting.name) || values[setting.name])
        .map((setting) => [
          setting.name,
          setting.type === 'minutes' ? Number(values[setting.name]) : values[setting.name],
        ]),
    );
    const body = {
      ...settings,
      kind,
      name: name.trim(),
      enabled: first ? false : enabled,
      creates,
      groups,
      domains: domains.split(/[\s,;]+/).filter(Boolean),
    };
    return current
      ? patchJson<Made>(`/api/identity/providers/${current.id}`, body)
      : postJson<Made>('/api/identity/providers', body);
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(undefined, {
      onSuccess: (saved) => {
        if (saved.token) setToken(saved);
        else if (first) {
          setCurrent(saved);
          setEnabled(true);
        } else onClose();
      },
    });
  }

  const flag = (label: string, checked: boolean, onChange: (checked: boolean) => void) => (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
  const listed = (setting: Setting) => (
    <SettingField
      key={setting.name}
      setting={setting}
      value={values[setting.name]}
      provider={current}
      onChange={(value) => setValues({ ...values, [setting.name]: value })}
    />
  );

  return (
    <Modal heading={t(provider ? 'sources.edit' : 'sources.new')} onClose={onClose} wide>
      {token ? (
        <Token made={token} />
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('sources.name')}
            <input
              type="text"
              required
              maxLength={150}
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={field}
            />
          </label>
          {!current && (
            <Picker
              label={t('sources.kind')}
              value={kind}
              options={KINDS.map((each) => [each, t(`sources.kind.${each}`)] as const)}
              onChange={setKind}
            />
          )}
          {current && <HereRows provider={current} />}
          {shown.filter((setting) => !setting.advanced).map(listed)}
          {!first && (
            <>
              <label className="flex flex-col gap-1 text-sm">
                {t('sources.domains')}
                <input
                  type="text"
                  value={domains}
                  placeholder="example.com"
                  onChange={(event) => setDomains(event.target.value)}
                  className={field}
                />
              </label>
              {flag(t('sources.creates'), creates, setCreates)}
              {flag(t('sources.groups'), groups, setGroups)}
              {shown.some((setting) => setting.advanced) && (
                <details className="flex flex-col gap-3">
                  <summary className="cursor-pointer text-sm">{t('sources.advanced')}</summary>
                  <div className="mt-3 flex flex-col gap-3">
                    {shown.filter((setting) => setting.advanced).map(listed)}
                  </div>
                </details>
              )}
              {kind !== 'scim' && flag(t('sources.enabled'), enabled, setEnabled)}
            </>
          )}
          {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
          <div className="flex justify-end gap-2">
            <Cancel />
            <button type="submit" disabled={save.isPending} className={primaryButton}>
              {t(first ? 'sources.next' : current ? 'tree.save' : 'tree.create')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

type Dialog =
  | { type: 'edit'; provider?: Provider }
  | { type: 'token'; provider: Provider }
  | { type: 'delete'; provider: Provider };

/** Where the installation's people sign in and come from besides its own accounts (U1). */
export function ProvidersSection() {
  const { t, formatDate, formatNumber } = useI18n();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const providers = useQuery({
    queryKey: PROVIDERS,
    queryFn: () => getJson<{ providers: Provider[] }>('/api/identity/providers'),
  });
  const synced = useProviderChange((provider: Provider) =>
    postJson(`/api/identity/providers/${provider.id}/sync`),
  );
  const renew = useProviderChange((provider: Provider) =>
    postJson<Made>(`/api/identity/providers/${provider.id}/token`),
  );
  const remove = useProviderChange((provider: Provider) =>
    deleteJson(`/api/identity/providers/${provider.id}`),
  );
  const failure = providers.error ?? synced.error ?? renew.error ?? remove.error;
  const close = () => setDialog(null);

  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <h2 className="flex-1 font-semibold">{t('sources.title')}</h2>
        <button type="button" className={button} onClick={() => setDialog({ type: 'edit' })}>
          <Plus size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('sources.new')}</span>
        </button>
      </div>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {providers.isSuccess &&
        (providers.data.providers.length === 0 ? (
          <p className="text-sm text-muted">{t('sources.none')}</p>
        ) : (
          <ul className="divide-y divide-line rounded border border-line">
            {providers.data.providers.map((provider) => (
              <li key={provider.id} className="flex items-center gap-2 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <p className={`truncate ${provider.enabled ? '' : 'text-muted'}`}>
                    {provider.name}
                  </p>
                  <p className="truncate text-xs text-muted">
                    {[
                      t(`sources.kind.${provider.kind}`),
                      !provider.enabled && t('sources.off'),
                      provider.synced_at &&
                        `${t('sources.synced')}: ${formatDate(provider.synced_at)}`,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                  {provider.error && (
                    <p className="text-xs text-danger">{codeText(provider.error, t)}</p>
                  )}
                </div>
                <span className="text-sm text-muted">
                  {t('sources.people')}: {formatNumber(provider.people)}
                </span>
                <ActionsMenu>
                  <MenuItem
                    icon={Pencil}
                    label={t('sources.edit')}
                    onSelect={() => setDialog({ type: 'edit', provider })}
                  />
                  {(provider.kind === 'ldap' ||
                    (provider.kind === 'saml' && provider.settings.metadata_url)) && (
                    <MenuItem
                      icon={RefreshCw}
                      label={t('sources.sync')}
                      disabled={!provider.enabled}
                      onSelect={() => synced.mutate(provider)}
                    />
                  )}
                  {provider.kind === 'scim' && (
                    <MenuItem
                      icon={KeyRound}
                      label={t('sources.renew')}
                      onSelect={() => setDialog({ type: 'token', provider })}
                    />
                  )}
                  <MenuSeparator />
                  <MenuItem
                    icon={Trash2}
                    label={t('sources.delete')}
                    onSelect={() => setDialog({ type: 'delete', provider })}
                  />
                </ActionsMenu>
              </li>
            ))}
          </ul>
        ))}
      {dialog?.type === 'edit' && <ProviderDialog provider={dialog.provider} onClose={close} />}
      {dialog?.type === 'token' && (
        <ConfirmDialog
          heading={t('sources.renewTitle')}
          confirmLabel={t('sources.renew')}
          onConfirm={() => renew.mutate(dialog.provider)}
          onClose={close}
        >
          <strong>{dialog.provider.name}</strong> {t('sources.renewWarning')}
        </ConfirmDialog>
      )}
      {renew.data && (
        <Modal heading={t('sources.renew')} onClose={() => renew.reset()}>
          <Token made={renew.data} />
        </Modal>
      )}
      {dialog?.type === 'delete' && (
        <ConfirmDialog
          heading={t('sources.deleteTitle')}
          confirmLabel={t('sources.delete')}
          onConfirm={() => remove.mutate(dialog.provider, { onSuccess: close })}
          onClose={close}
        >
          <strong>{dialog.provider.name}</strong> {t('sources.deleteWarning')}
        </ConfirmDialog>
      )}
    </section>
  );
}
