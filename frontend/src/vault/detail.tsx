import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, FolderInput, History, Paperclip, Pencil, Trash2, X } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { deleteJson, getBytes, postJson, upload } from '../api';
import { useI18n } from '../i18n';
import { ActionsMenu, MenuItem, MenuSeparator } from '../menu';
import { button, iconButton } from '../styles';
import { covers, errorMessage } from '../tree';
import { useFilePicker } from '../upload';
import { open, seal, type Bytes } from './crypto';
import { MailKeyShown } from './mailKey';
import { CopyButton, KIND_ICONS, RevealButton, saved } from './parts';
import { sealJson, type Opened } from './secret';
import { COLLECTIONS, OPENED, type Collection } from './state';
import { parseTotp, totpCode, totpLeft } from './totp';

function useSeen(item: Opened, collection: Collection) {
  return useMutation({
    mutationFn: (field: 'password' | 'totp') =>
      collection.kind === 'personal'
        ? Promise.resolve()
        : postJson(`/api/vault/items/${item.id}/seen`, { field }),
  });
}

function Field({
  label,
  children,
  actions,
}: {
  label: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 border-b border-line py-2">
      <div className="min-w-0 flex-1">
        <p className="text-xs text-muted">{label}</p>
        <div className="min-w-0 text-sm break-words">{children}</div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-0.5">{actions}</div>}
    </div>
  );
}

function OneTime({ secret, onSeen }: { secret: string; onSeen: () => void }) {
  const { t } = useI18n();
  const totp = useMemo(() => parseTotp(secret), [secret]);
  const [now, setNow] = useState(() => Date.now());
  const [code, setCode] = useState('');
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const step = totp ? Math.floor(now / 1000 / totp.period) : 0;
  useEffect(() => {
    if (totp) void totpCode(totp, step * totp.period * 1000).then(setCode);
  }, [totp, step]);
  if (!totp) {
    return (
      <Field label={t('vault.totp')}>
        <span className="text-danger">{t('vault.totpInvalid')}</span>
      </Field>
    );
  }
  const half = Math.ceil(code.length / 2);
  return (
    <Field
      label={t('vault.totp')}
      actions={
        <>
          <span className="text-xs text-muted tabular-nums" aria-label={t('vault.totpLeft')}>
            {totpLeft(totp, now)} s
          </span>
          <CopyButton text={code} label={t('vault.copyTotp')} onCopied={onSeen} />
        </>
      }
    >
      <span className="font-mono text-lg tracking-wider tabular-nums">
        {code.slice(0, half)} {code.slice(half)}
      </span>
    </Field>
  );
}

