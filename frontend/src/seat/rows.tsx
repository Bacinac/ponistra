import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight, LoaderCircle, type LucideIcon } from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { button } from '../styles';
import { act } from './api';
import { failure } from './failure';

/** One entry of a list on the seat screen: what it is at a glance, what can be done with it
 * once opened. */
export function Row({
  icon: Icon,
  name,
  state,
  marks,
  open,
  onToggle,
  children,
}: {
  icon: LucideIcon;
  name: string;
  state?: string;
  marks?: ReactNode;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const id = useId();
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <li className="rounded border border-line bg-raised">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={onToggle}
        className="flex w-full min-w-0 items-center gap-3 rounded px-3 py-2.5 text-left hover:bg-hover"
      >
        <Icon size={18} aria-hidden className="shrink-0" />
        <span className="min-w-0 flex-1 truncate">{name}</span>
        {marks}
        {state && <span className="shrink-0 text-sm text-muted">{state}</span>}
        <Chevron size={16} aria-hidden className="shrink-0 text-muted" />
      </button>
      {open && (
        <div id={id} className="flex flex-col gap-3 border-t border-line px-3 py-3">
          {children}
        </div>
      )}
    </li>
  );
}

export interface Action {
  path: string;
  body: object;
  /** What a status means for this action, where it says more than the general words. */
  own?: Partial<Record<number, MessageKey>>;
}

/** The agent's actions on one entry: one at a time, the list read again once it has answered. */
export function useAction(list: readonly unknown[], done?: () => void) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const mutation = useMutation<void, Error, Action>({
    mutationFn: ({ path, body }) => act(path, body),
    onSuccess: done,
    onSettled: () => queryClient.invalidateQueries({ queryKey: list }),
  });
  const error = mutation.error && failure(mutation.error, t, mutation.variables?.own);
  return { ...mutation, message: error || null };
}

/** A button of an entry's action, turning into its progress while the agent works on it. */
export function ActionButton({
  label,
  busy,
  disabled,
  onClick,
  look = button,
  type = 'button',
}: {
  label: string;
  busy?: string | false;
  disabled?: boolean;
  onClick?: () => void;
  look?: string;
  type?: 'button' | 'submit';
}) {
  return (
    <button type={type} className={look} disabled={disabled} onClick={onClick}>
      {busy && <LoaderCircle size={16} aria-hidden className="animate-spin" />}
      {busy || label}
    </button>
  );
}

export function Problem({ message }: { message: string | null }) {
  return message ? (
    <p role="alert" className="text-sm text-danger">
      {message}
    </p>
  ) : null;
}
