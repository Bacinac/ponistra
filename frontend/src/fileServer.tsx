import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FolderInput,
  KeyRound,
  ListChecks,
  RefreshCw,
  Server,
  Unplug,
  type LucideIcon,
} from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { deleteJson, patchJson, postJson } from './api';
import { Cancel, Close, ConfirmDialog, Modal } from './dialogs';
import { formatSize } from './explorer';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { field, primaryButton } from './styles';
import { codeText, errorMessage } from './tree';

type Why = 'narrower' | 'unreadable' | 'too_long' | 'link' | 'too_large';
type Kept = 'too_many_cells' | 'too_many_formulas' | 'too_large' | 'newer_file' | 'unreadable';

/** A company folder's connection to a folder on a file server of the organisation (D37). */
export interface FileServer {
  address: string;
  mode: 'copy' | 'inbox';
  username: string;
  state: 'reading' | 'read' | 'copying' | 'ready';
  error: string;
  found: {
    files?: number;
    folders?: number;
    bytes?: number;
    free?: number;
    copied?: number;
    taken?: number;
    left?: { path: string; why: Why }[];
    left_count?: number;
    kept?: { path: string; kept: Kept }[];
  };
  moving: boolean;
  read_at: string | null;
}

interface Connectable {
  id: string;
  name: string;
  share?: FileServer | null;
}

export type FileServerAction =
  'connect' | 'inventory' | 'refresh' | 'move' | 'signIn' | 'disconnect';

export const FILE_SERVER_LOOKS: Record<FileServerAction, { icon: LucideIcon; label: MessageKey }> =
  {
    connect: { icon: Server, label: 'fileServer.connect' },
    inventory: { icon: ListChecks, label: 'fileServer.inventory' },
    refresh: { icon: RefreshCw, label: 'fileServer.refresh' },
    move: { icon: FolderInput, label: 'fileServer.move' },
    signIn: { icon: KeyRound, label: 'fileServer.signIn' },
    disconnect: { icon: Unplug, label: 'fileServer.disconnect' },
  };

const path = (place: Connectable) => `/api/company/${place.id}/share`;

export function fileServerActions(share: FileServer | null | undefined): FileServerAction[] {
  if (!share) return ['connect'];
  if (share.mode === 'inbox') return ['refresh', 'signIn', 'disconnect'];
  const movable = (share.state === 'copying' || share.state === 'ready') && !share.moving;
  return [
    ...(share.state === 'reading' ? [] : ['inventory' as const]),
    'refresh',
    ...(movable ? ['move' as const] : []),
    'signIn',
    'disconnect',
  ];
}

