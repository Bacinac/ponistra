import {
  Crop,
  EyeOff,
  MoveUpRight,
  PenLine,
  Redo2,
  RotateCcw,
  RotateCw,
  Square,
  TrianglesCenterlineDashedHorizontal,
  TrianglesCenterlineDashedVertical,
  Type,
  Undo2,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useEffectEvent, type ReactNode } from 'react';
import { Loading, Panel } from '../frame';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { ColorChoice, WidthChoice, type Pen } from '../pen';
import { button, iconButton, smallField } from '../styles';
import {
  centred,
  mirroredDown,
  RATIOS,
  SIDES,
  sizeOf,
  TONES,
  TOOLS,
  turnedShown,
  uprightRect,
  type Edits,
  type Ratio,
  type Size,
  type Tone,
  type Tool,
} from './edits';
import { shownSize } from './ImageView';
import type { ImageRoom, Kept } from './room';

const RATIO_LABELS = new Map<Ratio, string>([
  [1, '1:1'],
  [4 / 3, '4:3'],
  [16 / 9, '16:9'],
]);

const TOOL_ICONS: Record<Tool, LucideIcon> = {
  arrow: MoveUpRight,
  rectangle: Square,
  stroke: PenLine,
  text: Type,
  blur: EyeOff,
};

/** Takes the edits back and forth by Ctrl+Z and Ctrl+Y outside a field being typed in. */
export function useUndoKeys(room: ImageRoom | null) {
  const key = useEffectEvent((event: globalThis.KeyboardEvent) => {
    const typing =
      'input:not([type="checkbox"], [type="radio"], [type="range"]), textarea, select, [contenteditable="true"]';
    if (!room || (event.target as Element).closest(typing)) return;
    const letter = event.key.toLowerCase();
    if (!(event.ctrlKey || event.metaKey) || event.altKey || (letter !== 'z' && letter !== 'y')) {
      return;
    }
    event.preventDefault();
    if (letter === 'y' || event.shiftKey) room.redo();
    else room.undo();
  });
  useEffect(() => {
    const listener = (event: globalThis.KeyboardEvent) => key(event);
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, []);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-muted">{title}</h3>
      {children}
    </section>
  );
}

/** Crops, turns, mirrors, makes smaller, tones and marks the image; the tone shown while a slider
 * is dragged is `toning`, which reaches the room once it is let go. */
