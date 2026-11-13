import * as ContextMenu from '@radix-ui/react-context-menu';
import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Check, ChevronRight, Ellipsis, type LucideIcon } from 'lucide-react';
import {
  createContext,
  useContext,
  useRef,
  type FocusEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';
import { useI18n } from './i18n';
import { iconButton, menu, menuItem } from './styles';

/** A chosen item may send the focus elsewhere, such as into a field it opened, but the open menu
 * holds on to it; the element it went for gets it once the menu is gone. */
const FOCUSABLE = 'a[href], button, [tabindex]';

function useCloseFocus(onCloseFocus?: () => void) {
  const sent = useRef<HTMLElement | null>(null);
  return {
    onBlur: (event: FocusEvent<HTMLElement>) => {
      const next = event.relatedTarget;
      if (next instanceof HTMLElement && !event.currentTarget.contains(next)) sent.current = next;
    },
    onCloseAutoFocus: (event: Event) => {
      const next = sent.current;
      sent.current = null;
      if (next?.isConnected) {
        event.preventDefault();
        next.focus();
      } else if (onCloseFocus) {
        event.preventDefault();
        onCloseFocus();
      }
    },
  };
}

export function Menu({
  trigger,
  align = 'end',
  onCloseFocus,
  children,
}: {
  trigger: ReactNode;
  align?: 'start' | 'end';
  onCloseFocus?: () => void;
  children: ReactNode;
}) {
  const closeFocus = useCloseFocus(onCloseFocus);
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>{trigger}</DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align={align} sideOffset={4} {...closeFocus} className={menu}>
          {children}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

const InContextMenu = createContext(false);

export function ContextMenuArea({
  items,
  onOpen,
  onCloseFocus,
  children,
}: {
  items: ReactNode;
  onOpen?: (event: MouseEvent) => void;
  onCloseFocus?: () => void;
  children: ReactNode;
}) {
  const trigger = useRef<HTMLElement | null>(null);
  const closeFocus = useCloseFocus(
    onCloseFocus ??
      (() => {
        const row = trigger.current;
        const target = row?.matches(FOCUSABLE) ? row : row?.querySelector<HTMLElement>(FOCUSABLE);
        target?.focus({ preventScroll: true });
      }),
  );
  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger
        asChild
        onContextMenu={(event) => {
          trigger.current = event.currentTarget as HTMLElement;
          onOpen?.(event);
        }}
      >
        {children}
      </ContextMenu.Trigger>
      <ContextMenu.Portal>
        <ContextMenu.Content {...closeFocus} className={menu}>
          <InContextMenu value>{items}</InContextMenu>
        </ContextMenu.Content>
      </ContextMenu.Portal>
    </ContextMenu.Root>
  );
}

export function ActionsMenu({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const trigger = (
    <button type="button" aria-label={t('tree.actions')} className={iconButton}>
      <Ellipsis size={16} />
    </button>
  );
  return <Menu trigger={trigger}>{children}</Menu>;
}

export function MenuItem({
  icon: Icon,
  swatch,
  label,
  shortcut,
  onSelect,
  disabled,
  hint,
  checked,
}: {
  icon: LucideIcon;
  swatch?: string;
  label: string;
  shortcut?: string;
  onSelect: () => void;
  disabled?: boolean;
  /** Why the item is disabled, under its label. */
  hint?: string;
  /** Whether what the item does is in force, for an item that says so. */
  checked?: boolean;
}) {
  const Kind = useContext(InContextMenu) ? ContextMenu : DropdownMenu;
  const content = (
    <>
      {swatch ? (
        <span
          aria-hidden
          style={{ background: swatch }}
          className="size-4 rounded-sm border border-line"
        />
      ) : (
        <Icon size={16} aria-hidden className="text-muted" />
      )}
      {hint ? (
        <span className="flex flex-col">
          {label}
          <span className="text-xs text-muted">{hint}</span>
        </span>
      ) : (
        label
      )}
      {shortcut && <kbd className="ml-auto pl-4 font-sans text-xs text-muted">{shortcut}</kbd>}
      {checked && <Check size={16} aria-hidden className={shortcut ? 'ml-2' : 'ml-auto'} />}
    </>
  );
  return checked === undefined ? (
    <Kind.Item className={menuItem} onSelect={onSelect} disabled={disabled}>
      {content}
    </Kind.Item>
  ) : (
    <Kind.CheckboxItem
      className={menuItem}
      onSelect={onSelect}
      disabled={disabled}
      checked={checked}
    >
      {content}
    </Kind.CheckboxItem>
  );
}

/** Emoji the user picks from at a glance, side by side on one line of the menu. */
export function MenuEmojis({
  emojis,
  label,
  onSelect,
}: {
  emojis: readonly string[];
  label: string;
  onSelect: (emoji: string) => void;
}) {
  const Kind = useContext(InContextMenu) ? ContextMenu : DropdownMenu;
  return (
    <Kind.Group aria-label={label} className="flex gap-0.5 pb-1">
      {emojis.map((emoji) => (
        <Kind.Item
          key={emoji}
          onSelect={() => onSelect(emoji)}
          className="cursor-default rounded p-1.5 text-xl leading-none outline-none data-highlighted:bg-hover"
        >
          {emoji}
        </Kind.Item>
      ))}
    </Kind.Group>
  );
}

export function MenuSub({
  icon: Icon,
  label,
  disabled,
  hint,
  children,
}: {
  icon: LucideIcon;
  label: string;
  disabled?: boolean;
  hint?: string;
  children: ReactNode;
}) {
  const Kind = useContext(InContextMenu) ? ContextMenu : DropdownMenu;
  return (
    <Kind.Sub>
      <Kind.SubTrigger className={menuItem} disabled={disabled}>
        <Icon size={16} aria-hidden className="text-muted" />
        {hint ? (
          <span className="flex flex-col">
            {label}
            <span className="text-xs text-muted">{hint}</span>
          </span>
        ) : (
          label
        )}
        <ChevronRight size={14} aria-hidden className="ml-auto text-muted" />
      </Kind.SubTrigger>
      <Kind.Portal>
        <Kind.SubContent sideOffset={4} className={menu}>
          {children}
        </Kind.SubContent>
      </Kind.Portal>
    </Kind.Sub>
  );
}

export function MenuChoices<T extends string>({
  value,
  choices,
  onChange,
}: {
  value: T;
  choices: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <DropdownMenu.RadioGroup value={value} onValueChange={(next) => onChange(next as T)}>
      {choices.map((choice) => (
        <DropdownMenu.RadioItem key={choice.value} value={choice.value} className={menuItem}>
          <span className="w-4">
            <DropdownMenu.ItemIndicator>
              <Check size={16} aria-hidden />
            </DropdownMenu.ItemIndicator>
          </span>
          {choice.label}
        </DropdownMenu.RadioItem>
      ))}
    </DropdownMenu.RadioGroup>
  );
}

export function MenuSeparator() {
  const Separator = useContext(InContextMenu) ? ContextMenu.Separator : DropdownMenu.Separator;
  return <Separator className="my-1 h-px bg-line" />;
}