export function Detail({
  item,
  collection,
  movable,
  onEdit,
  onMove,
}: {
  item: Opened;
  collection: Collection;
  movable: boolean;
  onEdit: () => void;
  onMove: () => void;
}) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const seen = useSeen(item, collection);
  const [shown, setShown] = useState(false);
  const [history, setHistory] = useState(false);
  const { secret } = item;
  const { search } = useLocation();
  const editable = covers(collection.role, 'edit');
  const toTrash = useMutation({
    mutationFn: () => deleteJson(`/api/vault/items/${item.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: OPENED });
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
      navigate(`/vault/${collection.id}${search}`);
    },
  });
  const failure = seen.error ?? toTrash.error;
  const Icon = KIND_ICONS[secret.kind];

  return (
    <article
      aria-label={secret.name}
      className="flex min-w-0 flex-1 flex-col gap-1 overflow-y-auto rounded-lg lg:border lg:border-line lg:p-4"
    >
      <div className="flex items-center gap-2">
        <Link
          to={`/vault/${collection.id}`}
          aria-label={t('frame.close')}
          className={`${iconButton} lg:hidden`}
        >
          <X size={16} aria-hidden />
        </Link>
        <Icon size={20} aria-hidden className="shrink-0 text-muted" />
        <h2 className="min-w-0 flex-1 truncate text-lg font-semibold">{secret.name}</h2>
        {editable && (
          <>
            <button type="button" onClick={onEdit} className={button}>
              <Pencil size={16} aria-hidden />
              {t('vault.edit')}
            </button>
            <ActionsMenu>
              <MenuItem
                icon={FolderInput}
                label={t('tree.move')}
                disabled={!movable}
                onSelect={onMove}
              />
              <MenuSeparator />
              <MenuItem icon={Trash2} label={t('tree.toTrash')} onSelect={() => toTrash.mutate()} />
            </ActionsMenu>
          </>
        )}
      </div>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {secret.kind === 'login' && (
        <>
          {secret.username && (
            <Field
              label={t('vault.username')}
              actions={<CopyButton text={secret.username} label={t('vault.copyUsername')} />}
            >
              {secret.username}
            </Field>
          )}
          {secret.password && (
            <Field
              label={t('vault.password')}
              actions={
                <>
                  <RevealButton
                    shown={shown}
                    onToggle={() => {
                      if (!shown) seen.mutate('password');
                      setShown(!shown);
                    }}
                  />
                  <CopyButton
                    text={secret.password}
                    label={t('vault.copyPassword')}
                    onCopied={() => seen.mutate('password')}
                  />
                </>
              }
            >
              <span className="font-mono">{shown ? secret.password : '••••••••••••'}</span>
            </Field>
          )}
          {secret.totp && <OneTime secret={secret.totp} onSeen={() => seen.mutate('totp')} />}
          {secret.urls.map((url, index) => (
            <Field
              key={index}
              label={t('vault.url')}
              actions={
                <a
                  href={url.includes('://') ? url : `https://${url}`}
                  target="_blank"
                  rel="noreferrer noopener"
                  aria-label={t('vault.openUrl')}
                  title={t('vault.openUrl')}
                  className={iconButton}
                >
                  <ExternalLink size={16} aria-hidden />
                </a>
              }
            >
              {url}
            </Field>
          ))}
        </>
      )}
      {secret.kind === 'mailkey' && secret.mailkey && <MailKeyShown mailkey={secret.mailkey} />}
      {secret.notes && (
        <Field label={t('vault.notes')}>
          <p className="whitespace-pre-wrap">{secret.notes}</p>
        </Field>
      )}
      <Attachments item={item} editable={editable} />
      {secret.history.length > 0 && (
        <div className="py-2">
          <button
            type="button"
            aria-expanded={history}
            onClick={() => setHistory(!history)}
            className="flex items-center gap-2 text-sm text-muted hover:text-ink"
          >
            <History size={16} aria-hidden />
            {t('vault.history')}
          </button>
          {history && (
            <ul className="mt-1 flex flex-col">
              {secret.history.map((entry, index) => (
                <li key={index} className="flex items-center gap-2 py-1 text-sm">
                  <span className="min-w-0 flex-1 truncate font-mono">{entry.password}</span>
                  <span className="text-xs text-muted">{formatDate(entry.until)}</span>
                  <CopyButton
                    text={entry.password}
                    label={t('vault.copyPassword')}
                    onCopied={() => seen.mutate('password')}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <p className="pt-2 text-xs text-muted">
        {t('vault.changed')}: {formatDate(item.updated_at)}
        {item.updated_by && ` · ${item.updated_by.name}`}
      </p>
    </article>
  );
}

function Attachments({ item, editable }: { item: Opened; editable: boolean }) {
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const refreshed = () => void queryClient.invalidateQueries({ queryKey: OPENED });
  const add = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) {
        const sealed = await seal(item.key, new Uint8Array(await file.arrayBuffer()));
        const stored = await upload(new Blob([sealed]));
        await postJson(`/api/vault/items/${item.id}/attachments`, {
          blob: stored.sha256,
          meta: await sealJson(item.key, { name: file.name, type: file.type }),
        });
      }
    },
    onSettled: refreshed,
  });
  const picker = useFilePicker((files) => add.mutate(files), { accept: '' });
  const fetched = useMutation({
    mutationFn: async (attachment: Opened['attachments'][number]) => {
      const sealed = (await getBytes(`/api/vault/attachments/${attachment.id}`)) as Bytes;
      const plain = await open(item.key, sealed);
      saved(new Blob([plain], { type: attachment.type }), attachment.name);
    },
  });
  const removed = useMutation({
    mutationFn: (id: string) => deleteJson(`/api/vault/attachments/${id}`),
    onSuccess: refreshed,
  });
  const failure = add.error ?? fetched.error ?? removed.error;
  if (!editable && item.attachments.length === 0) return null;
  return (
    <div className="flex flex-col gap-1 py-2">
      <p className="text-xs text-muted">{t('vault.attachments')}</p>
      {item.attachments.map((attachment) => (
        <div key={attachment.id} className="flex items-center gap-2 text-sm">
          <Paperclip size={14} aria-hidden className="shrink-0 text-muted" />
          <button
            type="button"
            onClick={() => fetched.mutate(attachment)}
            className="min-w-0 flex-1 truncate text-left hover:underline"
          >
            {attachment.name}
          </button>
          <span className="text-xs text-muted tabular-nums">
            {formatNumber(Math.max(1, Math.round(attachment.size / 1024)))} kB
          </span>
          {editable && (
            <button
              type="button"
              aria-label={t('vault.removeAttachment')}
              title={t('vault.removeAttachment')}
              onClick={() => removed.mutate(attachment.id)}
              className={iconButton}
            >
              <X size={14} aria-hidden />
            </button>
          )}
        </div>
      ))}
      {editable && (
        <button
          type="button"
          disabled={add.isPending}
          onClick={picker.open}
          className={`${button} self-start`}
        >
          {picker.element}
          <Paperclip size={16} aria-hidden />
          {t(add.isPending ? 'vault.attaching' : 'vault.attach')}
        </button>
      )}
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
    </div>
  );
}
