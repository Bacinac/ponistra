import { CheckCheck, ChevronDown, FlipVertical2, X, type LucideIcon } from 'lucide-react';
import {
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';
import { between } from './explorer';
import { useI18n } from './i18n';
import { Menu, MenuItem, MenuSeparator } from './menu';
import { scrollerOf, steady, useLongPress } from './press';
import { iconButton } from './styles';

/** What the element that opens a row takes: a long press or a Ctrl-click starts the choice, a click
    or Space then adds to it, Shift a range. */
let toggled: EventTarget | null = null;
let opening = false;

export function rowOpener(
  press: ReturnType<typeof useLongPress>[0],
  pressed: () => boolean,
  many: number,
  toggle: (range: boolean) => void,
) {
  return {
    ...press(() => toggle(false)),
    draggable: false,
    onClick: (event: MouseEvent) => {
      if (opening) return;
      if (event.detail > 1 || pressed()) {
        event.preventDefault();
        return;
      }
      const choosing = many > 0 || event.ctrlKey || event.metaKey;
      toggled = choosing ? event.currentTarget : null;
      if (!choosing) return;
      event.preventDefault();
      steady(event.currentTarget, () => toggle(event.shiftKey));
    },
    onDoubleClick: (event: MouseEvent<HTMLElement>) => {
      if (toggled !== event.currentTarget) return;
      toggled = null;
      opening = true;
      event.currentTarget.click();
      opening = false;
    },
    onKeyDown: (event: KeyboardEvent) => {
      if (event.key !== ' ') return;
      event.preventDefault();
      toggle(event.shiftKey);
    },
  };
}

/** The keys of a list being chosen from. A menu or dialog opened from the list sends its keys here
    through its portal, and a field keeps its own. */
export function choiceKeys(
  event: KeyboardEvent,
  many: number,
  { clear, all, remove }: { clear: () => void; all: () => void; remove?: () => void },
) {
  const target = event.target as HTMLElement;
  if (!event.currentTarget.contains(target)) return;
  if (target.closest('input:not([type=checkbox]), textarea, select, [contenteditable]')) return;
  if (event.key === 'Escape' && many > 0) clear();
  if (event.key === 'Delete' && many > 0) remove?.();
  if (event.key === 'a' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    all();
  }
}

/** The rows chosen in a list: a long press or a Ctrl-click starts the choice, a click then adds to
    it, Shift a range; while nothing is chosen a click opens the row as before. */
export function useChoice<Id extends string | number>(ids: readonly Id[]) {
  const [picked, setPicked] = useState<ReadonlySet<Id>>(() => new Set());
  const [anchor, setAnchor] = useState<Id | null>(null);
  const [press, pressed] = useLongPress();
  const chosen = ids.filter((id) => picked.has(id));
  const many = chosen.length;
  const choose = (next: Iterable<Id>, from: Id | null = null) => {
    setPicked(new Set(next));
    setAnchor(from);
  };
  const toggle = (id: Id, range = false) => {
    const next = new Set(chosen);
    const on = !next.has(id);
    const reached = range && anchor !== null && ids.includes(anchor);
    for (const each of reached ? between([...ids], anchor, id) : [id]) {
      if (on) next.add(each);
      else next.delete(each);
    }
    choose(next, id);
  };
  return {
    chosen,
    many,
    anchor,
    has: (id: Id) => picked.has(id),
    choose,
    toggle,
    press,
    pressed,
    /** What the element that opens a row takes. */
    opener: (id: Id) => rowOpener(press, pressed, many, (range) => toggle(id, range)),
    onKeyDown: (event: KeyboardEvent, remove?: () => void) =>
      choiceKeys(event, many, { clear: () => choose([]), all: () => choose(ids), remove }),
    all: {
      every: many > 0 && many === ids.length,
      many,
      total: ids.length,
      onChange: () => choose(many > 0 && many === ids.length ? [] : ids),
      onAll: () => choose(ids),
      onInvert: () => choose(ids.filter((id) => !picked.has(id))),
      onClear: () => choose([]),
    } satisfies All,
  };
}

export type Choice<Id extends string | number> = ReturnType<typeof useChoice<Id>>;

export interface All {
  every: boolean;
  many: number;
  /** How many the whole list holds, which may be more than it has loaded. */
  total: number;
  onChange: () => void;
  onAll: () => void;
  onInvert: () => void;
  onClear: () => void;
}

/** The box that chooses every row or none, and its menu: all, the other ones, none. */
function SelectAll({
  every,
  many,
  total,
  onChange,
  onAll,
  onInvert,
  onClear,
  more,
}: All & { more?: ReactNode }) {
  const { t, formatNumber } = useI18n();
  return (
    <>
      <input
        type="checkbox"
        checked={every}
        ref={(box) => {
          if (box) box.indeterminate = many > 0 && !every;
        }}
        onChange={onChange}
        aria-label={t('explorer.selectAll')}
        className="align-middle"
      />
      <Menu
        align="start"
        trigger={
          <button
            type="button"
            aria-label={t('explorer.selectMenu')}
            title={t('explorer.selectMenu')}
            className={iconButton}
          >
            <ChevronDown size={16} aria-hidden />
          </button>
        }
      >
        <MenuItem
          icon={CheckCheck}
          label={`${t('explorer.selectAll')} (${formatNumber(total)})`}
          onSelect={onAll}
        />
        {more}
        <MenuItem icon={FlipVertical2} label={t('explorer.invert')} onSelect={onInvert} />
        <MenuSeparator />
        <MenuItem icon={X} label={t('explorer.clear')} disabled={many === 0} onSelect={onClear} />
      </Menu>
    </>
  );
}

function ChosenCount({ many }: { many: number }) {
  const { t, formatNumber } = useI18n();
  return (
    <span className="ml-auto pr-2 text-sm whitespace-nowrap text-muted">
      {t('explorer.selected')}: {formatNumber(many)}
    </span>
  );
}

/** The bar atop a list while rows are chosen: all or none, what can be done to them, how many. It
    stays in sight while the list scrolls; `over` lays it on the table's head instead of above. */
export function ChoiceBar({
  all,
  more,
  above,
  over = false,
  children,
}: {
  all: All;
  more?: ReactNode;
  above?: ReactNode;
  over?: boolean;
  children: ReactNode;
}) {
  const bar = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const scroller = scrollerOf(bar.current!);
    // A browser keeps a sticky element clear of its scroller's padding, and rows would show there.
    if (scroller) bar.current!.style.top = `-${getComputedStyle(scroller).paddingTop}`;
  }, []);
  return (
    <div
      ref={bar}
      data-choice-bar
      onClick={(event) => event.stopPropagation()}
      className={`sticky top-0 z-20 bg-surface ${over ? '-mb-10' : ''}`}
    >
      {above}
      <div
        className={`flex items-center gap-1 border-b border-line ${over ? 'h-10 pl-3' : 'min-h-10 flex-wrap py-1 pl-2'}`}
      >
        <SelectAll {...all} more={more} />
        {children}
        <ChosenCount many={all.many} />
      </div>
    </div>
  );
}

/** One thing a row or the rows chosen can have done, as the bar's button and the row's menu item. */
export interface RowAction {
  icon: LucideIcon;
  label: string;
  disabled?: boolean;
  onSelect: () => void;
}

export function ActionButtons({ actions }: { actions: RowAction[] }) {
  return actions.map(({ icon: Icon, label, disabled, onSelect }) => (
    <button
      key={label}
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onSelect}
      className={iconButton}
    >
      <Icon size={16} aria-hidden />
    </button>
  ));
}

export function ActionItems({ actions }: { actions: RowAction[] }) {
  return actions.map((action) => <MenuItem key={action.label} {...action} />);
}

export function ChoiceBox({
  checked,
  onToggle,
  className = '',
}: {
  checked: boolean;
  onToggle: (range: boolean) => void;
  className?: string;
}) {
  const { t } = useI18n();
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={(event) => {
        const range = (event.nativeEvent as globalThis.MouseEvent).shiftKey;
        steady(event.currentTarget.closest('li, tr') ?? event.currentTarget, () => onToggle(range));
      }}
      onClick={(event) => event.stopPropagation()}
      aria-label={t('explorer.select')}
      className={`shrink-0 ${className}`}
    />
  );
}
