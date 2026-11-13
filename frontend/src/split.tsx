import { useCallback, useRef, useState, type CSSProperties } from 'react';
import { useI18n } from './i18n';

/** A column the reader widens or narrows by the separator beside it, its width in pixels kept in
    their browser. The column's own CSS caps it at a share of the row, so a narrower window never
    loses the column across from it. */
export interface Column {
  name: string;
  initial: number;
  min: number;
  max: number;
}

const STEP = 16;

export function clampWidth(column: Column, width: number): number {
  return Math.round(Math.min(column.max, Math.max(column.min, width)));
}

const keyOf = (column: Column) => `ponistra.width.${column.name}`;

export function storedWidth(column: Column): number {
  try {
    const width = Number(localStorage.getItem(keyOf(column)));
    return width ? clampWidth(column, width) : column.initial;
  } catch {
    return column.initial;
  }
}

/** The column's width and the custom property `--<name>` its classes read it from. */
export function useWidth(column: Column): [number, (width: number) => void, CSSProperties] {
  const [width, setWidth] = useState(() => storedWidth(column));
  const change = useCallback(
    (next: number) => {
      setWidth(next);
      try {
        localStorage.setItem(keyOf(column), String(next));
      } catch {
        return;
      }
    },
    [column],
  );
  return [width, change, { [`--${column.name}`]: `${width}px` } as CSSProperties];
}

/** Drags the column beside it, which stands on its left or right (`from`); the arrow keys step
    it, Home and End take it to its bounds and a double click puts it back. Each move starts from
    the width the column shows, which its cap may hold below the one kept. */
export function Splitter({
  column,
  width,
  onWidth,
  from = 'left',
  className = '',
}: {
  column: Column;
  width: number;
  onWidth: (width: number) => void;
  from?: 'left' | 'right';
  className?: string;
}) {
  const { t } = useI18n();
  const start = useRef<{ x: number; width: number } | null>(null);
  const sign = from === 'left' ? 1 : -1;
  const shown = (bar: HTMLElement) => {
    const own = from === 'left' ? bar.previousElementSibling : bar.nextElementSibling;
    return own ? own.getBoundingClientRect().width : width;
  };
  const end = (bar: HTMLElement) => {
    if (!start.current) return;
    start.current = null;
    onWidth(clampWidth(column, shown(bar)));
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={t('frame.width')}
      title={t('frame.widthHint')}
      aria-valuenow={width}
      aria-valuemin={column.min}
      aria-valuemax={column.max}
      tabIndex={0}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        start.current = { x: event.clientX, width: shown(event.currentTarget) };
      }}
      onPointerMove={(event) => {
        const was = start.current;
        if (was) onWidth(clampWidth(column, was.width + sign * (event.clientX - was.x)));
      }}
      onPointerUp={(event) => end(event.currentTarget)}
      onPointerCancel={(event) => end(event.currentTarget)}
      onDoubleClick={() => onWidth(column.initial)}
      onKeyDown={(event) => {
        const now = shown(event.currentTarget);
        const next = {
          ArrowLeft: now - sign * STEP,
          ArrowRight: now + sign * STEP,
          Home: column.min,
          End: column.max,
        }[event.key];
        if (next === undefined) return;
        event.preventDefault();
        onWidth(clampWidth(column, next));
      }}
      className={`group relative z-10 shrink-0 cursor-col-resize touch-none justify-center ${className}`}
    >
      <span className="w-0.5 rounded-full transition-colors group-hover:bg-line group-active:bg-accent" />
    </div>
  );
}
