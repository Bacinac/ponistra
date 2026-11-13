import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BookUser,
  CalendarDays,
  Inbox,
  type LucideIcon,
  Pencil,
  Share2,
  Trash2,
  Users,
} from 'lucide-react';
import { type ReactNode, useState } from 'react';
import { Link } from 'react-router';
import { AddGrant } from './access';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { ConfirmDialog, Modal, NameDialog } from './dialogs';
import { Loading } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { BoxContext, type Mailbox, useAccounts, useBox } from './mailData';
import { RemoveButton } from './mailParts';
import { ContextMenuArea, MenuItem } from './menu';
import { Badge, granteeName } from './people';
import { useMenuPress } from './press';
import { button, sideRow } from './styles';
import { errorMessage, type Grantee, type Role } from './tree';

const ROLES: Role[] = ['read', 'edit', 'own'];

interface MailGrant {
  id: number;
  role: Role;
  grantee: Grantee;
}

/** The pages a shared mailbox has its own of: its mail, its calendars and its contacts. */
const PAGES: Record<'mail' | 'calendar' | 'contacts', { own: MessageKey; icon: LucideIcon }> = {
  mail: { own: 'mail.mailboxOwn', icon: Inbox },
  calendar: { own: 'calendar.mailboxOwn', icon: CalendarDays },
  contacts: { own: 'contacts.mailboxOwn', icon: BookUser },
};

/** The shared mailboxes beside the user's own mail, calendars or contacts, the one shown
    marked. */
export function MailboxLinks({
  mailboxes,
  box,
  page = 'mail',
}: {
  mailboxes: Mailbox[];
  box: number | null;
  page?: keyof typeof PAGES;
}) {
  const { t, formatNumber } = useI18n();
  if (mailboxes.length === 0) return null;
  const { own, icon: Own } = PAGES[page];
  return (
    <section aria-label={t('mail.mailboxes')} className="flex flex-col gap-0.5">
      <h2 className="px-2 text-xs font-semibold text-muted">{t('mail.mailboxes')}</h2>
      {box !== null && (
        <Link to={`/${page}`} className={sideRow}>
          <Own size={16} aria-hidden className="shrink-0 text-muted" />
          <span className="min-w-0 flex-1 truncate">{t(own)}</span>
        </Link>
      )}
      {mailboxes.map((mailbox) => (
        <Link
          key={mailbox.id}
          to={`/${page}?box=${mailbox.id}`}
          aria-current={mailbox.id === box ? 'page' : undefined}
          className={sideRow}
        >
          <Users size={16} aria-hidden className="shrink-0 text-muted" />
          <span className="min-w-0 flex-1 truncate">{mailbox.name}</span>
          {page === 'mail' && mailbox.unseen > 0 && (
            <span className="text-xs font-semibold tabular-nums">
              {formatNumber(mailbox.unseen)}
            </span>
          )}
        </Link>
      ))}
    </section>
  );
}

/** The shared mailboxes beside the calendars or the contacts of the one the page shows. */
export function BoxLinks({ page }: { page: 'calendar' | 'contacts' }) {
  const box = useBox();
  const mailboxes = useQuery({
    queryKey: ['mail', 'mailboxes'],
    queryFn: () => getJson<{ mailboxes: Mailbox[] }>('/api/mail/mailboxes'),
    select: (data) => data.mailboxes,
  });
  return <MailboxLinks mailboxes={mailboxes.data ?? []} box={box} page={page} />;
}

function useMailboxChange<V>(mutationFn: (variables: V) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['mail'] }),
  });
}

