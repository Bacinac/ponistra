import {
  AlignHorizontalJustifyCenter,
  ArrowLeftToLine,
  ArrowRightToLine,
  DecimalsArrowRight,
  Ellipsis,
  Minus,
  Ruler as RulerIcon,
  Trash2,
  Underline,
  X,
  type LucideIcon,
} from 'lucide-react';
import {
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  type SyntheticEvent,
} from 'react';
import type { Command } from 'prosemirror-state';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { ContextMenuArea, MenuItem, MenuSeparator, MenuSub } from '../menu';
import { PX_PER_CM, type PageSetup } from './pages';
import {
  movedEdge,
  movedIndent,
  setIndent,
  snapped,
  SNAP,
  type Edge,
  type IndentMarker,
  type Indents,
} from './rulers';
import { LEADERS, TAB_KINDS, type Leader, type TabKind, type TabStop } from './schema';
import { addStop, moveStop, removeStop, restyleStop } from './stops';

/** The ruler's thickness, in px at any zoom. */
const THICKNESS = 20;

type Shape = IndentMarker | 'edge' | 'stop' | 'tab';

const KIND_ICONS: Record<TabKind, LucideIcon> = {
  left: ArrowRightToLine,
  center: AlignHorizontalJustifyCenter,
  right: ArrowLeftToLine,
  decimal: DecimalsArrowRight,
};
const LEADER_ICONS: Record<Leader | 'none', LucideIcon> = {
  none: X,
  dot: Ellipsis,
  hyphen: Minus,
  underscore: Underline,
};
/** How far past the ruler a dragged tab stop is taken off. */
const OFF = 16;

interface Mark {
  id: string;
  label: MessageKey;
  shape: Shape;
  /** Where it stands, in cm from the ruler's start. */
  at: number;
  /** Where a pointer this far along brings it. */
  settle: (cm: number, free: boolean) => number;
  apply: (at: number) => void;
  /** The length it stands for, as its tooltip shows it. */
  value: (at: number) => number;
  /** The marks that move with it. */
  carries?: readonly string[];
  /** Takes it off, where it may be dragged off the ruler. */
  remove?: () => void;
  /** What its own menu offers. */
  menu?: ReactNode;
  look?: string;
}

interface Drag {
  id: string;
  at: number;
  box: DOMRect;
  off: boolean;
}

