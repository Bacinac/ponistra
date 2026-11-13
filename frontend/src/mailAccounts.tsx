import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronRight } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { ApiError, patchJson, postJson, putJson } from './api';
import { useSession } from './auth';
import { MailEditor } from './MailEditor';
import { mailDoc } from './mailText';
import { Cancel, Labelled, Modal, NumberField } from './dialogs';
import { isMessageKey, useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { button, field, primaryButton } from './styles';
import { errorMessage } from './tree';
import {
  type Account,
  accountName,
  type Accounts,
  ACCOUNTS,
  type Protocol,
  PROTOCOLS,
  type Provider,
  type Security,
  type Server,
  inBox,
  useAccounts,
  useBox,
} from './mailData';

type Kind = 'imap' | 'smtp';

type Known = Pick<Accounts, 'plain' | 'app_passwords' | 'providers' | 'mailboxes'>;

interface Servers {
  protocol: Protocol;
  imap: Server;
  smtp: Server;
  activesync: { host: string };
  username: string;
  /** Microsoft, when the address is one of its people's, whose mail takes no password. */
  signin?: 'microsoft';
}

const SECURITIES: Security[] = ['tls', 'starttls', 'none'];
const PROVIDERS: Provider[] = ['google', 'microsoft'];
const PORTS: Record<Kind, Record<Security, number>> = {
  imap: { tls: 993, starttls: 143, none: 143 },
  smtp: { tls: 465, starttls: 587, none: 587 },
};
const SERVER_ERRORS =
  /^(imap|smtp)_(unreachable|tls|plain)$|^activesync_(unreachable|tls|version)$|^invalid_(imap|smtp|activesync|protocol)$/;

export function accountError(account: Account, t: (key: MessageKey) => string): string {
  const away = account.synced_at && /^(imap|activesync)_unreachable$/.test(account.error);
  const key = away
    ? `error.${account.error.replace('unreachable', 'away')}`
    : `error.${account.error}`;
  return isMessageKey(key) ? t(key) : t('error.unexpected');
}

async function guessed(address: string): Promise<Servers> {
  type Found = Record<Kind, Server & { username: string }> & {
    protocol: Protocol;
    activesync: { host: string; username: string };
    signin?: 'microsoft';
  };
  const found = await postJson<Found>('/api/mail/servers', { address });
  const server = ({ host, port, security }: Server) => ({ host, port, security });
  return {
    protocol: found.protocol,
    imap: server(found.imap),
    smtp: server(found.smtp),
    activesync: { host: found.activesync.host },
    username: (found.protocol === 'activesync' ? found.activesync : found.imap).username,
    signin: found.signin,
  };
}

/** The account's servers as the dialog edits them; an ActiveSync account's unused IMAP and SMTP
    start from the usual ports, should the user switch. */
function accountServers(account: Account): Servers {
  const usual = (kind: Kind, server: Server): Server =>
    server.host ? server : { host: '', port: PORTS[kind].tls, security: 'tls' };
  return {
    protocol: account.protocol,
    imap: usual('imap', account.imap),
    smtp: usual('smtp', account.smtp),
    activesync: account.activesync,
    username: account.username,
  };
}

function ServerFields({
  kind,
  server,
  plain,
  onChange,
}: {
  kind: Kind;
  server: Server;
  plain: string[];
  onChange: (server: Server) => void;
}) {
  const { t } = useI18n();
  const choose = (security: Security) => {
    const usual = Object.values(PORTS[kind]).includes(server.port);
    onChange({ ...server, security, port: usual ? PORTS[kind][security] : server.port });
  };
  return (
    <fieldset className="grid grid-cols-[1fr_7rem] gap-2">
      <legend className="mb-1 text-sm font-semibold">{t(`mail.${kind}`)}</legend>
      <div className="col-span-2">
        <Labelled label={t('mail.host')}>
          {(id) => (
            <input
              id={id}
              required
              value={server.host}
              onChange={(event) => onChange({ ...server, host: event.target.value.trim() })}
              className={field}
            />
          )}
        </Labelled>
      </div>
      <Labelled label={t('mail.security')}>
        {(id) => (
          <select
            id={id}
            value={server.security}
            onChange={(event) => choose(event.target.value as Security)}
            className={field}
          >
            {SECURITIES.map((security) => (
              <option
                key={security}
                value={security}
                disabled={security === 'none' && !plain.includes(server.host.toLowerCase())}
              >
                {t(`mail.security.${security}`)}
              </option>
            ))}
          </select>
        )}
      </Labelled>
      <NumberField
        label={t('mail.port')}
        value={server.port}
        min={1}
        max={65535}
        step={1}
        onChange={(port) => onChange({ ...server, port })}
      />
    </fieldset>
  );
}

function providerOf(known: Known, host: string): Provider | undefined {
  return (Object.keys(known.providers) as Provider[]).find(
    (provider) => known.providers[provider] === host,
  );
}

/** Sends the user to the provider to sign in to the account; the provider sends them back to
    their mail, where the account is then connected. */
function useSignIn() {
  const box = useBox();
  return useMutation({
    mutationFn: ({ provider, address }: { provider: Provider; address?: string }) =>
      postJson<{ url: string }>(inBox(`/api/mail/oauth/${provider}`, box), {
        address: address ?? '',
      }),
    onSuccess: ({ url }) => window.location.assign(url),
  });
}

function SignInAgain({
  provider,
  address,
  switched = false,
}: {
  provider: Provider;
  address: string;
  switched?: boolean;
}) {
  const { t } = useI18n();
  const signIn = useSignIn();
  return (
    <>
      <button
        type="button"
        disabled={signIn.isPending || signIn.isSuccess}
        onClick={() => signIn.mutate({ provider, address })}
        className={`${button} self-start`}
      >
        {t(switched ? `mail.oauthSwitch.${provider}` : `mail.oauthAgain.${provider}`)}
      </button>
      {signIn.isError && <p className="text-sm text-danger">{errorMessage(signIn.error, t)}</p>}
    </>
  );
}

/** The providers a new account signs in through instead of a password; an administrator is
    shown where those not yet set up are entered. */
function Providers({ known, returned }: { known: Known; returned?: string }) {
  const { t } = useI18n();
  const me = useSession().data?.user;
  const signIn = useSignIn();
  const ready = PROVIDERS.filter((provider) => known.providers[provider]);
  const missing = me?.is_admin && ready.length < PROVIDERS.length;
  const failed = returned && `error.${returned}`;
  return (
    <>
      {ready.map((provider) => (
        <button
          key={provider}
          type="button"
          disabled={signIn.isPending || signIn.isSuccess}
          onClick={() => signIn.mutate({ provider })}
          className={button}
        >
          {t(`mail.oauth.${provider}`)}
        </button>
      ))}
      {failed && (
        <p className="text-sm text-danger">
          {isMessageKey(failed) ? t(failed) : t('error.unexpected')}
        </p>
      )}
      {signIn.isError && <p className="text-sm text-danger">{errorMessage(signIn.error, t)}</p>}
      {missing && (
        <p className="text-xs text-muted">
          {t('mail.oauthSetup')}{' '}
          <Link to="/providers" className="text-link underline">
            {t('providers.title')}
          </Link>
        </p>
      )}
      {ready.length > 0 && <p className="text-center text-xs text-muted">{t('mail.oauthOr')}</p>}
    </>
  );
}

/** An account that signs in through OAuth: its name changes here, and its sign-in is renewed at
    the provider. */
export function OAuthAccountDialog({
  account,
  provider,
  onClose,
}: {
  account: Account;
  provider: Provider;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState(account.name);
  const save = useMutation({
    mutationFn: () => patchJson<Account>(`/api/mail/accounts/${account.id}`, { name }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ACCOUNTS });
      onClose();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Modal heading={t('mail.edit')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('mail.address')}>
          {(id) => <input id={id} disabled value={account.address} className={field} />}
        </Labelled>
        <p className="text-sm text-muted">{t(`mail.oauthAccount.${provider}`)}</p>
        <SignInAgain provider={provider} address={account.address} />
        <Labelled label={t('mail.name')}>
          {(id) => (
            <input
              id={id}
              maxLength={150}
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function SignatureDialog({ account, onClose }: { account: Account; onClose: () => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const box = useBox();
  const accounts = useAccounts().data;
  const shared = accounts?.signature ?? '';
  const several = (accounts?.accounts.length ?? 0) > 1;
  const [own, setOwn] = useState(account.own_signature);
  const [written, setWritten] = useState(() => ({
    shared,
    own: account.own_signature ? account.signature : shared,
  }));
  const [initial] = useState(() => ({
    shared: mailDoc(written.shared),
    own: mailDoc(written.own),
  }));
  const scope = own ? 'own' : 'shared';
  const save = useMutation({
    mutationFn: async () => {
      if (own) return patchJson(`/api/mail/accounts/${account.id}`, { signature: written.own });
      await putJson(inBox('/api/mail/signature', box), { html: written.shared });
      if (account.own_signature)
        await patchJson(`/api/mail/accounts/${account.id}`, { signature: null });
    },
    // A message begun at once takes its signature from the accounts as they are then.
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ACCOUNTS });
      onClose();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Modal heading={`${t('mail.signature')}: ${accountName(account)}`} wide onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {(several || account.own_signature) && (
          <div
            role="radiogroup"
            aria-label={t('mail.signature.scope')}
            className="flex flex-col gap-2"
          >
            {(['shared', 'own'] as const).map((each) => (
              <label key={each} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="signature-scope"
                  checked={scope === each}
                  onChange={() => setOwn(each === 'own')}
                  className="size-4"
                />
                {t(`mail.signature.${each}`)}
              </label>
            ))}
          </div>
        )}
        <MailEditor
          key={scope}
          label={t('mail.signature')}
          initial={initial[scope]}
          onChange={(html) => setWritten((before) => ({ ...before, [scope]: html }))}
          rows={6}
          autoFocus
        />
        <p className="text-sm text-muted">{t('mail.signatureHint')}</p>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Connects an account, or changes one: both servers are signed in to before anything is kept,
    and their settings open only when the guess was wrong or the user asks for them. */
export function AccountDialog({
  account,
  known,
  returned,
  onClose,
}: {
  account?: Account;
  known: Known;
  /** Why the provider's sign-in the user came back from did not connect the account. */
  returned?: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const session = useSession();
  const queryClient = useQueryClient();
  const [address, setAddress] = useState(account?.address ?? '');
  const me = session.data?.user;
  const box = useBox();
  const mailbox = known.mailboxes.find((each) => each.id === box);
  const [name, setName] = useState(
    account?.name ?? mailbox?.name ?? (me && me.name !== me.email ? me.name : ''),
  );
  const [password, setPassword] = useState('');
  const [servers, setServers] = useState<Servers | null>(account ? accountServers(account) : null);
  const [open, setOpen] = useState(false);
  const guess = useMutation({ mutationFn: () => guessed(address), onSuccess: setServers });
  const save = useMutation({
    mutationFn: async () => {
      const found = servers ?? (await guess.mutateAsync());
      if (found.signin && !account) return null;
      const sent = { address, name, password, ...found };
      return account
        ? patchJson<Account>(`/api/mail/accounts/${account.id}`, sent)
        : postJson<Account>(inBox('/api/mail/accounts', box), sent);
    },
    onSuccess: (saved) => {
      if (!saved) return;
      void queryClient.invalidateQueries({ queryKey: ACCOUNTS });
      onClose();
    },
    onError: (error) => {
      if (error instanceof ApiError && SERVER_ERRORS.test(error.code ?? '')) setOpen(true);
    },
  });
  const failure = save.error ?? guess.error;
  const appPasswords =
    servers?.protocol === 'imap' ? known.app_passwords[servers.imap.host] : undefined;
  const switchable = account && providerOf(known, account.imap.host);
  const signsIn = !account && servers?.signin === 'microsoft';

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Modal heading={t(account ? 'mail.edit' : 'mail.connectTitle')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {!account && <p className="text-sm text-muted">{t('mail.connectNote')}</p>}
        {!account && <Providers known={known} returned={returned} />}
        <Labelled label={t('mail.address')}>
          {(id) => (
            <input
              id={id}
              type="email"
              required
              disabled={Boolean(account)}
              value={address}
              onChange={(event) => {
                setAddress(event.target.value);
                if (!open) setServers(null);
              }}
              onBlur={() => {
                if (!servers && !guess.isPending && address.includes('@')) guess.mutate();
              }}
              className={field}
            />
          )}
        </Labelled>
        {signsIn ? (
          <p className="text-sm text-muted">
            {t(known.providers.microsoft ? 'mail.signInOnly' : 'mail.signInOnlyMissing')}
          </p>
        ) : (
          <>
            <Labelled label={t(appPasswords ? 'mail.appPassword' : 'mail.password')}>
              {(id) => (
                <input
                  id={id}
                  type="password"
                  required={!account}
                  autoComplete="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className={field}
                />
              )}
            </Labelled>
            {appPasswords && (
              <p className="-mt-2 text-xs text-muted">
                {t('mail.appPasswordNote')}{' '}
                <a
                  href={appPasswords}
                  target="_blank"
                  rel="noreferrer"
                  className="text-link underline"
                >
                  {t('mail.appPasswordMake')}
                </a>
              </p>
            )}
            {account && <p className="-mt-2 text-xs text-muted">{t('mail.passwordKept')}</p>}
            {switchable && <SignInAgain provider={switchable} address={account.address} switched />}
            <Labelled label={t('mail.name')}>
              {(id) => (
                <input
                  id={id}
                  maxLength={150}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className={field}
                />
              )}
            </Labelled>
            <button
              type="button"
              aria-expanded={open && Boolean(servers)}
              disabled={guess.isPending}
              onClick={() => {
                if (!servers) guess.mutate(undefined, { onSuccess: () => setOpen(true) });
                else setOpen(!open);
              }}
              className="flex items-center gap-1 self-start rounded text-sm text-link hover:underline"
            >
              <ChevronRight size={16} aria-hidden className={open && servers ? 'rotate-90' : ''} />
              {t('mail.servers')}
            </button>
            {open && servers && (
              <>
                <Labelled label={t('mail.protocol')}>
                  {(id) => (
                    <select
                      id={id}
                      value={servers.protocol}
                      onChange={(event) =>
                        setServers({ ...servers, protocol: event.target.value as Protocol })
                      }
                      className={field}
                    >
                      {PROTOCOLS.map((protocol) => (
                        <option key={protocol} value={protocol}>
                          {t(`mail.protocol.${protocol}`)}
                        </option>
                      ))}
                    </select>
                  )}
                </Labelled>
                <Labelled label={t('mail.username')}>
                  {(id) => (
                    <input
                      id={id}
                      required
                      value={servers.username}
                      onChange={(event) => setServers({ ...servers, username: event.target.value })}
                      className={field}
                    />
                  )}
                </Labelled>
                {servers.protocol === 'activesync' ? (
                  <Labelled label={t('mail.activesync')}>
                    {(id) => (
                      <input
                        id={id}
                        required
                        value={servers.activesync.host}
                        onChange={(event) =>
                          setServers({
                            ...servers,
                            activesync: { host: event.target.value.trim() },
                          })
                        }
                        className={field}
                      />
                    )}
                  </Labelled>
                ) : (
                  (['imap', 'smtp'] as const).map((kind) => (
                    <ServerFields
                      key={kind}
                      kind={kind}
                      server={servers[kind]}
                      plain={known.plain}
                      onChange={(server) => setServers({ ...servers, [kind]: server })}
                    />
                  ))
                )}
              </>
            )}
          </>
        )}
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          {!signsIn && (
            <button type="submit" disabled={save.isPending} className={primaryButton}>
              {t(save.isPending ? 'mail.checking' : account ? 'tree.save' : 'mail.connect')}
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}
