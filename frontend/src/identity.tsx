import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LogIn, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useLocation } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { useSession } from './auth';
import { Cancel, Close, ConfirmDialog, Modal, Picker } from './dialogs';
import { Loaded, Loading, Lobby, PrimaryAction } from './frame';
import { useI18n } from './i18n';
import { ActionsMenu, MenuItem } from './menu';
import { AdminFrame } from './settings';
import { field, primaryButton } from './styles';
import { errorMessage } from './tree';
import { CopyButton } from './vault/parts';

/** An application that signs its users in with this installation (D38). */
interface Application {
  id: number;
  name: string;
  client_id: string;
  redirect_uris: string[];
  everyone: boolean;
  created_at: string;
  used_at: string | null;
}

interface Made extends Application {
  secret: string;
}

const IDENTITY = ['identity'];
const APPLICATIONS = [...IDENTITY, 'applications'];
const WHO = ['admins', 'everyone'] as const;

type Dialog =
  | { type: 'edit'; application?: Application }
  | { type: 'renew'; application: Application }
  | { type: 'delete'; application: Application };

/** Where an application sends its user to sign in: the request goes to the server as it came, and
    the user, once confirmed where the installation asks for it, back with the code. */
export function AuthorizePage() {
  const { t } = useI18n();
  const { search } = useLocation();
  const user = useSession().data?.user;
  const asked = useQuery({
    queryKey: [...IDENTITY, 'authorize', search],
    queryFn: () => getJson<{ application: string }>(`/api/identity/authorize${search}`),
    retry: false,
  });
  const signIn = useMutation({
    mutationFn: () => postJson<{ redirect: string }>(`/api/identity/authorize${search}`),
    onSuccess: ({ redirect }) => location.replace(redirect),
  });
  const { mutate } = signIn;
  const ready = asked.isSuccess;
  useEffect(() => {
    if (ready) mutate();
  }, [ready, mutate]);
  const failure = asked.error ?? signIn.error;
  return (
    <Lobby>
      <section
        aria-labelledby="authorize"
        className="flex w-full max-w-md flex-col gap-4 rounded-xl bg-raised p-6"
      >
        <h2 id="authorize" className="flex items-center gap-2 text-lg font-semibold">
          <LogIn size={20} aria-hidden className="text-muted" />
          {asked.data
            ? t('identity.signingIn').replace('{application}', asked.data.application)
            : t('identity.title')}
        </h2>
        {user && (
          <p className="text-sm">
            <span className="text-muted">{t('identity.as')}</span> {user.name}
            {user.name !== user.email && <span className="text-muted"> ({user.email})</span>}
          </p>
        )}
        {failure ? <p className="text-danger">{errorMessage(failure, t)}</p> : <Loading />}
        {signIn.isError && (
          <div className="flex justify-end">
            <button type="button" onClick={() => mutate()} className={primaryButton}>
              {t('identity.continue')}
            </button>
          </div>
        )}
      </section>
    </Lobby>
  );
}

function useApplicationChange<V, R = unknown>(mutationFn: (variables: V) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: APPLICATIONS }),
  });
}

function Secret({ made, issuer }: { made: Made; issuer: string }) {
  const { t } = useI18n();
  const rows: [string, string][] = [
    [t('identity.issuer'), issuer],
    [t('identity.clientId'), made.client_id],
    [t('identity.secret'), made.secret],
  ];
  return (
    <section aria-label={made.name} className="flex flex-col gap-3">
      <p className="text-sm">{t('identity.shownOnce')}</p>
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
      <div className="flex justify-end">
        <Close />
      </div>
    </section>
  );
}

