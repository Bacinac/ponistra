import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import {
  ChartColumn,
  Ellipsis,
  FileText,
  Image,
  ListTree,
  PanelBottom,
  PanelTop,
  Plus,
  RectangleHorizontal,
  Table2,
  type LucideIcon,
} from 'lucide-react';
import {
  Fragment,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
} from 'react';
import { useI18n } from '../i18n';
import { shortcutLabel } from '../keys';
import { Menu, MenuItem, MenuSeparator, MenuSub } from '../menu';
import { iconButton } from '../styles';
import type { Context, EditorCommand, Group, Where } from './command';
import {
  available,
  commandOf,
  inGroup,
  labelOf,
  layoutCommands,
  perform,
  PLACED_GROUPS,
  refocus,
  styleCommands,
  whereOf,
} from './commands';
import type { Undo } from './history';
import { inList } from './lists';
import { NameBox } from './NameBox';
import { hasProposals } from './proposals';

function useHistory(history: Undo): void {
  const [, setVersion] = useState(0);
  useEffect(() => history.subscribe(() => setVersion((version) => version + 1)), [history]);
}

export function run(command: EditorCommand, context: Context): void {
  if (perform(command, context)) refocus(context);
}

export function titled(label: string, keys?: readonly string[]): string {
  return keys?.length ? `${label} (${shortcutLabel(keys[0])})` : label;
}

function CommandButton({ command, context }: { command: EditorCommand; context: Context }) {
  const { t } = useI18n();
  const label = labelOf(command, t);
  return (
    <button
      type="button"
      aria-label={label}
      title={titled(label, command.keys)}
      aria-pressed={command.active?.(context)}
      disabled={!available(command, context)}
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => run(command, context)}
      className={`${iconButton} aria-pressed:bg-selected aria-pressed:text-accent disabled:opacity-40`}
    >
      <command.icon size={16} aria-hidden />
    </button>
  );
}

const PICKER = { rows: 8, columns: 10 };
const STEPS: Record<string, [number, number]> = {
  ArrowUp: [-1, 0],
  ArrowDown: [1, 0],
  ArrowLeft: [0, -1],
  ArrowRight: [0, 1],
};

function SizePicker({ onPick }: { onPick: (rows: number, columns: number) => void }) {
  const { formatNumber } = useI18n();
  const [size, setSize] = useState({ rows: 1, columns: 1 });
  const grid = useRef<HTMLDivElement>(null);
  const named = (rows: number, columns: number) =>
    `${formatNumber(columns)} × ${formatNumber(rows)}`;

  function move(event: KeyboardEvent, rows: number, columns: number) {
    const step = STEPS[event.key];
    if (!step) return;
    const [row, column] = [rows + step[0], columns + step[1]];
    // Left from the first column is left to the menu, which closes the submenu there.
    if (column < 1) return;
    event.preventDefault();
    event.stopPropagation();
    grid.current?.querySelector<HTMLElement>(`[data-size="${row}:${column}"]`)?.focus();
  }

  return (
    <div className="flex flex-col gap-1 p-1">
      <div ref={grid} className="grid grid-cols-10 gap-0.5">
        {Array.from({ length: PICKER.rows }, (_, r) =>
          Array.from({ length: PICKER.columns }, (_, c) => {
            const [rows, columns] = [r + 1, c + 1];
            const within = rows <= size.rows && columns <= size.columns;
            return (
              <DropdownMenu.Item
                key={`${rows}:${columns}`}
                data-size={`${rows}:${columns}`}
                aria-label={named(rows, columns)}
                onFocus={() => setSize({ rows, columns })}
                onKeyDown={(event) => move(event, rows, columns)}
                onSelect={() => onPick(rows, columns)}
                className={`size-4 rounded-sm border outline-none ${within ? 'border-focus bg-selected' : 'border-line'}`}
              />
            );
          }),
        )}
      </div>
      <p className="text-center text-sm text-muted">{named(size.rows, size.columns)}</p>
    </div>
  );
}

export function CommandItem({
  command,
  label,
  context,
}: {
  command: EditorCommand;
  label: string;
  context: Context;
}) {
  const { t } = useI18n();
  const disabled = !available(command, context);
  if (command.sub) {
    return (
      <MenuSub
        icon={command.icon}
        label={label}
        disabled={disabled}
        hint={disabled && command.why ? t(command.why) : undefined}
      >
        {(typeof command.sub === 'string' ? [command.sub] : command.sub)
          .map(inGroup)
          .map((commands, at) => (
            <Fragment key={at}>
              {at > 0 && <MenuSeparator />}
              {commands.map((each) => (
                <CommandItem
                  key={each.id}
                  command={each}
                  label={each.sample ?? t(each.detail ?? each.label)}
                  context={context}
                />
              ))}
            </Fragment>
          ))}
      </MenuSub>
    );
  }
  return command.sized ? (
    <MenuSub icon={command.icon} label={label} disabled={disabled}>
      <SizePicker onPick={(rows, columns) => command.sized!(context, rows, columns)} />
    </MenuSub>
  ) : (
    <MenuItem
      icon={command.icon}
      swatch={command.swatch}
      label={label}
      shortcut={command.keys && shortcutLabel(command.keys[0])}
      disabled={disabled}
      hint={disabled && command.why ? t(command.why) : undefined}
      checked={command.active?.(context)}
      onSelect={() => run(command, context)}
    />
  );
}

