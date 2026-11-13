import { useQuery } from '@tanstack/react-query';
import { getJson, postJson } from './api';
import { isMessageKey } from './i18n';
import type { MessageKey } from './i18n/hr';
import { errorMessage } from './tree';
import { fromBase64, toBase64, type Bytes } from './vault/crypto';
import type { SmimeKey } from './mailSmime';
import { useHeld } from './vault/search';
import type { MailKey } from './vault/secret';
import { useVault } from './vault/state';

/** A key the server keeps for an address: the user's own, a colleague's own, or one the user met
    on a signed message. */
export interface KnownKey {
  id: number;
  kind: 'smime' | 'pgp';
  address: string;
  fingerprint: string;
  data: string;
  own: boolean;
  mine: boolean;
  expires_at: string | null;
  seen_at: string;
}

export const KEYS = ['mail', 'keys'];

const ARMORED = '-----BEGIN PGP';

/** What went wrong with a key or a seal: the reason the crypto modules name, else the server's. */
export function sealFailure(error: Error, t: (key: MessageKey) => string): string {
  const key = error.message;
  if (/^(smime|pgp|mail\.sealing)\./.test(key) && isMessageKey(key)) {
    const addresses = (error as Error & { addresses?: string[] }).addresses ?? [];
    return addresses.length > 0 ? `${t(key)} ${addresses.join(', ')}` : t(key);
  }
  return errorMessage(error, t);
}

async function fromPgp(armored: string): Promise<MailKey> {
  const pgp = await import('./mailPgp');
  const described = await pgp.described(await pgp.privateKey(armored));
  return {
    format: 'pgp',
    addresses: described.addresses,
    fingerprint: described.fingerprint,
    expires: described.expires,
    private: armored,
    public: [toBase64(described.public)],
  };
}

/** The key a file holds: PKCS #12 opened with its password, or an armored PGP secret key opened
    with its passphrase. */
export async function keyFrom(file: File, password: string): Promise<MailKey> {
  const data = new Uint8Array(await file.arrayBuffer()) as Bytes;
  const text = new TextDecoder().decode(data.subarray(0, 4096));
  if (text.includes(ARMORED)) {
    const pgp = await import('./mailPgp');
    return fromPgp(await pgp.imported(new TextDecoder().decode(data), password));
  }
  const smime = await import('./mailSmime');
  const key = await smime.fromPkcs12(data, password);
  const certified = await smime.described(key.chain[0]);
  return {
    format: 'smime',
    addresses: certified.addresses,
    fingerprint: certified.fingerprint,
    expires: certified.notAfter,
    private: toBase64(key.privateKey),
    public: key.chain.map(toBase64),
  };
}

/** A new PGP key for the address. */
export async function madeKey(name: string, address: string): Promise<MailKey> {
  const pgp = await import('./mailPgp');
  return fromPgp(await pgp.generated(name, address));
}

export function smimeKey(key: MailKey): SmimeKey {
  return { privateKey: fromBase64(key.private), chain: key.public.map(fromBase64) };
}

/** The key's public part as the user's own, under each address it carries, so colleagues and
    their own replies encrypt to it. */
export async function published(key: MailKey): Promise<void> {
  for (const address of key.addresses) {
    await postJson(`/api/mail/keys`, {
      kind: key.format,
      address,
      fingerprint: key.fingerprint,
      data: key.public[0],
      own: true,
      expires_at: key.expires,
    });
  }
}

/** The mail keys the unlocked vault holds, in every collection the user reads. */
export function useMailKeys(): { unlocked: boolean; keys: MailKey[]; pending: boolean } {
  const { unlocked } = useVault();
  const held = useHeld(true);
  const keys = (held.data ?? []).flatMap(({ item }) =>
    item.secret.kind === 'mailkey' && item.secret.mailkey ? [item.secret.mailkey] : [],
  );
  return { unlocked: unlocked !== null, keys, pending: unlocked !== null && held.isPending };
}

/** The keys the server knows for the addresses, the user's own and colleagues' first. */
export function useKnownKeys(addresses: string[], enabled = true) {
  const asked = [...new Set(addresses.map((address) => address.toLowerCase()))].sort();
  return useQuery({
    queryKey: [...KEYS, ...asked],
    queryFn: () =>
      getJson<{ keys: KnownKey[] }>(
        `/api/mail/keys?${asked.map((address) => `address=${encodeURIComponent(address)}`).join('&')}`,
      ).then(({ keys }) => keys),
    enabled: enabled && asked.length > 0,
  });
}

/** Every key the user keeps beside their own vault's: their own published and those they met. */
export function useMyKeys() {
  return useQuery({
    queryKey: [...KEYS, 'mine'],
    queryFn: () => getJson<{ keys: KnownKey[] }>('/api/mail/keys').then(({ keys }) => keys),
  });
}

/** The key the user met on a signed message, or that a correspondent sent, kept for the address. */
export function met(
  kind: 'smime' | 'pgp',
  address: string,
  fingerprint: string,
  data: Bytes,
  expires: string | null,
): Promise<KnownKey> {
  return postJson<KnownKey>('/api/mail/keys', {
    kind,
    address,
    fingerprint,
    data: toBase64(data),
    own: false,
    expires_at: expires,
  });
}
