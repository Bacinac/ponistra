import inverse from './assets/brand/logo-inverse.svg';
import logo from './assets/brand/logo.svg';
import markInverse from './assets/brand/mark-inverse.svg';
import mark from './assets/brand/mark.svg';
import { useDark } from './theme';

/** Where the P's ink is centred along the logo's width (x 45.5 of its 11.5–623.5 view box). */
export const MARK_AXIS = '5.56%';

/** The family sets its wordmarks by height, so every logo's stroke stays the same weight. */
export function Brand({ compact = false }: { compact?: boolean }) {
  const dark = useDark();
  return (
    <img
      src={dark ? inverse : logo}
      alt="Ponistra"
      width={compact ? 204 : 408}
      height={compact ? 28 : 56}
      className={`block shrink-0 ${compact ? 'h-7 w-[204px]' : 'h-auto w-[408px] max-w-full'}`}
      draggable={false}
    />
  );
}

/** The mark alone. */
export function BrandIcon() {
  const dark = useDark();
  return (
    <img
      src={dark ? markInverse : mark}
      alt="Ponistra"
      width={36}
      height={36}
      className="block size-9 shrink-0"
      draggable={false}
    />
  );
}