function Ruler({
  axis,
  length,
  text,
  origin,
  bands = [],
  marks,
  scale,
  readOnly,
  label,
  onAdd,
  onMenuClose,
}: {
  axis: 'x' | 'y';
  length: number;
  text: readonly [number, number];
  /** Where it counts from: the text's left or top edge. */
  origin: number;
  bands?: readonly (readonly [number, number])[];
  marks: readonly Mark[];
  scale: number;
  readOnly: boolean;
  label: string;
  /** A click on the ruler itself, this far along. */
  onAdd?: (cm: number, free: boolean) => void;
  onMenuClose?: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const track = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const unit = PX_PER_CM * scale;
  const across = axis === 'x';
  const along = (cm: number) => (across ? { left: cm * unit } : { top: cm * unit });
  const span = ([from, to]: readonly [number, number]) =>
    across
      ? { left: from * unit, width: (to - from) * unit }
      : { top: from * unit, height: (to - from) * unit };
  const dragged = drag && marks.find((mark) => mark.id === drag.id);
  const shift = dragged ? drag.at - dragged.at : 0;
  const shown = (mark: Mark) =>
    dragged && (mark === dragged || dragged.carries?.includes(mark.id)) ? mark.at + shift : mark.at;

  /** Whether an event is the ruler's own, not one from a mark's menu, which React passes up
   * through its portal. */
  const own = (event: SyntheticEvent) => event.currentTarget.contains(event.target as Node);
  const pointed = (event: PointerEvent, box: DOMRect) =>
    (across ? event.clientX - box.left : event.clientY - box.top) / unit;
  const start = (mark: Mark) => (event: PointerEvent<HTMLElement>) => {
    if (readOnly || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ id: mark.id, at: mark.at, box: track.current!.getBoundingClientRect(), off: false });
  };
  const move = (mark: Mark) => (event: PointerEvent) => {
    if (drag?.id !== mark.id) return;
    const at = mark.settle(pointed(event, drag.box), event.altKey);
    const [near, far] = across ? [drag.box.top, drag.box.bottom] : [drag.box.left, drag.box.right];
    const sideways = across ? event.clientY : event.clientX;
    const off = Boolean(mark.remove) && (sideways < near - OFF || sideways > far + OFF);
    if (at !== drag.at || off !== drag.off) setDrag({ ...drag, at, off });
  };
  const end = (mark: Mark) => () => {
    if (drag?.id !== mark.id) return;
    setDrag(null);
    if (drag.off) mark.remove?.();
    else if (drag.at !== mark.at) mark.apply(drag.at);
  };
  const nudge = (mark: Mark) => (event: KeyboardEvent) => {
    if (readOnly) return;
    if (mark.remove && (event.key === 'Delete' || event.key === 'Backspace')) {
      event.preventDefault();
      mark.remove();
      return;
    }
    const by = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[event.key];
    if (!by) return;
    event.preventDefault();
    const at = mark.settle(mark.at + by * SNAP, false);
    if (at !== mark.at) mark.apply(at);
  };

  const ticks: { at: number; size: number; number?: number }[] = [];
  const labelled = unit >= 18 ? 4 : 8;
  for (let step = Math.ceil(-origin / SNAP); origin + step * SNAP <= length; step++) {
    if (step === 0) continue;
    const whole = step % 4 === 0;
    ticks.push({
      at: origin + step * SNAP,
      size: whole ? 0 : step % 2 === 0 ? 5 : 3,
      ...(whole && step % labelled === 0 && { number: Math.abs(step / 4) }),
    });
  }
  const size = length * unit;

  return (
    <div
      ref={track}
      role="group"
      aria-label={label}
      className="ponistra-ruler relative shrink-0 bg-line select-none"
      style={across ? { width: size, height: THICKNESS } : { width: THICKNESS, height: size }}
      onMouseDown={(event) => {
        if (!own(event)) return;
        event.preventDefault();
        event.stopPropagation();
      }}
      onPointerDown={(event) => {
        const target = event.target as Element;
        if (readOnly || !onAdd || event.button !== 0 || !own(event)) return;
        if (target.closest('.ponistra-mark')) return;
        onAdd(pointed(event, event.currentTarget.getBoundingClientRect()), event.altKey);
      }}
      onDoubleClick={(event) => event.stopPropagation()}
    >
      <div
        className="absolute bg-raised"
        style={{ ...(across ? { top: 0, bottom: 0 } : { left: 0, right: 0 }), ...span(text) }}
      />
      {bands.map((band, index) => (
        <div
          key={index}
          className="absolute bg-hover"
          style={{ ...(across ? { top: 2, bottom: 2 } : { left: 2, right: 2 }), ...span(band) }}
        />
      ))}
      <svg
        aria-hidden
        className="absolute inset-0 text-muted"
        width={across ? size : THICKNESS}
        height={across ? THICKNESS : size}
      >
        {ticks.map(({ at, size: tick, number }) => {
          const where = at * unit;
          const middle = THICKNESS / 2;
          if (number !== undefined) {
            return (
              <text
                key={at}
                x={across ? where : middle}
                y={across ? middle : where}
                textAnchor="middle"
                dominantBaseline="central"
                fill="currentColor"
                fontSize={9}
              >
                {number}
              </text>
            );
          }
          if (!tick) return null;
          return across ? (
            <line
              key={at}
              x1={where}
              x2={where}
              y1={middle - tick / 2}
              y2={middle + tick / 2}
              stroke="currentColor"
            />
          ) : (
            <line
              key={at}
              y1={where}
              y2={where}
              x1={middle - tick / 2}
              x2={middle + tick / 2}
              stroke="currentColor"
            />
          );
        })}
      </svg>
      {marks.map((mark) => {
        const at = shown(mark);
        const shape = (
          <div
            key={mark.id}
            role="slider"
            tabIndex={readOnly ? -1 : 0}
            aria-label={t(mark.label)}
            aria-orientation={across ? 'horizontal' : 'vertical'}
            aria-valuenow={mark.value(at)}
            aria-valuetext={`${formatNumber(mark.value(at))} cm`}
            aria-disabled={readOnly || undefined}
            title={t(mark.label)}
            className={`ponistra-mark ponistra-mark-${mark.shape} ponistra-mark-${axis} ${mark.look ?? ''} ${drag?.id === mark.id && drag.off ? 'ponistra-mark-off' : ''}`}
            style={along(at)}
            onPointerDown={start(mark)}
            onPointerMove={move(mark)}
            onPointerUp={end(mark)}
            onPointerCancel={() => setDrag(null)}
            onKeyDown={nudge(mark)}
          />
        );
        return mark.menu && !readOnly ? (
          <ContextMenuArea key={mark.id} items={mark.menu} onCloseFocus={onMenuClose}>
            {shape}
          </ContextMenuArea>
        ) : (
          shape
        );
      })}
      {drag && dragged && (
        <>
          <span
            aria-hidden
            className={`ponistra-ruler-guide ponistra-ruler-guide-${axis}`}
            style={
              across
                ? { left: drag.box.left + drag.at * unit, top: drag.box.bottom }
                : { top: drag.box.top + drag.at * unit, left: drag.box.right }
            }
          />
          <span
            className="ponistra-ruler-value"
            style={
              across
                ? { left: drag.at * unit, top: THICKNESS + 4 }
                : { top: drag.at * unit, left: THICKNESS + 4 }
            }
          >
            {formatNumber(dragged.value(drag.at))} cm
          </span>
        </>
      )}
    </div>
  );
}

