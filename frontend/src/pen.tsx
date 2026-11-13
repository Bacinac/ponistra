import { TEXT_COLORS, type Swatch, type TextColor } from './editor/colors';
import { useI18n } from './i18n';

/** Pen widths, thin to thick: points on a PDF's page, the image's own units on an image. */
export const WIDTHS = [1, 2, 4] as const;
export type Width = (typeof WIDTHS)[number];

export interface Pen {
  color: TextColor;
  width: Width;
}

export const pressedButton = 'rounded p-1.5 hover:bg-hover aria-pressed:bg-selected';

/** A colour as it shows on paper, which is how a file's pages always show. */
export function SwatchButton({
  swatch,
  label,
  pressed,
  onClick,
}: {
  swatch: Swatch;
  label: string;
  pressed?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={pressedButton}
    >
      <span
        aria-hidden
        style={{ background: swatch.light }}
        className="block size-4 rounded-sm border border-line"
      />
    </button>
  );
}

/** The pen's colours to choose from. */
export function ColorChoice({ pen, onPen }: { pen: Pen; onPen: (pen: Pen) => void }) {
  const { t } = useI18n();
  return (Object.entries(TEXT_COLORS) as [TextColor, Swatch][]).map(([name, swatch]) => (
    <SwatchButton
      key={name}
      swatch={swatch}
      label={t(`color.${name}`)}
      pressed={pen.color === name}
      onClick={() => onPen({ ...pen, color: name })}
    />
  ));
}

/** The pen's widths, thin to thick. */
export function WidthChoice({ pen, onPen }: { pen: Pen; onPen: (pen: Pen) => void }) {
  const { t } = useI18n();
  return WIDTHS.map((width) => (
    <button
      key={width}
      type="button"
      aria-label={t(`pdf.width.${width}`)}
      title={t(`pdf.width.${width}`)}
      aria-pressed={pen.width === width}
      onClick={() => onPen({ ...pen, width })}
      className={pressedButton}
    >
      <span aria-hidden style={{ height: width + 1 }} className="block w-4 rounded-full bg-ink" />
    </button>
  ));
}

/** The pen's colours and widths to choose from, in one row. */
export function PenChoice({ pen, onPen }: { pen: Pen; onPen: (pen: Pen) => void }) {
  return (
    <>
      <ColorChoice pen={pen} onPen={onPen} />
      <span aria-hidden className="mx-1 h-5 w-px bg-line" />
      <WidthChoice pen={pen} onPen={onPen} />
    </>
  );
}
