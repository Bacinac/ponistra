import { EyeOff } from 'lucide-react';
import type { CSSProperties } from 'react';
import { useI18n } from '../i18n';
import { frameOf, HEADER, lookDeclarations, type Deck, type LaidBox } from './deck';
import { imageUrl } from './schema';
import type { Look, Shape } from './slides';

const BLOB = /^[0-9a-f]{64}$/;
const COLOR = /^#[0-9a-f]{6}$/;
const POINT = 96 / 72;

function lookStyle(look: Look | undefined): CSSProperties {
  const style: Record<string, string> = {};
  for (const [name, value] of lookDeclarations(look)) {
    if (name === '--slide-align') style.textAlign = value;
    else style[name.replace(/-(\w)/g, (_, letter: string) => letter.toUpperCase())] = value;
  }
  const anchor = look?.anchor ?? 'top';
  return {
    ...style,
    justifyContent:
      anchor === 'middle' ? 'center' : anchor === 'bottom' ? 'flex-end' : 'flex-start',
  };
}

function color(value: string | undefined): string | undefined {
  return value && COLOR.test(value) ? value : undefined;
}

function ShapeView({ shape, number, date }: { shape: Shape; number: string; date: string }) {
  const frame = frameOf(shape);
  const place: CSSProperties = { left: frame.x, top: frame.y, width: frame.w, height: frame.h };
  const line = shape.line && color(shape.line.color) && shape.line;
  const stroke = line ? Math.max(line.width, 0) * POINT : 0;
  switch (shape.type) {
    case 'rect':
    case 'ellipse':
      return (
        <div
          className="ponistra-slide-shape"
          style={{
            ...place,
            background: color(shape.fill),
            border: line ? `${stroke}px solid ${line.color}` : undefined,
            borderRadius: shape.type === 'ellipse' ? '50%' : undefined,
          }}
        />
      );
    case 'line':
      return (
        <svg
          className="ponistra-slide-shape overflow-visible"
          style={place}
          viewBox={`0 0 ${frame.w || 1} ${frame.h || 1}`}
          preserveAspectRatio="none"
        >
          <line
            x1={0}
            y1={shape.flip ? frame.h : 0}
            x2={frame.w}
            y2={shape.flip ? 0 : frame.h}
            stroke={line ? line.color : 'currentColor'}
            strokeWidth={stroke || POINT}
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      );
    case 'image':
      return shape.blob && BLOB.test(shape.blob) ? (
        <img className="ponistra-slide-shape" style={place} src={imageUrl(shape.blob)} alt="" />
      ) : null;
    case 'text':
    case 'number':
    case 'date':
      return (
        <div className="ponistra-slide-text" style={{ ...place, ...lookStyle(shape.text) }}>
          {shape.type === 'number' ? number : shape.type === 'date' ? date : shape.content}
        </div>
      );
  }
}

/** A box of its layout that nothing is written in yet, offering to be written. */
function Prompt({ box }: { box: LaidBox }) {
  const { t } = useI18n();
  return (
    <div
      className="ponistra-slide-prompt"
      style={{ left: box.x, top: box.y, width: box.w, height: box.h, ...lookStyle(box.look) }}
    >
      {t(`slides.prompt.${box.role}`)}
    </div>
  );
}

/** The slides behind the tab's text as the deck lays it out: each with its own background or
 * its layout's, its layout's shapes, its number above it, its boxes yet to be written and the
 * panel of its speaker notes. */
export function Frames({
  deck,
  cursor,
  editable,
  date,
  scope,
  first,
}: {
  deck: Deck;
  /** Where the cursor is while the editor has the focus, which a box's prompt gives way to. */
  cursor: number | null;
  editable: boolean;
  date: string;
  scope: string;
  /** How many slides the tabs before have, after which these are numbered. */
  first: number;
}) {
  const { t, formatNumber } = useI18n();
  return (
    <div data-styling={scope} aria-hidden className="ponistra-papers">
      {deck.slides.map((slide, index) => {
        const number = formatNumber(first + index + 1);
        const { background } = slide;
        const image = background?.image && BLOB.test(background.image) ? background.image : null;
        return (
          <div key={index}>
            <div className="ponistra-slide-head" style={{ top: slide.top - HEADER }}>
              <span>{number}</span>
              {slide.hidden && (
                <span className="flex items-center gap-1">
                  <EyeOff size={14} aria-hidden />
                  {t('slides.hidden')}
                </span>
              )}
            </div>
            <div
              className="ponistra-slide"
              data-hidden={slide.hidden || undefined}
              style={{
                top: slide.top,
                width: deck.width,
                height: deck.height,
                backgroundColor: color(background?.color),
                backgroundImage: image ? `url("${imageUrl(image)}")` : undefined,
              }}
            >
              {slide.layout.shapes.map((shape, at) => (
                <ShapeView key={at} shape={shape} number={number} date={date} />
              ))}
              {slide.boxes
                .filter(
                  (box) =>
                    editable &&
                    box.own &&
                    box.blank &&
                    !(cursor !== null && cursor >= box.from && cursor <= box.to),
                )
                .map((box) => (
                  <Prompt key={box.key} box={box} />
                ))}
              {slide.boxes
                .filter((box) => box.over)
                .map((box) => (
                  <div
                    key={box.key}
                    className="ponistra-slide-over"
                    style={{ left: box.x, top: box.y, width: box.w, height: box.h }}
                  />
                ))}
            </div>
            {slide.notes && (
              <div
                className="ponistra-slide-notes"
                style={{ top: slide.notes.top, width: deck.width, height: slide.notes.height }}
              >
                {t('command.speakerNotes')}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