function edgeMark(
  setup: PageSetup,
  edge: Edge,
  label: MessageKey,
  onSetup: (setup: PageSetup) => void,
): Mark {
  const far = edge === 'right' || edge === 'bottom' || edge === 'footer';
  const size = edge === 'left' || edge === 'right' ? setup.width : setup.height;
  const from = (cm: number) => (far ? size - cm : cm);
  return {
    id: edge,
    label,
    shape: edge === 'header' || edge === 'footer' ? 'stop' : 'edge',
    at: from(setup[edge]),
    settle: (cm, free) => from(movedEdge(setup, edge, snapped(from(cm), free))[edge]),
    apply: (at) => onSetup(movedEdge(setup, edge, from(at))),
    value: from,
  };
}

/** The page's width: its margins, and the indents and tab stops of the paragraphs being
 * written. */
export function HorizontalRuler({
  setup,
  scale,
  paragraph,
  readOnly,
  onSetup,
  onRun,
  onStops,
  onMenuClose,
}: {
  setup: PageSetup;
  scale: number;
  /** The first selected paragraph's, where the text being written spans the page's. */
  paragraph: { indents: Indents; listed: boolean; stops: readonly TabStop[] } | null;
  readOnly: boolean;
  onSetup: (setup: PageSetup) => void;
  /** Runs a command on the selected paragraphs. */
  onRun: (command: Command) => void;
  /** Opens the Tabs dialog on the selected paragraphs. */
  onStops: () => void;
  onMenuClose: () => void;
}) {
  const { t } = useI18n();
  const [kind, setKind] = useState<TabKind>('left');
  const start = setup.left;
  const finish = setup.width - setup.right;
  const width = finish - start;
  const marks = [
    edgeMark(setup, 'left', 'ruler.left', onSetup),
    edgeMark(setup, 'right', 'ruler.right', onSetup),
  ];
  const stopAt = (cm: number, free: boolean) =>
    Math.min(Math.max(snapped(cm - start, free), 0), setup.width - start);
  if (paragraph) {
    const { indents, listed, stops } = paragraph;
    const moved = (marker: IndentMarker, cm: number, free: boolean) =>
      movedIndent(indents, marker, snapped(cm, free), width, listed);
    const indent = (marker: IndentMarker) => (at: number) =>
      onRun(setIndent(marker, marker === 'right' ? finish - at : at - start, width));
    const lines = (marker: IndentMarker): Mark => ({
      id: marker === 'left' ? 'indent' : 'hanging',
      label: marker === 'left' ? 'ruler.indent' : 'ruler.hanging',
      shape: marker,
      at: start + indents.left,
      settle: (cm, free) => start + moved(marker, cm - start, free).left,
      apply: indent(marker),
      value: (at) => at - start,
      carries: marker === 'left' ? ['first', 'hanging'] : ['indent'],
    });
    if (!listed) {
      marks.push({
        id: 'first',
        label: 'ruler.first',
        shape: 'first',
        at: start + indents.left + indents.first,
        settle: (cm, free) => {
          const { left, first } = moved('first', cm - start, free);
          return start + left + first;
        },
        apply: indent('first'),
        value: (at) => at - start,
      });
      marks.push(lines('hanging'));
    }
    marks.push(lines('left'), {
      id: 'indentRight',
      label: 'ruler.indentRight',
      shape: 'right',
      at: finish - indents.right,
      settle: (cm, free) => finish - moved('right', finish - cm, free).right,
      apply: indent('right'),
      value: (at) => finish - at,
    });
    stops.forEach((stop, index) => {
      const restyle = (patch: Partial<Omit<TabStop, 'at'>>) => onRun(restyleStop(stop.at, patch));
      marks.push({
        id: `tab-${index}`,
        label: `ruler.tab.${stop.kind}`,
        shape: 'tab',
        look: `ponistra-stop ponistra-stop-${stop.kind}`,
        at: start + stop.at,
        settle: (cm, free) => start + stopAt(cm, free),
        apply: (at) => onRun(moveStop(stop.at, at - start)),
        value: (at) => at - start,
        remove: () => onRun(removeStop(stop.at)),
        menu: (
          <>
            {TAB_KINDS.map((each) => (
              <MenuItem
                key={each}
                icon={KIND_ICONS[each]}
                label={t(`ruler.tab.${each}`)}
                disabled={each === stop.kind}
                onSelect={() => restyle({ kind: each })}
              />
            ))}
            <MenuSub icon={Ellipsis} label={t('ruler.leader')}>
              {(['none', ...LEADERS] as const).map((each) => (
                <MenuItem
                  key={each}
                  icon={LEADER_ICONS[each]}
                  label={t(`ruler.leader.${each}`)}
                  disabled={each === (stop.leader ?? 'none')}
                  onSelect={() => restyle({ leader: each === 'none' ? undefined : each })}
                />
              ))}
            </MenuSub>
            <MenuItem icon={RulerIcon} label={t('command.tabStops')} onSelect={onStops} />
            <MenuSeparator />
            <MenuItem
              icon={Trash2}
              label={t('ruler.tab.remove')}
              onSelect={() => onRun(removeStop(stop.at))}
            />
          </>
        ),
      });
    });
  }
  return (
    <div className="relative">
      {paragraph && !readOnly && (
        <button
          type="button"
          aria-label={`${t('ruler.tabKind')}: ${t(`ruler.tab.${kind}`)}`}
          title={`${t('ruler.tabKind')}: ${t(`ruler.tab.${kind}`)}`}
          className="ponistra-tab-kind"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => setKind(TAB_KINDS[(TAB_KINDS.indexOf(kind) + 1) % TAB_KINDS.length])}
        >
          <span aria-hidden className={`ponistra-stop ponistra-stop-${kind}`} />
        </button>
      )}
      <Ruler
        axis="x"
        length={setup.width}
        text={[start, finish]}
        origin={start}
        marks={marks}
        scale={scale}
        readOnly={readOnly}
        label={t('ruler.horizontal')}
        onAdd={
          paragraph
            ? (cm, free) => {
                if (cm > start && cm < finish) onRun(addStop({ at: stopAt(cm, free), kind }));
              }
            : undefined
        }
        onMenuClose={onMenuClose}
      />
    </div>
  );
}

/** The page's height: its margins, and how far from its edges its header and footer stand, with
 * the room they take. */
export function VerticalRuler({
  setup,
  scale,
  header,
  footer,
  readOnly,
  onSetup,
}: {
  setup: PageSetup;
  scale: number;
  /** The heights of the page's header and footer, in px. */
  header: number;
  footer: number;
  readOnly: boolean;
  onSetup: (setup: PageSetup) => void;
}) {
  const { t } = useI18n();
  const bottom = setup.height - setup.footer;
  return (
    <Ruler
      axis="y"
      length={setup.height}
      text={[setup.top, setup.height - setup.bottom]}
      origin={setup.top}
      bands={[
        [setup.header, setup.header + header / PX_PER_CM],
        [bottom - footer / PX_PER_CM, bottom],
      ]}
      marks={[
        edgeMark(setup, 'header', 'ruler.header', onSetup),
        edgeMark(setup, 'top', 'ruler.top', onSetup),
        edgeMark(setup, 'bottom', 'ruler.bottom', onSetup),
        edgeMark(setup, 'footer', 'ruler.footer', onSetup),
      ]}
      scale={scale}
      readOnly={readOnly}
      label={t('ruler.vertical')}
    />
  );
}
