import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import {
  Lock,
  Paperclip,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  type LucideIcon,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { getJson, postBytes } from './api';
import { formatSize } from './explorer';
import { useI18n } from './i18n';
import type { Opened } from './mail';
import { HtmlBody } from './mailBody';
import { met, sealFailure, smimeKey, useMailKeys, type KnownKey } from './mailKeys';
import { PlainBody } from './plain';
import { fromBase64, type Bytes } from './vault/crypto';
import { saved } from './vault/parts';
import type { MailKey } from './vault/secret';
import { useVault, useVaultData } from './vault/state';
import { UnlockForm } from './vault/unlock';

/** One seal of a message as the server finds it (`sealing.Layer`), its bytes in base64. */
interface Layer {
  kind: 'smime' | 'pgp';
  how: 'signed' | 'encrypted';
  inline: boolean;
  content: string | null;
  signature: string | null;
  data: string | null;
}

export interface OpenedFile {
  part: string;
  name: string;
  type: string;
  data: string;
}

interface Shown {
  html: string | null;
  text: string | null;
  remote: boolean;
  files: OpenedFile[];
}

type Status = 'valid' | 'changed' | 'mismatch' | 'expired' | 'invalid' | 'unknown';

interface Signed {
  status: Status;
  /** Who signed, by the address the key names. */
  address: string | null;
  /** The key that signed, kept for the sender's address once the user accepts it. */
  key: Parameters<typeof met> | null;
}

/** What the browser read of a sealed message: whether it was encrypted, who signed it, and the
    message itself where the server could not show it. */
export interface Unsealed {
  encrypted: boolean;
  signed: Signed | null;
  shown: Shown | null;
}

const DEEPEST = 4;

const STATUS_ICONS: Record<Status, LucideIcon> = {
  valid: ShieldCheck,
  changed: ShieldAlert,
  mismatch: ShieldAlert,
  expired: ShieldAlert,
  invalid: ShieldAlert,
  unknown: ShieldQuestion,
};

function bytesOf(given: string | null): Bytes {
  return fromBase64(given ?? '');
}

/** The key an Autocrypt header carries for the address it names. */
function autocrypted(header: string | null, sender: string): Bytes | null {
  if (!header) return null;
  const fields = new Map(
    header.split(';').map((field) => {
      const at = field.indexOf('=');
      return [field.slice(0, at).trim().toLowerCase(), field.slice(at + 1).trim()] as const;
    }),
  );
  if (fields.get('addr')?.toLowerCase() !== sender) return null;
  const data = fields.get('keydata')?.replace(/\s+/g, '');
  try {
    return data ? fromBase64(data) : null;
  } catch {
    return null;
  }
}

async function openedWithAny<T>(
  keys: MailKey[],
  open: (key: MailKey) => Promise<T>,
  notForMe: string,
): Promise<T> {
  let failure: unknown = null;
  for (const key of keys) {
    try {
      return await open(key);
    } catch (error) {
      if (!(error instanceof Error) || error.message !== notForMe) failure ??= error;
    }
  }
  throw failure ?? new Error(notForMe);
}

/** A signer judged by the keys already known for the sender (trust on first use): the first key
    seen for an address is kept, a different one later is told. */
async function judged(
  kind: 'smime' | 'pgp',
  sender: string,
  known: KnownKey[],
  signer: { fingerprint: string; addresses: string[]; data: Bytes; expires: string | null },
): Promise<Signed> {
  const key: Signed['key'] = [kind, sender, signer.fingerprint, signer.data, signer.expires];
  const address = signer.addresses.includes(sender) ? sender : (signer.addresses[0] ?? null);
  if (address !== sender) return { status: 'mismatch', address, key: null };
  const held = known.filter((each) => each.kind === kind && each.address === sender);
  const fingerprint = signer.fingerprint.toLowerCase();
  if (held.length > 0 && !held.some((each) => each.fingerprint === fingerprint)) {
    return { status: 'changed', address, key };
  }
  await met(...key);
  return { status: 'valid', address, key: null };
}

async function smimeSigned(
  signature: Bytes,
  content: Bytes | null,
  sender: string,
  known: KnownKey[],
): Promise<{ signed: Signed; content: Bytes }> {
  const smime = await import('./mailSmime');
  const checked = await smime.checked(signature, content);
  if (!checked.valid || !checked.signer) {
    return { signed: { status: 'invalid', address: null, key: null }, content: checked.content };
  }
  const certified = await smime.described(checked.signer);
  const when = checked.signedAt ? new Date(checked.signedAt) : new Date();
  if (new Date(certified.notAfter) < when || new Date(certified.notBefore) > when) {
    return {
      signed: { status: 'expired', address: certified.addresses[0] ?? null, key: null },
      content: checked.content,
    };
  }
  const signed = await judged('smime', sender, known, {
    fingerprint: certified.fingerprint,
    addresses: certified.addresses,
    data: checked.signer,
    expires: certified.notAfter,
  });
  return { signed, content: checked.content };
}

async function pgpKeys(known: KnownKey[], sender: string, autocrypt: Bytes | null) {
  const pgp = await import('./mailPgp');
  const held = known.filter((each) => each.kind === 'pgp' && each.address === sender);
  const keys = (await Promise.all(held.map((each) => pgp.publicKeys(bytesOf(each.data))))).flat();
  const offered = autocrypt ? await pgp.publicKeys(autocrypt).catch(() => []) : [];
  return [...keys, ...offered];
}

async function pgpSigned(
  checked: { valid: boolean; signer: string | null },
  sender: string,
  known: KnownKey[],
  autocrypt: Bytes | null,
): Promise<Signed> {
  if (!checked.signer) return { status: 'unknown', address: null, key: null };
  if (!checked.valid) return { status: 'invalid', address: null, key: null };
  const pgp = await import('./mailPgp');
  const keys = await pgpKeys(known, sender, autocrypt);
  const key = keys.find((each) => each.getFingerprint() === checked.signer)!;
  const described = await pgp.described(key);
  return judged('pgp', sender, known, {
    fingerprint: described.fingerprint,
    addresses: described.addresses,
    data: described.public,
    expires: described.expires,
  });
}

async function unsealed(message: Opened, keys: MailKey[]): Promise<Unsealed> {
  const sender = (message.sender.address ?? '').toLowerCase();
  const known = sender
    ? (await getJson<{ keys: KnownKey[] }>(`/api/mail/keys?address=${encodeURIComponent(sender)}`))
        .keys
    : [];
  const autocrypt = autocrypted(message.autocrypt, sender);
  const read: Unsealed = { encrypted: false, signed: null, shown: null };
  let layer = await getJson<Layer>(`/api/mail/messages/${message.id}/sealed`);
  for (let depth = 0; depth < DEEPEST; depth++) {
    let entity: Bytes | null = null;
    if (layer.kind === 'smime') {
      const smime = await import('./mailSmime');
      if (layer.how === 'encrypted') {
        read.encrypted = true;
        entity = await openedWithAny(
          keys.filter((key) => key.format === 'smime'),
          (key) => smime.opened(bytesOf(layer.data), smimeKey(key)),
          'smime.notForMe',
        );
      } else {
        const detached = layer.content !== null;
        const found = await smimeSigned(
          bytesOf(detached ? layer.signature : layer.data),
          detached ? bytesOf(layer.content) : null,
          sender,
          known,
        );
        read.signed = found.signed;
        if (read.encrypted || !detached) entity = found.content;
      }
    } else {
      const pgp = await import('./mailPgp');
      const verifying = await pgpKeys(known, sender, autocrypt);
      if (layer.how === 'encrypted') {
        read.encrypted = true;
        const found = await openedWithAny(
          keys.filter((key) => key.format === 'pgp'),
          (key) => pgp.opened(bytesOf(layer.data), key.private, verifying),
          'pgp.notForMe',
        );
        if (found.checked) read.signed = await pgpSigned(found.checked, sender, known, autocrypt);
        if (layer.inline) {
          const text = new TextDecoder().decode(found.data);
          read.shown = { html: null, text, remote: false, files: [] };
          break;
        }
        entity = found.data;
      } else if (layer.inline) {
        const found = await pgp.checkedText(bytesOf(layer.data), verifying);
        read.signed = await pgpSigned(found.checked, sender, known, autocrypt);
        read.shown = { html: null, text: found.text, remote: false, files: [] };
        break;
      } else {
        const content = bytesOf(layer.content);
        const checked = await pgp.checked(content, bytesOf(layer.signature), verifying);
        read.signed = await pgpSigned(checked, sender, known, autocrypt);
        if (read.encrypted) entity = content;
      }
    }
    if (!entity) break;
    const answer = await postBytes<Partial<Shown> & { layer?: Layer }>(
      `/api/mail/messages/${message.id}/unsealed`,
      new Blob([entity], { type: 'application/octet-stream' }),
    );
    if (!answer.layer) {
      read.shown = answer as Shown;
      break;
    }
    layer = answer.layer;
  }
  return read;
}

/** The text of what was opened, as a reply quotes it. */
export function openedText(shown: Shown): string {
  if (shown.html === null) return shown.text ?? '';
  return new DOMParser().parseFromString(shown.html, 'text/html').body.innerText ?? '';
}

/** The message as a reply quotes it or a forward carries it: what the browser opened of it, where
    it is encrypted and was opened here. */
export function withUnsealed(queryClient: QueryClient, message: Opened): Opened {
  if (message.sealed !== 'encrypted') return message;
  const found = queryClient
    .getQueriesData<Unsealed>({ queryKey: ['mail', 'message', message.id, 'unsealed'] })
    .map(([, data]) => data?.shown)
    .find(Boolean);
  if (!found) return message;
  return {
    ...message,
    html: found.html,
    text: found.text,
    unsealed: { text: openedText(found), files: found.files },
  };
}

export function useUnsealed(message: Opened) {
  const { unlocked, keys, pending } = useMailKeys();
  const encrypted = message.sealed === 'encrypted';
  return useQuery({
    queryKey: [
      'mail',
      'message',
      message.id,
      'unsealed',
      encrypted ? keys.map((key) => key.fingerprint) : null,
    ],
    queryFn: () => unsealed(message, keys),
    enabled: message.sealed !== '' && (!encrypted || (unlocked && !pending && keys.length > 0)),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  });
}

function SignedLine({ signed, onAccepted }: { signed: Signed; onAccepted: () => void }) {
  const { t } = useI18n();
  const accept = useMutation({
    mutationFn: () => met(...signed.key!),
    onSuccess: onAccepted,
  });
  const Icon = STATUS_ICONS[signed.status];
  const good = signed.status === 'valid';
  return (
    <p className={`flex flex-wrap items-center gap-1.5 ${good ? 'text-success' : 'text-danger'}`}>
      <Icon size={16} aria-hidden className="shrink-0" />
      {t(`mail.signed.${signed.status}`)}
      {signed.address && <span className="text-muted">{signed.address}</span>}
      {signed.status === 'changed' && signed.key && (
        <button
          type="button"
          disabled={accept.isPending}
          onClick={() => accept.mutate()}
          className="text-accent hover:underline"
        >
          {t('mail.signed.accept')}
        </button>
      )}
      {accept.isError && <span>{sealFailure(accept.error, t)}</span>}
    </p>
  );
}

function OpenedFiles({ files }: { files: OpenedFile[] }) {
  const { t, formatNumber } = useI18n();
  return (
    <ul aria-label={t('mail.files')} className="flex flex-wrap gap-2">
      {files.map((file) => {
        const data = fromBase64(file.data);
        return (
          <li
            key={file.part}
            className="flex max-w-full min-w-0 items-center gap-2 rounded-lg border border-line px-2 py-1 text-sm"
          >
            <Paperclip size={14} aria-hidden className="shrink-0 text-muted" />
            <button
              type="button"
              onClick={() => saved(new Blob([data], { type: file.type }), file.name)}
              className="min-w-0 truncate text-left hover:underline"
            >
              {file.name || t('mail.download')}
            </button>
            <span className="shrink-0 text-xs text-muted">
              {formatSize(data.length, formatNumber)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** The vault's unlocking in place, for mail that needs its keys. */
export function VaultLocked() {
  const { t } = useI18n();
  const { unlock } = useVault();
  const vault = useVaultData();
  if (vault.isPending) return null;
  if (!vault.data) {
    return (
      <p>
        {t('mail.sealed.noVault')}{' '}
        <Link to="/vault" className="text-accent underline">
          {t('vault.title')}
        </Link>
      </p>
    );
  }
  return (
    <div className="flex max-w-sm flex-col gap-2">
      <p>{t('mail.sealed.locked')}</p>
      <UnlockForm vault={vault.data} mode="password" onOpened={(unlocked) => unlock(unlocked)} />
    </div>
  );
}

/** A sealed message's body: who signed it, and what an encrypted one says once the vault's key
    opened it; the server's body (`children`) where only a signature seals it. */
export function SealedBody({
  message,
  title,
  children,
}: {
  message: Opened;
  title: string;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { unlocked, keys, pending } = useMailKeys();
  const read = useUnsealed(message);
  const encrypted = message.sealed === 'encrypted';
  const shown = read.data?.shown;

  let body: ReactNode = children;
  if (encrypted) {
    if (!unlocked) body = <VaultLocked />;
    else if (pending || read.isPending)
      body = <p className="text-muted">{t('mail.sealed.opening')}</p>;
    else if (keys.length === 0)
      body = (
        <p>
          {t('mail.sealed.noKeys')}{' '}
          <Link to="/vault" className="text-accent underline">
            {t('vault.title')}
          </Link>
        </p>
      );
    else if (!shown) body = null;
  }
  if (shown) {
    body = (
      <>
        {shown.files.length > 0 && <OpenedFiles files={shown.files} />}
        {shown.html !== null ? (
          <HtmlBody title={title} html={shown.html} />
        ) : (
          <PlainBody text={shown.text ?? ''} />
        )}
      </>
    );
  }
  return (
    <>
      <div className="flex flex-col gap-1 text-sm">
        {encrypted && (
          <p className="flex items-center gap-1.5 text-muted">
            <Lock size={16} aria-hidden className="shrink-0" />
            {t('mail.sealed.encrypted')}
          </p>
        )}
        {read.data?.signed && (
          <SignedLine
            signed={read.data.signed}
            onAccepted={() =>
              void queryClient.invalidateQueries({
                queryKey: ['mail', 'message', message.id, 'unsealed'],
              })
            }
          />
        )}
        {read.isError && <p className="text-danger">{sealFailure(read.error, t)}</p>}
      </div>
      {body}
    </>
  );
}