function CommandMenu({
  group,
  label,
  icon: Icon,
  labelled = false,
  context,
}: {
  /** Several groups follow one another between separators. */
  group: Group | readonly Group[];
  label: string;
  icon: LucideIcon;
  labelled?: boolean;
  context: Context;
}) {
  const { t } = useI18n();
  const groups = (typeof group === 'string' ? [group] : group).map(inGroup);
  const commands = groups.flat();
  return (
    <Menu
      onCloseFocus={() => refocus(context)}
      trigger={
        <button
          type="button"
          aria-label={labelled ? undefined : label}
          title={label}
          disabled={!commands.some((command) => available(command, context))}
          className={`${iconButton} inline-flex items-center gap-1 text-sm disabled:opacity-40`}
        >
          <Icon size={16} aria-hidden />
          {labelled && label}
        </button>
      }
    >
      {groups.map((commands, at) => (
        <Fragment key={at}>
          {at > 0 && <MenuSeparator />}
          {commands.map((command) => (
            <CommandItem
              key={command.id}
              command={command}
              label={command.sample ?? t(command.detail ?? command.label)}
              context={context}
            />
          ))}
        </Fragment>
      ))}
    </Menu>
  );
}

const separator = <span aria-hidden className="mx-1 h-5 w-px bg-line" />;

const PLACED: Record<Exclude<Where, 'text'>, LucideIcon> = {
  table: Table2,
  image: Image,
  pdf: FileText,
  chart: ChartColumn,
  note: PanelBottom,
  part: PanelTop,
};

interface Segment {
  key: string;
  node: ReactNode;
  commands: EditorCommand[];
  /** Of the place the user is in, so it stays in the row while the others go under ⋯. */
  kept?: boolean;
}

const MORE_WIDTH = 40;
const WIDE = '(min-width: 48rem)';

function useWide(): boolean {
  return useSyncExternalStore(
    (changed) => {
      const query = matchMedia(WIDE);
      query.addEventListener('change', changed);
      return () => query.removeEventListener('change', changed);
    },
    () => matchMedia(WIDE).matches,
  );
}

/** Which segments fit in the row, null where all do: those kept, then the others in order until
 * one does not; the rest go under ⋯. */
