import { argon2id } from 'hash-wasm';

/** Bytes as WebCrypto takes them. */
export type Bytes = Uint8Array<ArrayBuffer>;

export interface Kdf {
  salt: string;
  memory: number;
  iterations: number;
  parallelism: number;
}

/** An X25519 key pair: the public key raw, the private one as PKCS #8. */
export interface Pair {
  publicKey: Bytes;
  privateKey: Bytes;
}

/** Argon2id's costs for a new password: 64 MiB, three passes, four lanes, as Bitwarden's. */
const COSTS = { memory: 65536, iterations: 3, parallelism: 4 };
const NONCE = 12;
const POINT = 32;
// Crockford's base32: no I, L, O or U, which are read for 1, 1, 0 and V.
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

export function toBase64(bytes: Bytes): string {
  let text = '';
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text);
}

export function fromBase64(text: string): Bytes {
  return Uint8Array.from(atob(text), (char) => char.charCodeAt(0));
}

export function toBase64Url(bytes: Bytes): string {
  return toBase64(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function random(size: number): Bytes {
  return crypto.getRandomValues(new Uint8Array(size));
}

export function joined(...parts: Bytes[]): Bytes {
  const whole = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let at = 0;
  for (const part of parts) {
    whole.set(part, at);
    at += part.length;
  }
  return whole;
}

export function textBytes(text: string): Bytes {
  return new TextEncoder().encode(text);
}

export function bytesText(bytes: Bytes): string {
  return new TextDecoder().decode(bytes);
}

function aes(raw: Bytes, usage: KeyUsage): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', raw, 'AES-GCM', false, [usage]);
}

/** The bytes sealed with a 256-bit key: a fresh nonce, then AES-GCM's ciphertext and tag. */
export async function seal(raw: Bytes, plain: Bytes): Promise<Bytes> {
  const iv = random(NONCE);
  const sealed = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    await aes(raw, 'encrypt'),
    plain,
  );
  return joined(iv, new Uint8Array(sealed));
}

/** What `seal` sealed; an OperationError where the key is not the one it was sealed with. */
export async function open(raw: Bytes, sealed: Bytes): Promise<Bytes> {
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: sealed.subarray(0, NONCE) },
    await aes(raw, 'decrypt'),
    sealed.subarray(NONCE),
  );
  return new Uint8Array(plain);
}

async function hkdf(secret: Bytes, info: string, salt: Bytes = new Uint8Array(0)): Promise<Bytes> {
  const key = await crypto.subtle.importKey('raw', secret, 'HKDF', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt, info: textBytes(info) },
    key,
    256,
  );
  return new Uint8Array(bits);
}

export function newKdf(): Kdf {
  return { salt: toBase64(random(16)), ...COSTS };
}

/** The key a password gives under these costs. */
export async function fromPassword(password: string, kdf: Kdf): Promise<Bytes> {
  const hash = await argon2id({
    password: password.normalize('NFC'),
    salt: fromBase64(kdf.salt),
    parallelism: kdf.parallelism,
    iterations: kdf.iterations,
    memorySize: kdf.memory,
    hashLength: 32,
    outputType: 'binary',
  });
  return new Uint8Array(hash);
}

/** 160 random bits as 32 letters and digits in groups of four. */
export function newCode(): string {
  let code = '';
  let value = 0;
  let bits = 0;
  for (const byte of random(20)) {
    value = (value << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      bits -= 5;
      code += ALPHABET[(value >> bits) & 31];
    }
    value &= (1 << bits) - 1;
  }
  return code.match(/.{4}/g)!.join('-');
}

/** A code as typed, without its dashes and spaces and with look-alike letters read as Crockford
    reads them; null where it cannot be a code. */
export function spelledCode(typed: string): string | null {
  const plain = typed.toUpperCase().replace(/[\s-]/g, '').replace(/O/g, '0').replace(/[IL]/g, '1');
  return /^[0-9A-HJKMNP-TV-Z]{32}$/.test(plain) ? plain : null;
}

/** The key a code gives. Its 160 random bits need no stretching. */
export function fromCode(spelled: string): Promise<Bytes> {
  return hkdf(textBytes(spelled), 'scriptor vault code');
}

/** The key a passkey's PRF output gives. */
export function fromPrf(output: Bytes): Promise<Bytes> {
  return hkdf(output, 'scriptor vault passkey');
}

export async function newPair(): Promise<Pair> {
  const pair = (await crypto.subtle.generateKey({ name: 'X25519' }, true, [
    'deriveBits',
  ])) as CryptoKeyPair;
  return {
    publicKey: new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey)),
    privateKey: new Uint8Array(await crypto.subtle.exportKey('pkcs8', pair.privateKey)),
  };
}

async function agreed(privateKey: Bytes, publicKey: Bytes): Promise<Bytes> {
  const mine = await crypto.subtle.importKey('pkcs8', privateKey, { name: 'X25519' }, false, [
    'deriveBits',
  ]);
  const theirs = await crypto.subtle.importKey('raw', publicKey, { name: 'X25519' }, false, []);
  return new Uint8Array(
    await crypto.subtle.deriveBits({ name: 'X25519', public: theirs }, mine, 256),
  );
}

/** Bytes only the holder of the private half of `to` opens: a key pair made for this once agrees
    a secret with `to`, HKDF turns it into a key, AES-GCM seals with it, and the one-off public
    key goes in front. */
export async function sealTo(to: Bytes, plain: Bytes): Promise<Bytes> {
  const once = await newPair();
  const secret = await agreed(once.privateKey, to);
  const key = await hkdf(secret, 'scriptor vault sealed', joined(once.publicKey, to));
  return joined(once.publicKey, await seal(key, plain));
}

export async function openSealed(pair: Pair, sealed: Bytes): Promise<Bytes> {
  const from = sealed.subarray(0, POINT);
  const secret = await agreed(pair.privateKey, from);
  const key = await hkdf(secret, 'scriptor vault sealed', joined(from, pair.publicKey));
  return open(key, sealed.subarray(POINT));
}
