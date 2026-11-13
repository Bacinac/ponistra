const DIGITS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
const WIDTH = 22;

/** One part of an address: a title for people, then the id the page is found by. */
export const SEGMENT = '(?:[a-z0-9-]*-)?[0-9A-Za-z]{22}';

/** A UUID as an address writes it: 22 base62 digits. */
export function compact(uuid: string): string {
  let value = BigInt(`0x${uuid.replaceAll('-', '')}`);
  let digits = '';
  for (let place = 0; place < WIDTH; place++) {
    digits = DIGITS[Number(value % 62n)] + digits;
    value /= 62n;
  }
  return digits;
}

function expand(digits: string): string | null {
  let value = 0n;
  for (const digit of digits) value = value * 62n + BigInt(DIGITS.indexOf(digit));
  if (value >> 128n) return null;
  const hex = value.toString(16).padStart(32, '0');
  return [20, 16, 12, 8].reduce((uuid, at) => `${uuid.slice(0, at)}-${uuid.slice(at)}`, hex);
}

/** The id a part of an address ends in; the words before it are not read. */
export function idIn(segment: string | undefined): string | null {
  const digits = segment?.match(new RegExp(`^${SEGMENT}$`)) && segment.slice(-WIDTH);
  return digits ? expand(digits) : null;
}

export function segment(title: string, id: string): string {
  const words = title
    .toLowerCase()
    .replaceAll('đ', 'dj')
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .replace(/[^a-z0-9]+/g, '-')
    .slice(0, 60)
    .replace(/^-+|-+$/g, '');
  return words ? `${words}-${compact(id)}` : compact(id);
}
