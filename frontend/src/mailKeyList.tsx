import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileUp } from 'lucide-react';
import { deleteJson } from './api';
import { useI18n } from './i18n';
import { KEYS, met, sealFailure, useMyKeys } from './mailKeys';
import { RemoveButton } from './mailParts';
import { button } from './styles';
import { useFilePicker } from './upload';
import { fromBase64, type Bytes } from './vault/crypto';

const KEY_FILES = '.asc,.gpg,.pgp,.cer,.crt,.pem,.der';
const PEM = /-----BEGIN CERTIFICATE-----([\s\S]*?)-----END CERTIFICATE-----/g;

/** The keys a file holds for others to encrypt to: OpenPGP public keys or certificates, kept for
    each address they carry. */
async function keptFrom(file: File): Promise<number> {
  const data = new Uint8Array(await file.arrayBuffer()) as Bytes;
  const text = new TextDecoder().decode(data);
  let kept = 0;
  if (text.includes('-----BEGIN PGP') || /\.(gpg|pgp)$/i.test(file.name)) {
    const pgp = await import('./mailPgp');
    for (const key of await pgp.publicKeys(text.includes('-----BEGIN PGP') ? text : data)) {
      const described = await pgp.described(key);
      for (const address of described.addresses) {
        await met('pgp', address, described.fingerprint, described.public, described.expires);
        kept += 1;
      }
    }
    return kept;
  }
  const smime = await import('./mailSmime');
  const certificates = text.includes('-----BEGIN CERTIFICATE-----')
    ? [...text.matchAll(PEM)].map((found) => fromBase64(found[1].replace(/\s+/g, '')))
    : [data];
  for (const der of certificates) {
    const certified = await smime.described(der);
    for (const address of certified.addresses) {
      await met('smime', address, certified.fingerprint, der, certified.notAfter);
      kept += 1;
    }
  }
  return kept;
}

/** The keys the user encrypts mail with: their own published from the vault, and those they met
    on signed messages or brought from a file. */
export function MailKeysSection() {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const keys = useMyKeys();
  const refreshed = () => void queryClient.invalidateQueries({ queryKey: KEYS });
  const brought = useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await keptFrom(file);
    },
    onSettled: refreshed,
  });
  const removed = useMutation({
    mutationFn: (id: number) => deleteJson(`/api/mail/keys/${id}`),
    onSuccess: refreshed,
  });
  const picker = useFilePicker((files) => brought.mutate(files), { accept: KEY_FILES });
  const failure = keys.error ?? brought.error ?? removed.error;
  const row = 'flex min-w-0 items-center gap-2 border-b border-line py-1 pl-2';
  return (
    <section aria-label={t('mail.keys')} className="flex flex-col gap-2">
      <h2 className="font-semibold">{t('mail.keys')}</h2>
      {failure && <p className="text-sm text-danger">{sealFailure(failure, t)}</p>}
      {keys.data?.length === 0 && <p className="text-sm text-muted">{t('mail.keysNone')}</p>}
      {(keys.data?.length ?? 0) > 0 && (
        <ul aria-label={t('mail.keys')} className="flex flex-col">
          {keys.data!.map((key) => (
            <li key={key.id} className={row}>
              <span className="min-w-0 flex-1 truncate">{key.address}</span>
              <span className="truncate text-sm text-muted">
                {t(key.kind === 'smime' ? 'vault.mailkey.smime' : 'vault.mailkey.pgp')}
                {key.own && ` · ${t('mail.keysOwn')}`}
                {key.expires_at &&
                  ` · ${t('vault.mailkey.expires')}: ${formatDate(key.expires_at)}`}
              </span>
              <span className="hidden font-mono text-xs text-muted md:inline">
                {key.fingerprint.slice(-16)}
              </span>
              <RemoveButton
                label={`${t('mail.keysRemove')} ${key.address}`}
                disabled={removed.isPending}
                onClick={() => removed.mutate(key.id)}
              />
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        disabled={brought.isPending}
        onClick={picker.open}
        className={`${button} self-start`}
      >
        {picker.element}
        <FileUp size={16} aria-hidden />
        {t('mail.keysBring')}
      </button>
    </section>
  );
}