function ApplicationDialog({
  application,
  issuer,
  onClose,
}: {
  application?: Application;
  issuer: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(application?.name ?? '');
  const [redirects, setRedirects] = useState(application?.redirect_uris.join('\n') ?? '');
  const [who, setWho] = useState<(typeof WHO)[number]>(
    application?.everyone ? 'everyone' : 'admins',
  );
  const save = useApplicationChange(() => {
    const body = {
      name: name.trim(),
      redirect_uris: redirects.split('\n').map((each) => each.trim()),
      everyone: who === 'everyone',
    };
    return application
      ? patchJson<Application>(`/api/identity/applications/${application.id}`, body)
      : postJson<Made>('/api/identity/applications', body);
  });
  const made = !application && save.data ? (save.data as Made) : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: application ? onClose : undefined });
  }

  return (
    <Modal heading={t(application ? 'identity.edit' : 'identity.new')} onClose={onClose}>
      {made ? (
        <Secret made={made} issuer={issuer} />
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('identity.name')}
            <input
              type="text"
              required
              maxLength={150}
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('identity.redirects')}
            <textarea
              required
              rows={3}
              value={redirects}
              onChange={(event) => setRedirects(event.target.value)}
              className={`${field} font-mono`}
            />
          </label>
          <Picker
            label={t('identity.who')}
            value={who}
            options={WHO.map((each) => [each, t(`identity.who.${each}`)] as const)}
            onChange={setWho}
          />
          {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
          <div className="flex justify-end gap-2">
            <Cancel />
            <button type="submit" disabled={save.isPending} className={primaryButton}>
              {t(application ? 'tree.save' : 'tree.create')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function Applications({ issuer, applications }: { issuer: string; applications: Application[] }) {
  const { t, formatDate } = useI18n();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const remove = useApplicationChange((application: Application) =>
    deleteJson(`/api/identity/applications/${application.id}`),
  );
  const renew = useApplicationChange((application: Application) =>
    postJson<Made>(`/api/identity/applications/${application.id}/secret`),
  );
  const failure = remove.error ?? renew.error;
  const close = () => setDialog(null);
  const cell = 'px-2 py-2 whitespace-nowrap';
  return (
    <AdminFrame
      title={t('identity.title')}
      primary={
        <PrimaryAction
          icon={Plus}
          label={t('identity.new')}
          onClick={() => setDialog({ type: 'edit' })}
        />
      }
    >
      <div className="flex w-full max-w-5xl flex-col gap-4">
        <dl className="flex flex-col gap-1 text-sm">
          <dt className="text-muted">{t('identity.issuer')}</dt>
          <dd className="flex items-center gap-2">
            <span className="min-w-0 font-mono break-all select-all">{issuer}</span>
            <CopyButton text={issuer} label={`${t('identity.copy')}: ${t('identity.issuer')}`} />
          </dd>
        </dl>
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        {applications.length === 0 ? (
          <p className="text-sm text-muted">{t('identity.none')}</p>
        ) : (
          <table className="w-full border-collapse">
            <thead className="text-left text-sm text-muted">
              <tr className="border-b border-line">
                <th className="w-full px-2 py-2 font-normal">{t('identity.name')}</th>
                <th className="hidden px-2 py-2 font-normal sm:table-cell">{t('identity.who')}</th>
                <th className="px-2 py-2 font-normal">{t('identity.used')}</th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody>
              {applications.map((application) => (
                <tr key={application.id} className="border-b border-line">
                  <td className={`${cell} max-w-0`}>
                    <p className="truncate">{application.name}</p>
                    <p className="truncate font-mono text-xs text-muted">
                      {application.redirect_uris.join(', ')}
                    </p>
                  </td>
                  <td className={`${cell} hidden text-sm sm:table-cell`}>
                    {t(`identity.who.${application.everyone ? 'everyone' : 'admins'}`)}
                  </td>
                  <td className={`${cell} text-sm text-muted`}>
                    {application.used_at ? formatDate(application.used_at) : t('users.never')}
                  </td>
                  <td className="pr-2">
                    <ActionsMenu>
                      <MenuItem
                        icon={Pencil}
                        label={t('identity.edit')}
                        onSelect={() => setDialog({ type: 'edit', application })}
                      />
                      <MenuItem
                        icon={RefreshCw}
                        label={t('identity.renew')}
                        onSelect={() => setDialog({ type: 'renew', application })}
                      />
                      <MenuItem
                        icon={Trash2}
                        label={t('identity.delete')}
                        onSelect={() => setDialog({ type: 'delete', application })}
                      />
                    </ActionsMenu>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {dialog?.type === 'edit' && (
        <ApplicationDialog application={dialog.application} issuer={issuer} onClose={close} />
      )}
      {dialog?.type === 'renew' && (
        <ConfirmDialog
          heading={t('identity.renewTitle')}
          confirmLabel={t('identity.renew')}
          onConfirm={() => renew.mutate(dialog.application)}
          onClose={close}
        >
          <strong>{dialog.application.name}</strong> {t('identity.renewWarning')}
        </ConfirmDialog>
      )}
      {renew.data && (
        <Modal heading={t('identity.renew')} onClose={() => renew.reset()}>
          <Secret made={renew.data} issuer={issuer} />
        </Modal>
      )}
      {dialog?.type === 'delete' && (
        <ConfirmDialog
          heading={t('identity.deleteTitle')}
          confirmLabel={t('identity.delete')}
          onConfirm={() => remove.mutate(dialog.application, { onSuccess: close })}
          onClose={close}
        >
          <strong>{dialog.application.name}</strong> {t('identity.deleteWarning')}
        </ConfirmDialog>
      )}
    </AdminFrame>
  );
}

export function ApplicationsPage() {
  const me = useSession().data?.user;
  const applications = useQuery({
    queryKey: APPLICATIONS,
    queryFn: () =>
      getJson<{ issuer: string; applications: Application[] }>('/api/identity/applications'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return (
    <Loaded query={applications}>
      {(data) => <Applications issuer={data.issuer} applications={data.applications} />}
    </Loaded>
  );
}
