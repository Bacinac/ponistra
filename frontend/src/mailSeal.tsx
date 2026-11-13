import { FileSignature, Lock } from 'lucide-react';
import { useState } from 'react';
import { getJson, postJson, upload } from './api';
import { useI18n } from './i18n';
import type { Opened } from './mail';
import { smimeKey, useMailKeys, useMyKeys, type KnownKey } from './mailKeys';
import { VaultLocked } from './mailSealed';
import { button } from './styles';
import { fromBase64, type Bytes } from './vault/crypto';
import type { MailKey } from './vault/secret';

export interface Choice {
  sign: boolean;
  encrypt: boolean;
}

/** What the message carries sealed, as `/api/mail/send` takes it: blobs uploaded, by hash. */
export interface Given {
  kind: 'smime' | 'pgp';
  how: 'signed' | 'encrypted';
  micalg?: string;
  entity?: string;
  data: string;
}

/** Why a message cannot leave sealed: no key of the user's own for the address it goes from, or
    recipients no key of the same kind encrypts to. */
export class Unsealable extends Error {
  constructor(
    key: 'mail.sealing.noOwnKey' | 'mail.sealing.noKeys',
    readonly addresses: string[],
  ) {
    super(key);
  }
}

async function stored(data: Bytes): Promise<string> {
  return (await upload(new Blob([data], { type: 'application/octet-stream' }))).sha256;
}

function usable(key: KnownKey): boolean {
  return key.expires_at === null || new Date(key.expires_at) > new Date();
}

/** The message's body signed, encrypted, or both, with the user's own key for the address it goes
    from and, to encrypt, every recipient's key of the same kind and the user's own. */
export async function sealedFor(
  message: object,
  choice: Choice,
  from: string,
  recipients: string[],
  keys: MailKey[],
): Promise<Given> {
  const own = keys.filter((key) => key.addresses.includes(from.toLowerCase()));
  if (own.length === 0) throw new Unsealable('mail.sealing.noOwnKey', [from]);
  let mine = own[0];
  let theirs: KnownKey[] = [];
  if (choice.encrypt) {
    const asked = [...new Set(recipients.map((address) => address.toLowerCase()))];
    const { keys: known } = await getJson<{ keys: KnownKey[] }>(
      `/api/mail/keys?${asked.map((address) => `address=${encodeURIComponent(address)}`).join('&')}`,
    );
    const missing = (format: MailKey['format']) =>
      asked.filter(
        (address) =>
          !known.some((key) => key.kind === format && key.address === address && usable(key)),
      );
    const fitting = own.find((key) => missing(key.format).length === 0);
    if (!fitting) throw new Unsealable('mail.sealing.noKeys', missing(mine.format));
    mine = fitting;
    theirs = known.filter((key) => key.kind === mine.format && usable(key));
  }
  const { entity: given } = await postJson<{ entity: string }>('/api/mail/sealing', message);
  const entity = fromBase64(given);
  if (mine.format === 'pgp') {
    const pgp = await import('./mailPgp');
    if (!choice.encrypt) {
      const signed = await pgp.signature(entity, mine.private);
      return {
        kind: 'pgp',
        how: 'signed',
        micalg: signed.micalg,
        entity: await stored(entity),
        data: await stored(signed.data),
      };
    }
    const publicKeys = (
      await Promise.all(
        [...theirs.map((key) => key.data), mine.public[0]].map((data) =>
          pgp.publicKeys(fromBase64(data)),
        ),
      )
    ).flat();
    const data = await pgp.sealed(entity, publicKeys, choice.sign ? mine.private : null);
    return { kind: 'pgp', how: 'encrypted', data: await stored(data) };
  }
  const smime = await import('./mailSmime');
  let sealing = entity;
  if (choice.sign) {
    const signed = await smime.signature(entity, smimeKey(mine));
    const seal: Given = {
      kind: 'smime',
      how: 'signed',
      micalg: signed.micalg,
      entity: await stored(entity),
      data: await stored(signed.data),
    };
    if (!choice.encrypt) return seal;
    const inner = await postJson<{ entity: string }>('/api/mail/sealing/signed', seal);
    sealing = fromBase64(inner.entity);
  }
  const certificates = [...theirs.map((key) => fromBase64(key.data)), fromBase64(mine.public[0])];
  const data = await smime.sealed(sealing, certificates);
  return { kind: 'smime', how: 'encrypted', data: await stored(data) };
}

/** Whether the message is signed and encrypted, offered where the user has a mail key of their
    own; a reply to an encrypted message is encrypted unless the user says otherwise. */
export function useSealing(original: Opened | undefined) {
  const answeringSealed = original?.sealed === 'encrypted';
  const [choice, setChoice] = useState<Choice>({ sign: false, encrypt: answeringSealed });
  const mine = useMyKeys();
  const { unlocked, keys } = useMailKeys();
  const offered =
    answeringSealed || keys.length > 0 || (mine.data ?? []).some((key) => key.own && key.mine);
  const chosen = choice.sign || choice.encrypt;
  return { choice, setChoice, offered, chosen, unlocked, keys };
}

export function SealingToggles({
  sealing,
  disabled,
}: {
  sealing: ReturnType<typeof useSealing>;
  disabled: boolean;
}) {
  const { t } = useI18n();
  if (!sealing.offered) return null;
  const toggle = (name: keyof Choice, label: 'mail.sealing.sign' | 'mail.sealing.encrypt') => {
    const Icon = name === 'sign' ? FileSignature : Lock;
    return (
      <button
        type="button"
        aria-pressed={sealing.choice[name]}
        disabled={disabled}
        onClick={() => sealing.setChoice({ ...sealing.choice, [name]: !sealing.choice[name] })}
        className={`${button} aria-pressed:bg-selected aria-pressed:font-semibold`}
      >
        <Icon size={16} aria-hidden />
        {t(label)}
      </button>
    );
  };
  return (
    <>
      {toggle('sign', 'mail.sealing.sign')}
      {toggle('encrypt', 'mail.sealing.encrypt')}
    </>
  );
}

/** The vault's unlocking where the user chose to seal the message and it is locked. */
export function SealingLocked({ sealing }: { sealing: ReturnType<typeof useSealing> }) {
  return sealing.chosen && !sealing.unlocked ? <VaultLocked /> : null;
}
