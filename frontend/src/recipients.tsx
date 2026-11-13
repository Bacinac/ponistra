import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { useId, useState, type ClipboardEvent, type FocusEvent, type KeyboardEvent } from 'react';
import { getJson } from './api';
import { useI18n } from './i18n';
import { useSettled } from './settled';
import type { Person } from './mailData';

interface Found {
  people: Person[];
  /** The accounts whose organisation's directory did not answer. */
  unanswered: string[];
}

/** The people text written out names, by commas or semicolons outside quotes and angle brackets:
 * `Ana Kovač <ana@example.com>, "Horvat, Iva" <iva@example.com>; marko@example.com`. */
export function written(text: string): Person[] {
  const pieces: string[] = [];
  let piece = '';
  let quoted = false;
  let angled = false;
  for (const each of text) {
    if (each === '"') quoted = !quoted;
    else if (each === '<' && !quoted) angled = true;
    else if (each === '>' && !quoted) angled = false;
    if (!quoted && !angled && (each === ',' || each === ';' || each === '\n')) {
      pieces.push(piece);
      piece = '';
    } else piece += each;
  }
  pieces.push(piece);
  return pieces
    .map((each) => each.trim())
    .filter(Boolean)
    .map((each) => {
      const named = /^"?([^"<]*?)"?\s*<([^>]*)>$/.exec(each);
      return named
        ? { name: named[1].trim(), address: named[2].trim() }
        : { name: '', address: each };
    });
}

function decoded(text: string): string {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
}

/** What a mailto link asks to write (RFC 6068): to whom, with copies, the subject and the text;
 * its `+` stays a plus, as the RFC has it, not a space as in a form. */
export function mailto(link: string) {
  const rest = link.replace(/^mailto:/i, '');
  const at = rest.indexOf('?');
  const asked = {
    to: written(decoded(at < 0 ? rest : rest.slice(0, at))),
    cc: [] as Person[],
    bcc: [] as Person[],
    subject: '',
    text: '',
  };
  for (const field of at < 0 ? [] : rest.slice(at + 1).split('&')) {
    const sign = field.indexOf('=');
    const name = decoded(sign < 0 ? field : field.slice(0, sign)).toLowerCase();
    const value = sign < 0 ? '' : decoded(field.slice(sign + 1));
    if (name === 'to' || name === 'cc' || name === 'bcc') asked[name].push(...written(value));
    else if (name === 'subject') asked.subject = value;
    else if (name === 'body') asked.text = value.replace(/\r\n?/g, '\n');
  }
  return asked;
}

function reachable(address: string): boolean {
  return /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(address);
}

/** The people a message goes to, each a chip: chosen as the user types from the people of their
 * mail and the directory of their organisation, or written out whole; `source` offers others,
 * such as the installation's colleagues alone. */