function SharingDialog({ mailbox, onClose }: { mailbox: Mailbox; onClose: () => void }) {
  const { t } = useI18n();
  const path = `/api/mail/mailboxes/${mailbox.id}/grants`;
  const grants = useQuery({
    queryKey: ['mail', 'grants', mailbox.id],
    queryFn: () => getJson<{ grants: MailGrant[] }>(path),
    select: (data) => data.grants,
  });
  const give = useMailboxChange((grant: { kind: Grantee['kind']; id: number | null; role: Role }) =>
    postJson(path, grant),
  );
  const take = useMailboxChange((id: number) => deleteJson(`${path}/${id}`));
  const failure = grants.error ?? give.error ?? take.error;
  return (
    <Modal heading={`${t('mail.mailboxShare')} ${mailbox.name}`} onClose={onClose}>
      <AddGrant onAdd={(grantee, role) => give.mutate({ ...grantee, role })} />
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {grants.isPending ? (
        <Loading />
      ) : (
        <ul aria-label={t('mail.mailboxShare')} className="flex flex-col gap-2">
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

function MailboxRow({ mailbox, children }: { mailbox: Mailbox; children: ReactNode }) {
  const { t } = useI18n();
  const press = useMenuPress();
  const [dialog, setDialog] = useState<'share' | 'rename' | 'remove' | null>(null);
  const remove = useMailboxChange(() => deleteJson(`/api/mail/mailboxes/${mailbox.id}`));
  const owner = mailbox.role === 'own';
  const close = () => setDialog(null);
  const heading = 'flex items-center gap-2 font-semibold';
  const title = (
    <>
      <Users size={16} aria-hidden className="shrink-0 text-muted" />
      <span className="min-w-0 flex-1 truncate">{mailbox.name}</span>
      <span className="text-sm font-normal text-muted">{t(`access.role.${mailbox.role}`)}</span>
    </>
  );
  return (
    <section aria-label={mailbox.name} className="flex flex-col gap-2">
      {owner ? (
        <ContextMenuArea
          items={
            <>
              <MenuItem
                icon={Share2}
                label={t('mail.mailboxShare')}
                onSelect={() => setDialog('share')}
              />
              <MenuItem
                icon={Pencil}
                label={t('tree.rename')}
                onSelect={() => setDialog('rename')}
              />
              <MenuItem
                icon={Trash2}
                label={t('mail.mailboxRemove')}
                onSelect={() => setDialog('remove')}
              />
            </>
          }
        >
          <h3 {...press} className={`${heading} select-none [-webkit-touch-callout:none]`}>
            {title}
          </h3>
        </ContextMenuArea>
      ) : (
        <h3 className={heading}>{title}</h3>
      )}
      {remove.isError && <p className="text-sm text-danger">{errorMessage(remove.error, t)}</p>}
      {owner && children}
      {dialog === 'share' && <SharingDialog mailbox={mailbox} onClose={close} />}
      {dialog === 'rename' && (
        <NameDialog
          heading={t('tree.rename')}
          submitLabel={t('tree.save')}
          initial={mailbox.name}
          onSubmit={(name) => patchJson(`/api/mail/mailboxes/${mailbox.id}`, { name })}
          onDone={close}
          onClose={close}
        />
      )}
      {dialog === 'remove' && (
        <ConfirmDialog
          heading={t('mail.mailboxRemoveTitle')}
          confirmLabel={t('mail.mailboxRemove')}
          onConfirm={() => remove.mutate(undefined, { onSuccess: close })}
          onClose={close}
        >
          <strong>{mailbox.name}</strong> {t('mail.mailboxRemoveWarning')}
        </ConfirmDialog>
      )}
    </section>
  );
}

/** The shared mailboxes the user reaches, in the settings: a new one, and for those they own,
    whom it is shared with and its accounts, which `accounts` lists in the mailbox. */
export function Mailboxes({ accounts }: { accounts: () => ReactNode }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const listed = useAccounts();
  const [making, setMaking] = useState(false);
  if (!listed.data) return listed.isError ? null : <Loading />;
  return (
    <section aria-label={t('mail.mailboxes')} className="flex flex-col gap-4">
      <h2 className="font-semibold">{t('mail.mailboxes')}</h2>
      {listed.data.mailboxes.map((mailbox) => (
        <BoxContext key={mailbox.id} value={mailbox.id}>
          <MailboxRow mailbox={mailbox}>{accounts()}</MailboxRow>
        </BoxContext>
      ))}
      <div>
        <button type="button" onClick={() => setMaking(true)} className={button}>
          <Users size={16} aria-hidden />
          {t('mail.mailboxNew')}
        </button>
      </div>
      {making && (
        <NameDialog
          heading={t('mail.mailboxNew')}
          submitLabel={t('mail.mailboxMake')}
          onSubmit={(name) => postJson<Mailbox>('/api/mail/mailboxes', { name })}
          onDone={() => {
            setMaking(false);
            void queryClient.invalidateQueries({ queryKey: ['mail'] });
          }}
          onClose={() => setMaking(false)}
        />
      )}
    </section>
  );
}
