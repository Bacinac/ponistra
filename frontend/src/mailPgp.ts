import * as openpgp from 'openpgp';
import type { Bytes } from './vault/crypto';

export interface PgpDescribed {
  fingerprint: string;
  addresses: string[];
  name: string;
  expires: string | null;
  /** The public key in its binary form, which colleagues and correspondents encrypt to. */
  public: Bytes;
}

export interface PgpChecked {
  valid: boolean;
  /** The fingerprint of the key that signed, where one of the keys given did. */
  signer: string | null;
  /** The id of the key that signed, known or not. */
  keyId: string;
  signedAt: string | null;
}

/** Why a key or a message could not be used, by the key of its message. */
export class Unusable extends Error {}

const ADDRESS = /<([^<>\s]+@[^<>\s]+)>|([^<>\s]+@[^<>\s]+)/;

function addressesOf(key: openpgp.Key): string[] {
  return key
    .getUserIDs()
    .map((id) => ADDRESS.exec(id))
    .flatMap((found) => (found ? [(found[1] ?? found[2]).toLowerCase()] : []));
}

export async function described(key: openpgp.Key): Promise<PgpDescribed> {
  const expires = await key.getExpirationTime();
  const [id] = key.getUserIDs();
  return {
    fingerprint: key.getFingerprint(),
    addresses: addressesOf(key),
    name: id?.replace(/\s*<[^>]*>\s*$/, '') ?? '',
    expires: expires instanceof Date ? expires.toISOString() : null,
    public: key.toPublic().write() as Bytes,
  };
}

/** A secret key the user brings, opened with its passphrase where it has one: the vault keeps it
 * open, as the vault itself seals it. */
export async function imported(armored: string, passphrase: string): Promise<string> {
  let key: openpgp.PrivateKey;
  try {
    key = await openpgp.readPrivateKey({ armoredKey: armored });
  } catch {
    throw new Unusable('pgp.notPrivate');
  }
  if (!key.isDecrypted()) {
    try {
      key = await openpgp.decryptKey({ privateKey: key, passphrase });
    } catch {
      throw new Unusable('pgp.wrongPassphrase');
    }
  }
  return key.armor();
}

/** A new key for the address, Curve25519 as GnuPG and Thunderbird read. */
export async function generated(name: string, address: string): Promise<string> {
  const { privateKey } = await openpgp.generateKey({
    userIDs: [{ name, email: address }],
    format: 'armored',
  });
  return privateKey;
}

export function privateKey(armored: string): Promise<openpgp.PrivateKey> {
  return openpgp.readPrivateKey({ armoredKey: armored });
}

export async function publicKey(binary: Bytes): Promise<openpgp.Key> {
  try {
    return await openpgp.readKey({ binaryKey: binary });
  } catch {
    throw new Unusable('pgp.notKey');
  }
}

/** The public keys an armored block or a file holds. */
export async function publicKeys(given: string | Bytes): Promise<openpgp.Key[]> {
  try {
    const keys =
      typeof given === 'string'
        ? await openpgp.readKeys({ armoredKeys: given })
        : await openpgp.readKeys({ binaryKeys: given });
    return keys.map((key) => key.toPublic());
  } catch {
    throw new Unusable('pgp.notKey');
  }
}

async function result(
  signatures: openpgp.VerifyMessageResult['signatures'],
  keys: openpgp.Key[],
): Promise<PgpChecked> {
  const [first] = signatures;
  if (!first) return { valid: false, signer: null, keyId: '', signedAt: null };
  const keyId = first.keyID.toHex();
  const signer = keys.find((key) => key.getKeyIDs().some((id) => id.equals(first.keyID)));
  let valid = false;
  try {
    valid = await first.verified;
  } catch {
    valid = false;
  }
  const made = (await first.signature).packets[0]?.created;
  return {
    valid: valid && Boolean(signer),
    signer: signer?.getFingerprint() ?? null,
    keyId,
    signedAt: made ? made.toISOString() : null,
  };
}

/** What a PGP message encrypted to the key carries, and its signature where it is signed. */
export async function opened(
  armored: Bytes,
  key: string,
  keys: openpgp.Key[],
): Promise<{ data: Bytes; checked: PgpChecked | null }> {
  let message: openpgp.Message<Uint8Array>;
  try {
    message = await openpgp.readMessage({ armoredMessage: new TextDecoder().decode(armored) });
  } catch {
    throw new Unusable('pgp.unsupported');
  }
  try {
    const found = await openpgp.decrypt({
      message,
      decryptionKeys: await privateKey(key),
      verificationKeys: keys,
      format: 'binary',
    });
    const checked = found.signatures.length > 0 ? await result(found.signatures, keys) : null;
    return { data: found.data as Bytes, checked };
  } catch (error) {
    if (error instanceof Unusable) throw error;
    throw new Unusable('pgp.notForMe');
  }
}

/** Whether a detached signature signs the content. */
export async function checked(
  content: Bytes,
  signature: Bytes,
  keys: openpgp.Key[],
): Promise<PgpChecked> {
  const found = await openpgp.verify({
    message: await openpgp.createMessage({ binary: content }),
    signature: await openpgp.readSignature({
      armoredSignature: new TextDecoder().decode(signature),
    }),
    verificationKeys: keys,
    format: 'binary',
  });
  return result(found.signatures, keys);
}

/** Whether a message signed in its text is what its signer wrote, and that text. */
export async function checkedText(
  armored: Bytes,
  keys: openpgp.Key[],
): Promise<{ text: string; checked: PgpChecked }> {
  const message = await openpgp.readCleartextMessage({
    cleartextMessage: new TextDecoder().decode(armored),
  });
  const found = await openpgp.verify({ message, verificationKeys: keys });
  return { text: found.data, checked: await result(found.signatures, keys) };
}

const MICALG: Partial<Record<openpgp.enums.hash, string>> = {
  [openpgp.enums.hash.sha256]: 'pgp-sha256',
  [openpgp.enums.hash.sha384]: 'pgp-sha384',
  [openpgp.enums.hash.sha512]: 'pgp-sha512',
};

/** A detached signature over the entity in canonical text, as PGP/MIME signs (RFC 3156, 5). */
export async function signature(
  entity: Bytes,
  key: string,
): Promise<{ data: Bytes; micalg: string }> {
  const armored = await openpgp.sign({
    message: await openpgp.createMessage({ text: new TextDecoder().decode(entity) }),
    signingKeys: await privateKey(key),
    detached: true,
  });
  const read = await openpgp.readSignature({ armoredSignature: armored });
  const micalg = MICALG[read.packets[0]?.hashAlgorithm as openpgp.enums.hash];
  if (!micalg) throw new Unusable('pgp.unsupported');
  return { data: new TextEncoder().encode(armored) as Bytes, micalg };
}

/** The entity encrypted to each key, signed inside by the user's where they sign. */
export async function sealed(
  entity: Bytes,
  keys: openpgp.Key[],
  signingKey: string | null,
): Promise<Bytes> {
  const armored = await openpgp.encrypt({
    message: await openpgp.createMessage({ binary: entity }),
    encryptionKeys: keys,
    signingKeys: signingKey ? await privateKey(signingKey) : undefined,
  });
  return new TextEncoder().encode(armored) as Bytes;
}