export function Recipients({
  id,
  people,
  onChange,
  autoFocus,
  source = '/api/mail/people',
}: {
  id: string;
  people: Person[];
  onChange: (people: Person[]) => void;
  autoFocus?: boolean;
  source?: string;
}) {
  const { t } = useI18n();
  const list = useId();
  const [typed, setTyped] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const settled = useSettled(typed.trim(), 150);
  const found = useQuery({
    queryKey: ['people', source, settled],
    queryFn: () => getJson<Found>(`${source}?${new URLSearchParams({ q: settled })}`),
    enabled: settled.length > 0,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
  const chosen = new Set(people.map((each) => each.address.toLowerCase()));
  const offered = typed.trim()
    ? (found.data?.people ?? []).filter((each) => !chosen.has(each.address.toLowerCase()))
    : [];
  const unanswered = typed.trim() ? (found.data?.unanswered ?? []) : [];
  const shown = open && (offered.length > 0 || unanswered.length > 0);

  function add(given: Person[]) {
    const fresh = given.filter((each) => !chosen.has(each.address.toLowerCase()));
    if (fresh.length > 0) onChange([...people, ...fresh]);
    setTyped('');
    setActive(-1);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    const quoting = (typed.match(/"/g)?.length ?? 0) % 2 === 1;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (offered.length === 0) return;
      event.preventDefault();
      setOpen(true);
      const next = active + (event.key === 'ArrowDown' ? 1 : -1);
      setActive(next >= offered.length ? -1 : next < -1 ? offered.length - 1 : next);
    } else if (event.key === 'Enter' || ((event.key === ',' || event.key === ';') && !quoting)) {
      event.preventDefault();
      if (shown && offered[active]) add([offered[active]]);
      else add(written(typed));
    } else if (event.key === 'Tab' && typed.trim()) {
      add(shown && offered[active] ? [offered[active]] : written(typed));
    } else if (event.key === 'Backspace' && !typed && people.length > 0) {
      onChange(people.slice(0, -1));
    } else if (event.key === 'Escape' && shown) {
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    }
  }

  function onPaste(event: ClipboardEvent<HTMLInputElement>) {
    const pasted = event.clipboardData.getData('text');
    if (!/[,;\n]/.test(pasted)) return;
    event.preventDefault();
    add(written(typed + pasted));
  }

  function onBlur(event: FocusEvent<HTMLInputElement>) {
    if (event.relatedTarget?.closest(`[data-recipients="${list}"]`)) return;
    setOpen(false);
    if (typed.trim()) add(written(typed));
  }

  return (
    <div data-recipients={list} className="relative">
      <div className="flex flex-wrap items-center gap-1 rounded border border-control bg-surface px-2 py-1 has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-2 has-[input:focus-visible]:outline-focus">
        {people.map((each, at) => (
          <span
            key={`${each.address}-${at}`}
            title={each.name ? `${each.name} <${each.address}>` : each.address}
            className={`inline-flex min-w-0 items-center gap-1 rounded border py-0.5 pr-0.5 pl-2 text-sm ${reachable(each.address) ? 'border-line' : 'border-danger text-danger'}`}
          >
            <span className="truncate">{each.name || each.address}</span>
            <button
              type="button"
              aria-label={`${t('mail.removeRecipient')} ${each.name || each.address}`}
              onClick={() => onChange(people.filter((_, other) => other !== at))}
              className="rounded p-0.5 text-muted hover:bg-hover hover:text-ink"
            >
              <X size={12} aria-hidden />
            </button>
          </span>
        ))}
        <input
          id={id}
          type="text"
          name={`recipients-${list}`}
          role="combobox"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          aria-autocomplete="list"
          aria-expanded={shown}
          aria-controls={list}
          aria-activedescendant={shown && active >= 0 ? `${list}-${active}` : undefined}
          autoFocus={autoFocus}
          value={typed}
          onChange={(event) => {
            setTyped(event.target.value);
            setActive(-1);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={onBlur}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          className="min-w-32 flex-1 bg-transparent py-1 text-ink outline-none"
        />
      </div>
      {shown && (
        <div
          onMouseDown={(event) => event.preventDefault()}
          className="absolute top-full right-0 left-0 z-50 mt-1 max-h-72 overflow-y-auto rounded border border-line bg-raised p-1 text-ink shadow-lg"
        >
          {offered.length > 0 && (
            <div id={list} role="listbox" aria-label={t('mail.to')}>
              {offered.map((each, index) => (
                <div
                  key={each.address}
                  id={`${list}-${index}`}
                  role="option"
                  aria-selected={index === active}
                  onClick={() => add([each])}
                  className="flex cursor-pointer flex-col rounded px-2 py-1.5 text-sm hover:bg-hover aria-selected:bg-selected"
                >
                  {each.name && <span className="truncate">{each.name}</span>}
                  <span className="truncate text-muted">{each.address}</span>
                </div>
              ))}
            </div>
          )}
          {unanswered.length > 0 && (
            <p className="px-2 py-1.5 text-sm text-danger">
              {t('mail.directoryUnanswered')} {unanswered.join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
