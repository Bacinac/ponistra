import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { ConfirmDialog } from './dialogs';
import { formatSize } from './explorer';
import { useI18n } from './i18n';
import { button, primaryButton } from './styles';
import { codeText, errorMessage } from './tree';

type Why = 'shortcut' | 'google_only' | 'no_download' | 'too_large';
type Kept = 'too_many_cells' | 'too_many_formulas' | 'too_large' | 'newer_file' | 'unreadable';

interface Space {
  folder: string;
  title: string;
  shared: boolean;
  found: {
    files?: number;
    folders?: number;
    bytes?: number;
    copying?: number;
    left?: { id: string; name: string; why: Why }[];
    left_count?: number;
    kept?: [string, Kept][];
  };
  read_at: string | null;
}

/** A Google account's Drive, copied into PONISTRA and followed until its user finishes leaving
    Google (D44). */
export interface Drive {
  id: number;
  state: 'copying' | 'ready';
  error: string;
  finishing: boolean;
  read_at: string | null;
  spaces: Space[];
}

interface Accounts {
  ready: boolean;
  accounts: { account: number; address: string; drive: Drive | null }[];
}

const DRIVE = ['drive'];
// The errors after which the drive waits for its user to sign in to Google again.
const STOPPED = new Set([
  'oauth_login',
  'oauth_client',
  'oauth_refused',
  'mail_lost',
  'drive_scope',
  'drive_disabled',
]);

function useDriveChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (change: () => Promise<unknown>) => change(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DRIVE }),
  });
}

function SpaceLine({ space }: { space: Space }) {
  const { t, formatNumber } = useI18n();
  const found = space.found;
  const left = found.left ?? [];
  const kept = found.kept ?? [];
  return (
    <li className="flex flex-col gap-0.5">
      <Link to={`/f/${space.folder}`} className="truncate text-sm underline">
        {space.title}
        {space.shared && <span className="text-muted"> · {t('drive.shared')}</span>}
      </Link>
      <p className="text-xs text-muted">
        {t('drive.files')}: {formatNumber(found.files ?? found.copying ?? 0)} · {t('drive.folders')}
        : {formatNumber(found.folders ?? 0)} · {formatSize(found.bytes ?? 0, formatNumber)}
      </p>
      {left.length > 0 && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">
            {t('drive.left')}: {formatNumber(found.left_count ?? left.length)}
          </summary>
          <ul className="ms-4 list-disc">
            {left.map((each) => (
              <li key={each.id}>
                {each.name} · {t(`drive.why.${each.why}`)}
              </li>
            ))}
          </ul>
        </details>
      )}
      {kept.length > 0 && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">
            {t('drive.kept')}: {formatNumber(kept.length)}
          </summary>
          <ul className="ms-4 list-disc">
            {kept.map(([name, why]) => (
              <li key={name}>
                {name} · {t(`fileServer.kept.${why}`)}
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

function DriveState({ drive }: { drive: Drive }) {
  const { t, formatDate, formatNumber } = useI18n();
  if (drive.error) return <p className="text-sm text-danger">{codeText(drive.error, t)}</p>;
  let state: string;
  if (drive.finishing) state = t('drive.finishing');
  else if (drive.state === 'copying') {
    const copied = drive.spaces.reduce((sum, each) => sum + (each.found.copying ?? 0), 0);
    state = `${t('drive.copying')}… ${copied ? formatNumber(copied) : ''}`;
  } else state = `${t('drive.ready')} ${drive.read_at ? formatDate(drive.read_at) : ''}`;
  return <p className="text-sm text-muted">{state}</p>;
}

function DriveActions({ address, drive }: { address: string; drive: Drive }) {
  const { t } = useI18n();
  const change = useDriveChange();
  const signIn = useMutation({
    mutationFn: () => postJson<{ url: string }>('/api/mail/oauth/google', { address }),
    onSuccess: ({ url }) => window.location.assign(url),
  });
  const [asking, setAsking] = useState<'finish' | 'stop' | null>(null);
  const stopped = STOPPED.has(drive.error);
  const failure = change.error ?? signIn.error;
  return (
    <>
      <div className="flex flex-wrap gap-2">
        {stopped && (
          <button
            type="button"
            disabled={signIn.isPending || signIn.isSuccess}
            onClick={() => signIn.mutate()}
            className={primaryButton}
          >
            {t('mail.oauthAgain.google')}
          </button>
        )}
        {!drive.finishing && (
          <button
            type="button"
            disabled={change.isPending}
            onClick={() => change.mutate(() => patchJson(`/api/drive/${drive.id}`, {}))}
            className={button}
          >
            {t(stopped ? 'drive.retry' : 'drive.refresh')}
          </button>
        )}
        {!drive.finishing && (
          <button
            type="button"
            disabled={drive.state !== 'ready' || change.isPending}
            onClick={() => setAsking('finish')}
            className={button}
          >
            {t('drive.finish')}
          </button>
        )}
        <button
          type="button"
          disabled={change.isPending}
          onClick={() => setAsking('stop')}
          className={button}
        >
          {t('drive.stop')}
        </button>
      </div>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {asking === 'finish' && (
        <ConfirmDialog
          heading={t('drive.finishTitle')}
          confirmLabel={t('drive.finishAction')}
          onConfirm={() => change.mutate(() => postJson(`/api/drive/${drive.id}/finish`))}
          onClose={() => setAsking(null)}
        >
          {t('drive.finishWarning')}
        </ConfirmDialog>
      )}
      {asking === 'stop' && (
        <ConfirmDialog
          heading={t('drive.stopTitle')}
          confirmLabel={t('drive.stopAction')}
          onConfirm={() => change.mutate(() => deleteJson(`/api/drive/${drive.id}`))}
          onClose={() => setAsking(null)}
        >
          {t('drive.stopWarning')}
        </ConfirmDialog>
      )}
    </>
  );
}

/** The user's Google accounts, each one's Drive taken into PONISTRA on request. */
export function DriveSettings() {
  const { t } = useI18n();
  const found = useQuery({ queryKey: DRIVE, queryFn: () => getJson<Accounts>('/api/drive') });
  const change = useDriveChange();
  if (found.isError) return <p className="text-sm text-danger">{errorMessage(found.error, t)}</p>;
  if (!found.data) return null;
  const { ready, accounts } = found.data;
  if (!accounts.length)
    return (
      <p className="text-sm text-muted">
        {t('drive.none')}{' '}
        <Link to="/settings/mail-accounts" className="underline">
          {t('mail.accounts')}
        </Link>
      </p>
    );
  return (
    <>
      {!ready && <p className="text-sm text-danger">{codeText('oauth_client', t)}</p>}
      {change.isError && <p className="text-sm text-danger">{errorMessage(change.error, t)}</p>}
      <ul className="flex flex-col gap-6">
        {accounts.map(({ account, address, drive }) => (
          <li key={account} className="flex flex-col gap-2">
            <p className="font-medium">{address}</p>
            {drive ? (
              <>
                <DriveState drive={drive} />
                {drive.spaces.length > 0 && (
                  <ul className="flex flex-col gap-2">
                    {drive.spaces.map((space) => (
                      <SpaceLine key={space.folder} space={space} />
                    ))}
                  </ul>
                )}
                <DriveActions address={address} drive={drive} />
              </>
            ) : (
              <button
                type="button"
                disabled={!ready || change.isPending}
                onClick={() => change.mutate(() => postJson('/api/drive', { account }))}
                className={`${primaryButton} self-start`}
              >
                {t('drive.begin')}
              </button>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
