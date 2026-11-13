import type { LucideIcon } from 'lucide-react';
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

export interface Choice {
  id: string;
  label: string;
  icon: LucideIcon;
  keys?: string;
  disabled: boolean;
  run: () => void;
}

export type Palette = (query: string) => Choice[];

const Current = createContext<Palette | null>(null);
const Provide = createContext<((palette: Palette | null) => void) | null>(null);

export function PaletteProvider({ children }: { children: ReactNode }) {
  const [palette, setPalette] = useState<Palette | null>(null);
  const provide = useCallback((next: Palette | null) => setPalette(() => next), []);
  return (
    <Provide value={provide}>
      <Current value={palette}>{children}</Current>
    </Provide>
  );
}

export function usePalette(): Palette | null {
  return useContext(Current);
}

export function useProvidePalette(palette: Palette): void {
  const provide = useContext(Provide);
  useEffect(() => {
    if (!provide) return;
    provide(palette);
    return () => provide(null);
  }, [provide, palette]);
}