function useTouched(touches: string[][]) {
  const queryClient = useQueryClient();
  return () => Promise.all(touches.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

/** What is done at once, its failure shown where the section shows its own. */
export function useFileServerChange(touches: string[][]) {
  const touched = useTouched(touches);
  return useMutation({
    mutationFn: ({ place, action }: { place: Connectable; action: FileServerAction }) => {
      if (action === 'move') return postJson(`${path(place)}/move`);
      if (action === 'disconnect') return deleteJson(path(place));
      return patchJson(path(place), {});
    },
    onSuccess: touched,
  });
}

export function FileServerLine({ share }: { share: FileServer }) {
  const { t, formatDate, formatNumber } = useI18n();
  const found = share.found;
  const left = share.mode === 'copy' && !!found.left_count;
  let state: string;
  if (share.mode === 'inbox')
    state = `${t('fileServer.mode.inbox')} · ${t('fileServer.taken')}: ${formatNumber(found.taken ?? 0)}`;
  else if (share.moving) state = t('fileServer.moving');
  else if (share.state === 'reading') state = t('fileServer.reading');
  else if (share.state === 'read') state = t('fileServer.read');
  else if (share.state === 'copying')
    state = `${t('fileServer.copying')} ${formatNumber(found.copied ?? 0)} / ${formatNumber(found.files ?? 0)}`;
  else state = `${t('fileServer.ready')} ${share.read_at ? formatDate(share.read_at) : ''}`;
  return (
    <p className="truncate text-xs text-muted">
      {share.address} ·{' '}
      {share.error ? <span className="text-danger">{codeText(share.error, t)}</span> : state}
      {left && ` · ${t('fileServer.left')}: ${formatNumber(found.left_count!)}`}
    </p>
  );
}

function SignInDialog({
  place,
  touches,
  onClose,
}: {
  place: Connectable;
  touches: string[][];
  onClose: () => void;
}) {
  const { t } = useI18n();
  const touched = useTouched(touches);
  const share = place.share;
  const [address, setAddress] = useState('');
  const [username, setUsername] = useState(share?.username ?? '');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<FileServer['mode']>('copy');
  const save = useMutation({
    mutationFn: () =>
      share
        ? patchJson(path(place), { username, password })
        : postJson(path(place), { address, username, password, mode }),
    onSuccess: async () => {
      await touched();
      onClose();
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Modal
      heading={`${t(share ? 'fileServer.signInTitle' : 'fileServer.connectTitle')}: ${place.name}`}
      onClose={onClose}
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        {share ? (
          <p className="truncate text-sm text-muted">{share.address}</p>
        ) : (
          <label className="flex flex-col gap-1 text-sm">
            {t('fileServer.address')}
            <input
              required
              maxLength={1000}
              value={address}
              placeholder={t('fileServer.addressExample')}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setAddress(event.target.value)}
              className={field}
            />
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm">
          {t('fileServer.username')}
          <input
            required
            maxLength={320}
            value={username}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setUsername(event.target.value)}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('fileServer.password')}
          <input
            type="password"
            maxLength={1000}
            value={password}
            autoComplete="new-password"
            onChange={(event) => setPassword(event.target.value)}
            className={field}
          />
        </label>
        {!share && (
          <fieldset className="flex flex-col gap-2 text-sm">
            {(['copy', 'inbox'] as const).map((each) => (
              <label key={each} className="flex items-start gap-2">
                <input
                  type="radio"
                  name="mode"
                  checked={mode === each}
                  onChange={() => setMode(each)}
                  className="mt-0.5"
                />
                <span className="flex flex-col">
                  {t(`fileServer.mode.${each}`)}
                  <span className="text-xs text-muted">{t(`fileServer.mode.${each}Note`)}</span>
                </span>
              </label>
            ))}
          </fieldset>
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t(share ? 'tree.save' : 'fileServer.connectAction')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function InventoryDialog({
  place,
  share,
  touches,
  onClose,
}: {
  place: Connectable;
  share: FileServer;
  touches: string[][];
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const touched = useTouched(touches);
  const copy = useMutation({
    mutationFn: () => patchJson(path(place), { copy: true }),
    onSuccess: async () => {
      await touched();
      onClose();
    },
  });
  const found = share.found;
  const left = found.left ?? [];
  const kept = found.kept ?? [];
  const counts: [MessageKey, string][] = [
    ['fileServer.files', formatNumber(found.files ?? 0)],
    ['fileServer.folders', formatNumber(found.folders ?? 0)],
    ['fileServer.size', formatSize(found.bytes ?? 0, formatNumber)],
    ...(share.state === 'read' && found.free !== undefined
      ? [['fileServer.free', formatSize(found.free, formatNumber)] as [MessageKey, string]]
      : []),
  ];

  return (
    <Modal heading={`${t('fileServer.inventoryTitle')}: ${place.name}`} wide onClose={onClose}>
      <p className="truncate text-sm text-muted">{share.address}</p>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {counts.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted">{t(label)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {!!left.length && (
        <section className="flex flex-col gap-1 text-sm">
          <h3 className="font-semibold">{t('fileServer.left')}</h3>
          <ul className="max-h-48 overflow-y-auto rounded border border-line">
            {left.map((each) => (
              <li key={each.path} className="flex gap-2 px-3 py-1">
                <span className="min-w-0 flex-1 truncate">{each.path}</span>
                <span className="shrink-0 text-muted">{t(`fileServer.why.${each.why}`)}</span>
              </li>
            ))}
          </ul>
          {(found.left_count ?? 0) > left.length && (
            <p className="text-muted">
              {t('fileServer.more')} {formatNumber(found.left_count! - left.length)}
            </p>
          )}
        </section>
      )}
      {!!kept.length && (
        <section className="flex flex-col gap-1 text-sm">
          <h3 className="font-semibold">{t('fileServer.kept')}</h3>
          <ul className="max-h-48 overflow-y-auto rounded border border-line">
            {kept.map((each) => (
              <li key={each.path} className="flex gap-2 px-3 py-1">
                <span className="min-w-0 flex-1 truncate">{each.path}</span>
                <span className="shrink-0 text-muted">{t(`fileServer.kept.${each.kept}`)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {copy.isError && <p className="text-sm text-danger">{errorMessage(copy.error, t)}</p>}
      <div className="flex justify-end gap-2">
        <Close />
        {share.state === 'read' && (
          <button
            type="button"
            disabled={copy.isPending}
            onClick={() => copy.mutate()}
            className={primaryButton}
          >
            {t('fileServer.copy')}
          </button>
        )}
      </div>
    </Modal>
  );
}

/** The dialog of an action that asks something first; `onChange` does what needs no more. */
export function FileServerDialog({
  action,
  place,
  touches,
  onChange,
  onClose,
}: {
  action: FileServerAction;
  place: Connectable;
  touches: string[][];
  onChange: (action: FileServerAction) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const share = place.share;
  if (action === 'connect' || action === 'signIn')
    return <SignInDialog place={place} touches={touches} onClose={onClose} />;
  if (!share) return null;
  if (action === 'inventory')
    return <InventoryDialog place={place} share={share} touches={touches} onClose={onClose} />;
  if (action === 'move')
    return (
      <ConfirmDialog
        heading={t('fileServer.moveTitle')}
        confirmLabel={t('fileServer.moveAction')}
        onConfirm={() => onChange('move')}
        onClose={onClose}
      >
        <strong>{place.name}</strong> {t('fileServer.moveWarning')}
      </ConfirmDialog>
    );
  if (action === 'disconnect')
    return (
      <ConfirmDialog
        heading={t('fileServer.disconnectTitle')}
        confirmLabel={t('fileServer.disconnectAction')}
        onConfirm={() => onChange('disconnect')}
        onClose={onClose}
      >
        <strong>{place.name}</strong>{' '}
        {t(share.mode === 'copy' ? 'fileServer.disconnectCopy' : 'fileServer.disconnectInbox')}
      </ConfirmDialog>
    );
  return null;
}