function useFit(row: RefObject<HTMLDivElement | null>, segments: Segment[]): Set<number> | null {
  const layout = segments.map((segment) => `${segment.key}${segment.kept ? '!' : ''}`).join();
  const [shown, setShown] = useState<string | null>(null);
  useLayoutEffect(() => {
    const element = row.current!;
    const kept = layout.split(',').map((key) => key.endsWith('!'));
    const fit = () => {
      const widths = [...element.querySelectorAll<HTMLElement>(':scope > [data-segment]')].map(
        (segment) => segment.offsetWidth,
      );
      const room = element.clientWidth;
      if (widths.reduce((sum, width) => sum + width, 0) <= room) return setShown(null);
      let used = MORE_WIDTH;
      const fits = new Set<number>();
      const take = (at: number) => {
        used += widths[at];
        fits.add(at);
      };
      for (const [at, width] of widths.entries()) if (kept[at] && used + width <= room) take(at);
      for (const [at, width] of widths.entries()) {
        if (kept[at]) continue;
        if (used + width > room) break;
        take(at);
      }
      setShown([...fits].sort((a, b) => a - b).join());
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(element);
    return () => observer.disconnect();
  }, [row, layout]);
  return useMemo(
    () => (shown === null ? null : new Set(shown ? shown.split(',').map(Number) : [])),
    [shown],
  );
}

export function Toolbar({ context }: { context: Context }) {
  const { t } = useI18n();
  useHistory(context.history);
  const row = useRef<HTMLDivElement>(null);
  const wide = useWide();
  const buttons = (group: Group) =>
    inGroup(group).map((command) => (
      <CommandButton key={command.id} command={command} context={context} />
    ));
  const styles = [...inGroup('style'), ...styleCommands(context.styling)];
  const style = styles.find((command) => command.active?.(context));
  const alignments = inGroup('align');
  const alignment = alignments.find((command) => command.active?.(context)) ?? alignments[0];
  const forms = inList(context.view.state, 'bullet') ? 'bulletForm' : 'numberForm';
  const where = whereOf(context);
  const reviewing = hasProposals(context.view.state);
  const review = inGroup('review').filter((command) => reviewing || available(command, context));
  const layouts = context.slides ? layoutCommands(context.slides) : [];
  const layout = layouts.find((command) => command.active?.(context));
  const segments: Segment[] = [
    ...(where === 'table' && wide
      ? [
          {
            key: 'nameBox',
            node: <NameBox context={context} />,
            commands: [commandOf('table.goTo')!],
            kept: true,
          },
        ]
      : []),
    { key: 'history', node: buttons('history'), commands: inGroup('history') },
    ...(context.slides
      ? [
          {
            key: 'slide',
            node: (
              <>
                <select
                  aria-label={t('commandGroup.slideLayout')}
                  value={layout?.id ?? ''}
                  disabled={!layouts.some((command) => available(command, context))}
                  onChange={(event) => {
                    const chosen = layouts.find((command) => command.id === event.target.value);
                    if (chosen) run(chosen, context);
                  }}
                  className="rounded px-2 py-1 text-sm hover:bg-hover disabled:opacity-40"
                >
                  {!layout && <option value="" hidden />}
                  {layouts.map((command) => (
                    <option key={command.id} value={command.id}>
                      {labelOf(command, t)}
                    </option>
                  ))}
                </select>
                {buttons('slide')}
                <CommandMenu
                  group="slideSize"
                  label={t('commandGroup.slideSize')}
                  icon={RectangleHorizontal}
                  context={context}
                />
              </>
            ),
            commands: [...layouts, ...inGroup('slide'), ...inGroup('slideSize')],
          },
        ]
      : []),
    {
      key: 'style',
      node: (
        <select
          aria-label={t('editor.style')}
          value={style?.id ?? ''}
          disabled={!styles.some((command) => available(command, context) || command === style)}
          onChange={(event) => {
            const chosen = styles.find((command) => command.id === event.target.value);
            if (chosen) run(chosen, context);
          }}
          className="rounded px-2 py-1 text-sm hover:bg-hover disabled:opacity-40"
        >
          {!style && <option value="" hidden />}
          {styles.map((command) => (
            <option key={command.id} value={command.id}>
              {labelOf(command, t)}
            </option>
          ))}
        </select>
      ),
      commands: styles,
    },
    { key: 'format', node: buttons('format'), commands: inGroup('format') },
    {
      key: 'color',
      node: (['color', 'highlight'] as const).map((group) => (
        <CommandMenu
          key={group}
          group={group}
          label={t(`commandGroup.${group}`)}
          icon={inGroup(group)[0].icon}
          context={context}
        />
      )),
      commands: [...inGroup('color'), ...inGroup('highlight')],
    },
    {
      key: 'paragraph',
      node: (
        <>
          {buttons('list')}
          <CommandMenu
            group={[forms, 'numbering']}
            label={t('editor.listForm')}
            icon={ListTree}
            context={context}
          />
          <CommandMenu
            group="align"
            label={t('editor.align')}
            icon={alignment.icon}
            context={context}
          />
          {buttons('indent')}
        </>
      ),
      commands: [
        ...inGroup('list'),
        ...inGroup(forms),
        ...inGroup('numbering'),
        ...alignments,
        ...inGroup('indent'),
      ],
    },
    {
      key: 'insert',
      node: (
        <CommandMenu
          group="insert"
          label={t('editor.insert')}
          icon={Plus}
          labelled
          context={context}
        />
      ),
      commands: inGroup('insert'),
    },
    { key: 'comment', node: buttons('comment'), commands: inGroup('comment') },
    ...(review.some((command) => available(command, context))
      ? [
          {
            key: 'review',
            node: review.map((command) => (
              <CommandButton key={command.id} command={command} context={context} />
            )),
            commands: review,
          },
        ]
      : []),
    ...(where === 'text'
      ? []
      : [
          {
            key: where,
            node: (
              <CommandMenu
                group={PLACED_GROUPS[where]}
                label={t(`commandGroup.${where}`)}
                icon={PLACED[where]}
                labelled
                context={context}
              />
            ),
            commands: PLACED_GROUPS[where].flatMap(inGroup),
            kept: true,
          },
        ]),
  ];
  const shown = useFit(row, segments);
  const hidden = segments.filter((_, index) => shown && !shown.has(index));
  return (
    <div
      ref={row}
      role="toolbar"
      aria-label={t('editor.toolbar')}
      className="relative flex min-w-0 flex-1 items-center"
    >
      {segments.map((segment, index) => (
        <div
          key={segment.key}
          data-segment
          className={`flex shrink-0 items-center gap-0.5 ${!shown || shown.has(index) ? '' : 'invisible absolute'}`}
        >
          {index > 0 && separator}
          {segment.node}
        </div>
      ))}
      {hidden.length > 0 && (
        <div className="flex shrink-0 items-center">
          {separator}
          <Menu
            onCloseFocus={() => refocus(context)}
            trigger={
              <button
                type="button"
                aria-label={t('editor.more')}
                title={t('editor.more')}
                className={iconButton}
              >
                <Ellipsis size={16} aria-hidden />
              </button>
            }
          >
            {hidden.map((segment, index) => (
              <Fragment key={segment.key}>
                {index > 0 && <MenuSeparator />}
                {segment.commands.map((command) => (
                  <CommandItem
                    key={command.id}
                    command={command}
                    label={labelOf(command, t)}
                    context={context}
                  />
                ))}
              </Fragment>
            ))}
          </Menu>
        </div>
      )}
    </div>
  );
}
