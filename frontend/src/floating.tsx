import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';

/** A bar that floats by what it is about, below it where there is room, else above it. */
export function Floating({
  anchor,
  within,
  label,
  children,
}: {
  anchor: DOMRectReadOnly;
  within: HTMLElement;
  label: string;
  children: ReactNode;
}) {
  const self = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ top: number; left: number } | null>(null);
  useLayoutEffect(() => {
    const room = within.getBoundingClientRect();
    const { width, height } = self.current!.getBoundingClientRect();
    const below = anchor.bottom - room.top + 6;
    const above = anchor.top - room.top - height - 6;
    const top = Math.min(
      Math.max(below + height <= room.height ? below : above, 8),
      room.height - height - 8,
    );
    const left = Math.max(Math.min(anchor.left - room.left, room.width - width - 8), 8);
    setPlace({ top, left });
  }, [anchor, within]);
  return (
    <div
      ref={self}
      role="toolbar"
      aria-label={label}
      onMouseDown={(event) => event.preventDefault()}
      style={place ?? { visibility: 'hidden' }}
      className="absolute z-20 flex items-center gap-0.5 rounded border border-line bg-raised p-1 text-sm shadow-lg"
    >
      {children}
    </div>
  );
}