export function EditPanel({
  room,
  kept,
  altered,
  edits,
  upright,
  cropping,
  onCropping,
  onToning,
  tool,
  onTool,
  pen,
  onPen,
  save,
  failure,
  onSave,
  onClose,
}: {
  room: ImageRoom | null;
  kept: Kept;
  /** Whether anything is edited or marked, so that there is a copy. */
  altered: boolean;
  edits: Edits;
  upright: Size | null;
  cropping: Ratio | undefined;
  onCropping: (ratio: Ratio | undefined) => void;
  onToning: (tone: Partial<Record<Tone, number>>) => void;
  tool: Tool | null;
  onTool: (tool: Tool | null) => void;
  pen: Pen;
  onPen: (pen: Pen) => void;
  /** What saving the copy is called where it is saved. */
  save: string;
  /** Why saving it did not go through. */
  failure?: string | null;
  onSave: () => void;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  if (!room || !upright) {
    return (
      <Panel title={t('image.editing')} onClose={onClose}>
        <Loading />
      </Panel>
    );
  }
  const full = shownSize(upright, edits);
  const cropped = sizeOf(upright, { ...edits, side: null });
  const longer = Math.max(cropped.width, cropped.height);
  const sides = SIDES.filter((side) => side < longer || side === edits.side);
  const result = sizeOf(upright, edits);
  const dimensions = ({ width, height }: Size) =>
    `${formatNumber(width)} × ${formatNumber(height)} px`;
  const iconAction = (label: MessageKey, Icon: LucideIcon, onClick: () => void) => (
    <button
      type="button"
      aria-label={t(label)}
      title={t(label)}
      onClick={onClick}
      className={iconButton}
    >
      <Icon size={16} aria-hidden />
    </button>
  );
  const ratioChosen = (ratio: Ratio) => {
    onCropping(ratio);
    if (ratio !== null) room.change({ crop: uprightRect(centred(full, ratio), upright, edits) });
  };
  const toned = (tone: Tone) => () => {
    if (edits[tone] === kept.edits[tone]) return;
    room.change({ [tone]: edits[tone] });
    onToning({});
  };

  return (
    <Panel title={t('image.editing')} onClose={onClose}>
      <div className="flex gap-1">
        <button
          type="button"
          aria-label={t('command.undo')}
          title={t('command.undo')}
          disabled={!kept.undoable}
          onClick={room.undo}
          className={`${iconButton} disabled:opacity-40`}
        >
          <Undo2 size={16} aria-hidden />
        </button>
        <button
          type="button"
          aria-label={t('command.redo')}
          title={t('command.redo')}
          disabled={!kept.redoable}
          onClick={room.redo}
          className={`${iconButton} disabled:opacity-40`}
        >
          <Redo2 size={16} aria-hidden />
        </button>
        <button
          type="button"
          disabled={!altered}
          onClick={() => {
            onCropping(undefined);
            room.reset();
          }}
          className={`${button} ml-auto`}
        >
          {t('image.reset')}
        </button>
      </div>

      <Section title={t('image.cropping')}>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            aria-pressed={cropping !== undefined}
            onClick={() => {
              onTool(null);
              onCropping(cropping === undefined ? null : undefined);
            }}
            className={`${button} aria-pressed:bg-selected`}
          >
            <Crop size={16} aria-hidden />
            {t('image.crop')}
          </button>
          {edits.crop && (
            <button type="button" onClick={() => room.change({ crop: null })} className={button}>
              {t('image.uncrop')}
            </button>
          )}
        </div>
        {cropping !== undefined && (
          <div role="radiogroup" aria-label={t('image.ratio')} className="flex flex-wrap gap-1">
            {RATIOS.map((ratio) => (
              <button
                key={String(ratio)}
                type="button"
                role="radio"
                aria-checked={cropping === ratio}
                onClick={() => ratioChosen(ratio)}
                className={`${button} aria-checked:bg-selected`}
              >
                {RATIO_LABELS.get(ratio) ?? t('image.ratio.free')}
              </button>
            ))}
          </div>
        )}
      </Section>

      <Section title={t('image.turn')}>
        <div className="flex gap-1">
          {iconAction('pages.turnLeft', RotateCcw, () => room.change(turnedShown(edits, -90)))}
          {iconAction('pages.turnRight', RotateCw, () => room.change(turnedShown(edits, 90)))}
          {iconAction('image.flipAcross', TrianglesCenterlineDashedVertical, () =>
            room.change({ flip: !edits.flip }),
          )}
          {iconAction('image.flipDown', TrianglesCenterlineDashedHorizontal, () =>
            room.change(mirroredDown(edits)),
          )}
        </div>
      </Section>

      <Section title={t('explorer.size')}>
        <select
          aria-label={t('explorer.size')}
          value={edits.side ?? ''}
          onChange={(event) =>
            room.change({ side: event.target.value ? Number(event.target.value) : null })
          }
          className={smallField}
        >
          <option value="">{`${t('image.side.original')} (${dimensions(cropped)})`}</option>
          {sides.map((side) => (
            <option key={side} value={side}>
              {t('image.side.at').replace('{side}', formatNumber(side))}
            </option>
          ))}
        </select>
        <p className="text-sm text-muted">
          {t('image.result').replace('{size}', dimensions(result))}
        </p>
      </Section>

      <Section title={t('image.tone')}>
        {TONES.map((tone) => (
          <label key={tone} className="flex items-center gap-2 text-sm">
            <span className="w-24">{t(`image.${tone}`)}</span>
            <input
              type="range"
              min={0}
              max={2}
              step={0.01}
              value={edits[tone]}
              onChange={(event) => onToning({ [tone]: Number(event.target.value) })}
              onPointerUp={toned(tone)}
              onKeyUp={toned(tone)}
              onBlur={toned(tone)}
              className="min-w-0 flex-1"
            />
            <span className="w-12 text-right tabular-nums">
              {t('image.percent').replace('{value}', formatNumber(Math.round(edits[tone] * 100)))}
            </span>
          </label>
        ))}
      </Section>

      <Section title={t('image.marks')}>
        <div className="flex gap-1">
          {TOOLS.map((each) => {
            const Icon = TOOL_ICONS[each];
            return (
              <button
                key={each}
                type="button"
                aria-label={t(`image.mark.${each}`)}
                title={t(`image.mark.${each}`)}
                aria-pressed={tool === each}
                onClick={() => {
                  onCropping(undefined);
                  onTool(tool === each ? null : each);
                }}
                className={`${iconButton} aria-pressed:bg-selected`}
              >
                <Icon size={16} aria-hidden />
              </button>
            );
          })}
        </div>
        {tool && tool !== 'blur' && (
          <>
            <div className="flex flex-wrap gap-0.5">
              <ColorChoice pen={pen} onPen={onPen} />
            </div>
            <div className="flex gap-0.5">
              <WidthChoice pen={pen} onPen={onPen} />
            </div>
          </>
        )}
      </Section>

      <button type="button" disabled={!altered} onClick={onSave} className={`${button} self-start`}>
        {save}
      </button>
      {failure && (
        <p role="alert" className="text-sm text-danger">
          {failure}
        </p>
      )}
    </Panel>
  );
}
