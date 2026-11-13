import { useMutation } from '@tanstack/react-query';
import { Download, FileUp, KeyRound } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useSession } from '../auth';
import { useI18n } from '../i18n';
import { keyFrom, madeKey, sealFailure } from '../mailKeys';
import { button, field, primaryButton } from '../styles';
import { useFilePicker } from '../upload';
import { fromBase64 } from './crypto';
import { saved } from './parts';
import type { MailKey } from './secret';

const KEY_FILES = '.p12,.pfx,.asc,.key,.gpg,.pgp';

/** What a mail key is, as the vault shows it beside its name. */
export function MailKeyShown({ mailkey }: { mailkey: MailKey }) {
  const { t, formatDate } = useI18n();
  const expired = mailkey.expires !== null && new Date(mailkey.expires) < new Date();
  const fetched = useMutation({
    mutationFn: async () => {
      const name = mailkey.addresses[0] ?? mailkey.fingerprint;
      if (mailkey.format === 'smime') {
        saved(
          new Blob([fromBase64(mailkey.public[0])], { type: 'application/pkix-cert' }),
          `${name}.cer`,
        );
        return;
      }
      const pgp = await import('../mailPgp');
      const [key] = await pgp.publicKeys(fromBase64(mailkey.public[0]));
      saved(new Blob([key.armor()], { type: 'application/pgp-keys' }), `${name}.asc`);
    },
  });
  return (
    <div className="flex flex-col gap-1 border-b border-line py-2 text-sm">
      <p className="text-xs text-muted">{t(`vault.mailkey.${mailkey.format}`)}</p>
      <p className="break-words">{mailkey.addresses.join(', ')}</p>
      <p className="font-mono text-xs break-all text-muted">{mailkey.fingerprint}</p>
      {mailkey.expires && (
        <p className={`text-xs ${expired ? 'text-danger' : 'text-muted'}`}>
          {t(expired ? 'vault.mailkey.expired' : 'vault.mailkey.expires')}:{' '}
          {formatDate(mailkey.expires)}
        </p>
      )}
      <button
        type="button"
        disabled={fetched.isPending}
        onClick={() => fetched.mutate()}
        className={`${button} mt-1 self-start`}
      >
        <Download size={16} aria-hidden />
        {t('vault.mailkey.public')}
      </button>
      {fetched.isError && <p className="text-danger">{sealFailure(fetched.error, t)}</p>}
    </div>
  );
}

/** A mail key brought from a file or made anew, for a new item of the vault. */
export function MailKeyFields({ onKey }: { onKey: (key: MailKey) => void }) {
  const { t } = useI18n();
  const session = useSession();
  const me = session.data?.user;
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState('');
  const [making, setMaking] = useState(false);
  const [address, setAddress] = useState(me?.email ?? '');
  const picker = useFilePicker(
    ([picked]) => {
      setMaking(false);
      setFile(picked);
    },
    { accept: KEY_FILES, multiple: false },
  );
  const opening = useMutation({
    mutationFn: () => (making ? madeKey(me?.name ?? '', address.trim()) : keyFrom(file!, password)),
    onSuccess: onKey,
  });

  function opened(event: FormEvent) {
    event.preventDefault();
    event.stopPropagation();
    opening.mutate();
  }

  return (
    <div className="flex flex-col gap-2 rounded border border-line p-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={picker.open} className={button}>
          {picker.element}
          <FileUp size={16} aria-hidden />
          {t('vault.mailkey.fromFile')}
        </button>
        <button
          type="button"
          aria-pressed={making}
          onClick={() => {
            setFile(null);
            setMaking(true);
          }}
          className={`${button} aria-pressed:bg-selected`}
        >
          <KeyRound size={16} aria-hidden />
          {t('vault.mailkey.make')}
        </button>
      </div>
      {(file || making) && (
        <div className="flex flex-col gap-2">
          {file && (
            <>
              <p className="truncate">{file.name}</p>
              <label className="flex flex-col gap-1">
                {t('vault.mailkey.password')}
                <input
                  type="password"
                  autoComplete="off"
                  autoFocus
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') opened(event);
                  }}
                  className={field}
                />
              </label>
            </>
          )}
          {making && (
            <label className="flex flex-col gap-1">
              {t('vault.mailkey.address')}
              <input
                type="email"
                autoFocus
                value={address}
                onChange={(event) => setAddress(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') opened(event);
                }}
                className={field}
              />
            </label>
          )}
          <button
            type="button"
            disabled={opening.isPending || (making && !address.trim())}
            onClick={opened}
            className={`${primaryButton} self-start`}
          >
            {t(making ? 'vault.mailkey.create' : 'vault.mailkey.open')}
          </button>
        </div>
      )}
      {opening.isError && <p className="text-danger">{sealFailure(opening.error, t)}</p>}
    </div>
  );
}
