import type { Bytes } from './crypto';

export interface Totp {
  secret: Bytes;
  digits: number;
  period: number;
  hash: 'SHA-1' | 'SHA-256' | 'SHA-512';
}

const BASE32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
const HASHES = { SHA1: 'SHA-1', SHA256: 'SHA-256', SHA512: 'SHA-512' } as const;

function base32(text: string): Bytes | null {
  const plain = text.toUpperCase().replace(/[\s=-]/g, '');
  // RFC 4226 asks for 128 bits; sites give no fewer than 80.
  if (plain.length < 16 || /[^A-Z2-7]/.test(plain)) return null;
  const bytes: number[] = [];
  let value = 0;
  let bits = 0;
  for (const char of plain) {
    value = (value << 5) | BASE32.indexOf(char);
    bits += 5;
    if (bits >= 8) {
      bits -= 8;
      bytes.push((value >> bits) & 255);
    }
    value &= (1 << bits) - 1;
  }
  return Uint8Array.from(bytes);
}

/** An otpauth:// address, or a base32 secret as a site shows it beside its QR code; null where
    the text is neither. */
export function parseTotp(text: string): Totp | null {
  const given = text.trim();
  if (!given.toLowerCase().startsWith('otpauth://')) {
    const secret = base32(given);
    return secret && { secret, digits: 6, period: 30, hash: 'SHA-1' };
  }
  let address: URL;
  try {
    address = new URL(given);
  } catch {
    return null;
  }
  if (address.host.toLowerCase() !== 'totp') return null;
  const secret = base32(address.searchParams.get('secret') ?? '');
  const digits = Number(address.searchParams.get('digits') ?? 6);
  const period = Number(address.searchParams.get('period') ?? 30);
  const hash = HASHES[(address.searchParams.get('algorithm') ?? 'SHA1').toUpperCase() as 'SHA1'];
  if (!secret || ![6, 7, 8].includes(digits) || !(period > 0) || !hash) return null;
  return { secret, digits, period, hash };
}

/** The code RFC 6238 gives at this moment. */
export async function totpCode(totp: Totp, now: number = Date.now()): Promise<string> {
  const counter = Math.floor(now / 1000 / totp.period);
  const message = new Uint8Array(8);
  new DataView(message.buffer).setBigUint64(0, BigInt(counter));
  const key = await crypto.subtle.importKey(
    'raw',
    totp.secret,
    { name: 'HMAC', hash: totp.hash },
    false,
    ['sign'],
  );
  const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, message));
  const at = mac[mac.length - 1] & 15;
  const value = new DataView(mac.buffer).getUint32(at) & 0x7fffffff;
  return String(value % 10 ** totp.digits).padStart(totp.digits, '0');
}

/** Seconds until the code changes. */
export function totpLeft(totp: Totp, now: number = Date.now()): number {
  return totp.period - (Math.floor(now / 1000) % totp.period);
}
