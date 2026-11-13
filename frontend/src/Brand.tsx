import inverse from './assets/brand/logo-inverse.svg';
import logo from './assets/brand/logo.svg';
import mark from './assets/brand/mark.svg';
import { useDark } from './theme';

export function Brand({ compact = false }: { compact?: boolean }) {
  const dark = useDark();
  return (
    <img
      src={dark ? inverse : logo}
      alt="Ponistra"
      width={compact ? 138 : 330}
      height={compact ? 40 : 96}
      className={`block shrink-0 ${compact ? 'h-10 w-[138px] object-contain' : 'h-auto w-[330px] max-w-full'}`}
      draggable={false}
    />
  );
}

/** The mark alone. */
export function BrandIcon() {
  return (
    <img
      src={mark}
      alt="Ponistra"
      width={36}
      height={36}
      className="block size-9 shrink-0"
      draggable={false}
    />
  );
}
