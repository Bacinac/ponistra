import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Building2,
  Camera,
  Globe,
  ImageOff,
  Mail,
  MapPin,
  Pencil,
  Phone,
  Plus,
  Search,
  Smartphone,
  Star,
  StarOff,
  Trash2,
  UserRoundPlus,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { deleteJson, getJson, patchJson, postJson, putBytes } from './api';
import { AppPasswordsDialog } from './appPasswords';
import {
  ActionButtons,
  ActionItems,
  ChoiceBar,
  ChoiceBox,
  useChoice,
  type RowAction,
} from './choice';
import { Cancel, Close, ConfirmDialog, Modal } from './dialogs';
import { Frame, Loading, PrimaryAction, useWide } from './frame';
import { isMessageKey, useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { ActionsMenu, ContextMenuArea, MenuItem, MenuSeparator } from './menu';
import { BoxContext, inBox, type Mailbox, useBox } from './mailData';
import { BoxLinks } from './mailShared';
import { initials } from './people';
import { useSettled } from './settled';
import { button, field, iconButton, primaryButton } from './styles';
import { errorMessage, codeText } from './tree';
import { useFilePicker } from './upload';

type Kind = 'email' | 'phone' | 'address' | 'url';

interface Point {
  kind: Kind;
  label: string;
  value: string;
  parts: string[];
}

const FIELDS = [
  'name',
  'given',
  'family',
  'middle',
  'prefix',
  'suffix',
  'nickname',
  'organisation',
  'department',
  'title',
  'birthday',
  'note',
] as const;
type FieldName = (typeof FIELDS)[number];
type Fields = Record<FieldName, string>;

interface Summary {
  id: number;
  name: string;
  organisation: string;
  title: string;
  email: string;
  phone: string;
  photo: string | null;
  colleague: boolean;
  starred: boolean;
}

interface Contact extends Summary {
  fields: Fields;
  points: Point[];
  directory: { host: string; fields: Partial<Fields>; points: Point[] } | null;
  sources: {
    kind: 'microsoft' | 'google' | 'activesync' | 'directory';
    source: string;
    taken_at: string;
  }[];
  changed_at: string;
}

interface Listed extends Summary {
  avatar: string | null;
}

interface Book {
  contacts: Listed[];
  failed: { account: string; error: string }[];
  directories: string[];
  /** The user's role in the shared mailbox whose contacts these are; none in their own. */
  role: Mailbox['role'] | null;
}

interface Colleague {
  name: string;
  address: string;
  title: string;
  company: string;
  account: number;
  contact: number | null;
}

const CONTACTS = ['contacts'];
// The lengths the backend keeps of each field.
const LONGEST: Record<FieldName, number> = {
  name: 500,
  given: 200,
  family: 200,
  middle: 200,
  prefix: 100,
  suffix: 100,
  nickname: 200,
  organisation: 300,
  department: 300,
  title: 300,
  birthday: 10,
  note: 20000,
};
// The directory's values a colleague's own do not stand in front of.
const WORK: FieldName[] = ['title', 'organisation'];
const MORE: FieldName[] = ['name', 'prefix', 'middle', 'suffix', 'nickname'];
const LABELS: Record<Kind, string[]> = {
  email: ['work', 'home', 'other'],
  phone: ['mobile', 'work', 'home', 'main', 'fax', 'pager', 'other'],
  address: ['work', 'home', 'other'],
  url: ['work', 'home', 'other'],
};
const KINDS: Kind[] = ['email', 'phone', 'address', 'url'];
const KIND_ICONS: Record<Kind, LucideIcon> = {
  email: Mail,
  phone: Phone,
  address: MapPin,
  url: Globe,
};
// Where each part of a postal address sits in its vCard ADR value.
const ADDRESS = [
  [2, 'street'],
  [5, 'code'],
  [3, 'city'],
  [4, 'region'],
  [6, 'country'],
] as const;
const ADDRESS_PARTS = 7;
// A leap year, so a birthday without one may still be 29 February.
const LEAP = '2000';
const PHOTOS = 'image/png,image/jpeg,image/gif,image/webp,image/avif';

const BLANK = Object.fromEntries(FIELDS.map((name) => [name, ''])) as Fields;

function blankPoint(kind: Kind): Point {
  return {
    kind,
    label: kind === 'phone' ? 'mobile' : '',
    value: '',
    parts: kind === 'address' ? Array<string>(ADDRESS_PARTS).fill('') : [],
  };
}

function derivedName(fields: Fields): string {
  return [fields.prefix, fields.given, fields.middle, fields.family, fields.suffix]
    .filter(Boolean)
    .join(' ');
}

function labelText(label: string, t: (key: MessageKey) => string): string {
  const key = `contacts.label.${label}`;
  return isMessageKey(key) ? t(key) : label;
}

/** Two points of a contact are one where they reach the same: an address in any case, a
    number in any spacing. */
function reach(point: Point): string {
  if (point.kind === 'phone') return point.value.replace(/[^\d+]/g, '');
  return `${point.kind}:${point.value.trim().toLowerCase()}`;
}

function useChanged() {
  const queryClient = useQueryClient();
  return (contact?: Contact, gone: number[] = []) => {
    if (contact) queryClient.setQueryData([...CONTACTS, contact.id], contact);
    // A deleted contact stays opened until the navigation away from it, a transition, commits:
    // asked for again before then, it is a 404.
    void queryClient.invalidateQueries({
      queryKey: CONTACTS,
      predicate: ({ queryKey }) => !gone.includes(queryKey[1] as number),
    });
    void queryClient.invalidateQueries({ queryKey: ['mail', 'people'] });
  };
}

type Dialog =
  | { type: 'new' }
  | { type: 'edit'; contact: Contact }
  | { type: 'colleagues'; typed: string }
  | { type: 'phones' };

export function ContactsPage() {
  const [search] = useSearchParams();
  const box = Number(search.get('box')) || null;
  return (
    <BoxContext key={box ?? 0} value={box}>
      <ContactsShown />
    </BoxContext>
  );
}

function ContactsShown() {
  const { t, formatNumber } = useI18n();
  const box = useBox();
  const here = (path: string) => inBox(path, box);
  const params = useParams();
  const [asked] = useSearchParams();
  const [query, setQuery] = useState(asked.get('q') ?? '');
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const typed = useSettled(query.trim(), 150);
  const book = useQuery({
    queryKey: [...CONTACTS, 'book', box, typed],
    queryFn: () => getJson<Book>(here(`/api/contacts?${new URLSearchParams({ q: typed })}`)),
    placeholderData: keepPreviousData,
  });
  const id = params.contact ? Number(params.contact) : null;
  const opened = useQuery({
    queryKey: [...CONTACTS, id],
    queryFn: () => getJson<Contact>(`/api/contacts/${id}`),
    enabled: id !== null,
  });
  const contact = id !== null ? opened.data : undefined;
  const reader = book.data?.role === 'read';
  const close = () => setDialog(null);
  const searchable = (book.data?.directories.length ?? 0) > 0;
  const shown = book.data?.contacts ?? [];
  const choice = useChoice(shown.map((each) => each.id));
  const chosen = shown.filter((each) => choice.has(each.id));
  const navigate = useNavigate();
  const changed = useChanged();
  const [removing, setRemoving] = useState<Summary[] | null>(null);
  const remove = useMutation({
    mutationFn: (gone: Summary[]) =>
      postJson(here('/api/contacts/delete'), { contacts: gone.map((each) => each.id) }),
    onSuccess: (_, gone) => {
      choice.choose([]);
      if (id !== null && gone.some((each) => each.id === id)) void navigate(here('/contacts'));
      changed(
        undefined,
        gone.map((each) => each.id),
      );
    },
  });
  const star = useMutation({
    mutationFn: ({ on, starred }: { on: Summary[]; starred: boolean }) =>
      postJson(here('/api/contacts/star'), { contacts: on.map((each) => each.id), starred }),
    onSuccess: () => changed(),
  });
  const writeTo = (on: Summary[]) =>
    here(
      `/mail?${new URLSearchParams(
        on
          .filter((each) => each.email)
          .flatMap((each) => [
            ['to', each.email],
            ['name', each.name],
          ]),
      )}`,
    );
  const writable = chosen.filter((each) => each.email);
  const actionsOf = (on: Summary[]): RowAction[] =>
    reader
      ? []
      : [
          {
            icon: Star,
            label: t('contacts.star'),
            disabled: star.isPending || on.every((each) => each.starred),
            onSelect: () => star.mutate({ on, starred: true }),
          },
          {
            icon: StarOff,
            label: t('contacts.unstar'),
            disabled: star.isPending || !on.some((each) => each.starred),
            onSelect: () => star.mutate({ on, starred: false }),
          },
          {
            icon: Trash2,
            label: t('contacts.deleteMany'),
            disabled: remove.isPending,
            onSelect: () => setRemoving(on),
          },
        ];
  const rowMenu = (each: Summary) => {
    const on = choice.has(each.id) ? chosen : [each];
    return (
      <>
        <MenuItem
          icon={Mail}
          label={t('contacts.write')}
          disabled={!on.some((one) => one.email)}
          onSelect={() => void navigate(writeTo(on))}
        />
        <ActionItems actions={actionsOf(on)} />
      </>
    );
  };
  const row =
    'flex min-w-0 items-center gap-3 rounded px-2 py-2 hover:bg-hover aria-[current=page]:bg-selected';

  const wide = useWide();
  const list = (
    <div
      className="flex flex-col gap-2"
      onKeyDown={(event) => choice.onKeyDown(event, () => setRemoving(chosen))}
    >
      <input
        type="search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t('contacts.search')}
        aria-label={t('contacts.search')}
        className={field}
      />
      {book.data?.failed.map((each) => (
        <p key={each.account} className="text-sm text-danger">
          {each.account}: {codeText(each.error, t)}
        </p>
      ))}
      {book.isError && <p className="text-sm text-danger">{errorMessage(book.error, t)}</p>}
      {remove.isError && <p className="text-sm text-danger">{errorMessage(remove.error, t)}</p>}
      {star.isError && <p className="text-sm text-danger">{errorMessage(star.error, t)}</p>}
      {book.isPending ? (
        <Loading />
      ) : shown.length === 0 ? (
        <p className="text-sm text-muted">{t(typed ? 'contacts.noMatch' : 'contacts.empty')}</p>
      ) : (
        <div className="flex flex-col">
          {choice.many > 0 && (
            <ChoiceBar all={choice.all}>
              <Link
                to={writeTo(chosen)}
                aria-label={t('contacts.write')}
                title={t('contacts.write')}
                aria-disabled={writable.length === 0}
                onClick={(event) => {
                  if (writable.length === 0) event.preventDefault();
                }}
                className={`${iconButton} aria-disabled:pointer-events-none aria-disabled:opacity-50`}
              >
                <Mail size={16} aria-hidden />
              </Link>
              <ActionButtons actions={actionsOf(chosen)} />
            </ChoiceBar>
          )}
          <ul className="flex flex-col gap-0.5">
            {shown.map((each) => (
              <ContextMenuArea key={each.id} items={rowMenu(each)}>
                <li
                  className={`flex min-w-0 items-center rounded select-none [-webkit-touch-callout:none] ${choice.has(each.id) ? 'bg-selected' : ''}`}
                >
                  {choice.many > 0 && (
                    <ChoiceBox
                      checked={choice.has(each.id)}
                      onToggle={(range) => choice.toggle(each.id, range)}
                      className="ml-2"
                    />
                  )}
                  <Link
                    {...choice.opener(each.id)}
                    to={here(`/contacts/${each.id}`)}
                    aria-current={each.id === id ? 'page' : undefined}
                    className={`${row} flex-1`}
                  >
                    <Avatar contact={each} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm">
                        {each.name || t('contacts.unnamed')}
                      </span>
                      <span className="block truncate text-xs text-muted">
                        {[each.organisation, each.email || each.phone].filter(Boolean).join(' · ')}
                      </span>
                    </span>
                    {each.starred && (
                      <Star
                        size={14}
                        role="img"
                        aria-label={t('contacts.starred')}
                        className="shrink-0 fill-current text-accent"
                      />
                    )}
                    {each.colleague && (
                      <span title={t('contacts.fromDirectory')} className="shrink-0 text-muted">
                        <Building2 size={14} aria-hidden />
                        <span className="sr-only">{t('contacts.fromDirectory')}</span>
                      </span>
                    )}
                  </Link>
                </li>
              </ContextMenuArea>
            ))}
          </ul>
        </div>
      )}
      {removing && (
        <ConfirmDialog
          heading={t('contacts.deleteManyTitle')}
          confirmLabel={t('contacts.deleteMany')}
          onConfirm={() => remove.mutate(removing)}
          onClose={() => setRemoving(null)}
        >
          {`${t('explorer.selected')}: ${formatNumber(removing.length)}. ${t('contacts.deleteChosen')}`}
        </ConfirmDialog>
      )}
      {searchable && !reader && typed.length >= 2 && (
        <button
          type="button"
          onClick={() => setDialog({ type: 'colleagues', typed })}
          className={`${button} self-start`}
        >
          <Search size={16} aria-hidden />
          {t('contacts.searchDirectory')}
        </button>
      )}
      <BoxLinks page="contacts" />
    </div>
  );

  return (
    <Frame
      title={contact?.name || t('rail.contacts')}
      folders={false}
      primary={
        reader ? undefined : (
          <PrimaryAction
            icon={UserRoundPlus}
            label={t('contacts.new')}
            onClick={() => setDialog({ type: 'new' })}
          />
        )
      }
      more={
        <>
          {searchable && !reader && (
            <MenuItem
              icon={Building2}
              label={t('contacts.colleague')}
              onSelect={() => setDialog({ type: 'colleagues', typed: query.trim() })}
            />
          )}
          {searchable && !reader && <MenuSeparator />}
          <MenuItem
            icon={Smartphone}
            label={t('contacts.phones')}
            onSelect={() => setDialog({ type: 'phones' })}
          />
        </>
      }
      side={wide ? list : undefined}
    >
      {id === null ? (
        wide ? (
          <p className="text-muted">{t('contacts.choose')}</p>
        ) : (
          list
        )
      ) : contact ? (
        <Detail
          key={contact.id}
          contact={contact}
          onEdit={reader ? undefined : () => setDialog({ type: 'edit', contact })}
        />
      ) : (
        <article className="flex w-full max-w-3xl flex-col gap-2">
          <Link
            to={here('/contacts')}
            aria-label={t('frame.close')}
            className={`${iconButton} self-start md:hidden`}
          >
            <X size={16} aria-hidden />
          </Link>
          {opened.isError ? (
            <p className="text-sm text-danger">{errorMessage(opened.error, t)}</p>
          ) : (
            <Loading />
          )}
        </article>
      )}
      {dialog?.type === 'new' && <ContactDialog onClose={close} />}
      {dialog?.type === 'edit' && <ContactDialog contact={dialog.contact} onClose={close} />}
      {dialog?.type === 'colleagues' && <ColleaguesDialog initial={dialog.typed} onClose={close} />}
      {dialog?.type === 'phones' && <AppPasswordsDialog onClose={close} />}
    </Frame>
  );
}

function Avatar({ contact }: { contact: Listed }) {
  return contact.avatar === null ? (
    <Initials name={contact.name} size="size-9 text-xs" />
  ) : (
    <img src={contact.avatar} alt="" className="size-9 shrink-0 rounded-full object-cover" />
  );
}

function Photo({ contact }: { contact: Contact }) {
  return contact.photo === null ? (
    <Initials name={contact.name} size="size-16 text-xl" />
  ) : (
    <img
      src={`/api/contacts/${contact.id}/photo?v=${contact.photo.slice(0, 12)}`}
      alt=""
      className="size-16 shrink-0 rounded-full object-cover"
    />
  );
}

function Initials({ name, size }: { name: string; size: string }) {
  return (
    <span
      aria-hidden
      className={`flex ${size} shrink-0 items-center justify-center rounded-full bg-selected font-semibold text-ink`}
    >
      {initials(name)}
    </span>
  );
}

function Shown({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-b border-line py-2">
      <p className="text-xs text-muted">{label}</p>
      <div className="min-w-0 text-sm break-words whitespace-pre-line">{children}</div>
    </div>
  );
}

function PointShown({ point, name }: { point: Point; name: string }) {
  const { t } = useI18n();
  const Icon = KIND_ICONS[point.kind];
  const link = 'text-sm break-words text-link hover:underline';
  let value: ReactNode = (
    <span className="text-sm break-words whitespace-pre-line">{point.value}</span>
  );
  if (point.kind === 'email') {
    value = (
      <Link to={`/mail?${new URLSearchParams({ to: point.value, name })}`} className={link}>
        {point.value}
      </Link>
    );
  } else if (point.kind === 'phone') {
    value = (
      <a href={`tel:${point.value.replace(/[^\d+]/g, '')}`} className={link}>
        {point.value}
      </a>
    );
  } else if (point.kind === 'url') {
    const href = /^https?:\/\//i.test(point.value) ? point.value : `https://${point.value}`;
    value = (
      <a href={href} target="_blank" rel="noreferrer" className={link}>
        {point.value}
      </a>
    );
  }
  return (
    <div className="flex items-start gap-3 border-b border-line py-2">
      <Icon size={16} aria-hidden className="mt-0.5 shrink-0 text-muted" />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="sr-only">{t(`contacts.kind.${point.kind}`)}</span>
        {value}
        {point.label && <span className="text-xs text-muted">{labelText(point.label, t)}</span>}
      </div>
    </div>
  );
}

function Birthday({ value }: { value: string }) {
  const { language } = useI18n();
  const yearless = value.startsWith('--');
  const [year, month, day] = (yearless ? `${LEAP}${value.slice(1)}` : value).split('-').map(Number);
  if (!year || !month || !day) return <>{value}</>;
  const shown = new Intl.DateTimeFormat(language, {
    day: 'numeric',
    month: 'long',
    ...(yearless ? {} : { year: 'numeric' }),
    timeZone: 'UTC',
  }).format(Date.UTC(year, month - 1, day));
  return <>{shown}</>;
}

/** A contact, which `onEdit` changes, none where the contacts are only read. */
function Detail({ contact, onEdit }: { contact: Contact; onEdit?: () => void }) {
  const { t, formatDate } = useI18n();
  const box = useBox();
  const navigate = useNavigate();
  const changed = useChanged();
  const [removing, setRemoving] = useState(false);
  const photo = useMutation({
    mutationFn: async (file: File | null) => {
      if (file) await putBytes<Contact>(`/api/contacts/${contact.id}/photo`, file);
      else await deleteJson(`/api/contacts/${contact.id}/photo`);
    },
    onSuccess: () => changed(),
  });
  const remove = useMutation({
    mutationFn: () => deleteJson(`/api/contacts/${contact.id}`),
    onSuccess: () => {
      void navigate(inBox('/contacts', box));
      changed(undefined, [contact.id]);
    },
  });
  const star = useMutation({
    mutationFn: (starred: boolean) =>
      postJson('/api/contacts/star', { contacts: [contact.id], starred }),
    onSuccess: () => changed(),
  });
  const picker = useFilePicker((files) => photo.mutate(files[0]), {
    accept: PHOTOS,
    multiple: false,
  });
  const failure = photo.error ?? remove.error ?? star.error;
  const work = [contact.title, contact.fields.department, contact.organisation]
    .filter(Boolean)
    .join(' · ');
  const own = new Set(contact.points.map(reach));
  const theirs = contact.directory?.points.filter((each) => !own.has(reach(each))) ?? [];
  const { nickname, birthday, note } = contact.fields;

  return (
    <article aria-label={contact.name} className="flex w-full max-w-3xl flex-col gap-1">
      {picker.element}
      <div className="flex items-center gap-3 pb-2">
        <Link
          to={inBox('/contacts', box)}
          aria-label={t('frame.close')}
          className={`${iconButton} lg:hidden`}
        >
          <X size={16} aria-hidden />
        </Link>
        <Photo contact={contact} />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-semibold">
            {contact.name || t('contacts.unnamed')}
          </h2>
          {work && <p className="text-sm break-words text-muted">{work}</p>}
        </div>
        <button
          type="button"
          aria-pressed={contact.starred}
          aria-label={t(contact.starred ? 'contacts.unstar' : 'contacts.star')}
          title={t(contact.starred ? 'contacts.unstar' : 'contacts.star')}
          disabled={!onEdit || star.isPending}
          onClick={() => star.mutate(!contact.starred)}
          className={iconButton}
        >
          <Star
            size={18}
            aria-hidden
            className={contact.starred ? 'fill-current text-accent' : ''}
          />
        </button>
        {onEdit && (
          <button
            type="button"
            onClick={onEdit}
            aria-label={t('contacts.edit')}
            title={t('contacts.edit')}
            className={button}
          >
            <Pencil size={16} aria-hidden />
            <span className="hidden sm:inline">{t('contacts.edit')}</span>
          </button>
        )}
        {onEdit && (
          <ActionsMenu>
            <MenuItem
              icon={Camera}
              label={t(contact.photo === null ? 'contacts.addPhoto' : 'contacts.changePhoto')}
              disabled={photo.isPending}
              onSelect={picker.open}
            />
            {contact.photo !== null && (
              <MenuItem
                icon={ImageOff}
                label={t('contacts.removePhoto')}
                disabled={photo.isPending}
                onSelect={() => photo.mutate(null)}
              />
            )}
            <MenuSeparator />
            <MenuItem
              icon={Trash2}
              label={t('contacts.delete')}
              onSelect={() => setRemoving(true)}
            />
          </ActionsMenu>
        )}
      </div>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      {contact.points.map((each, at) => (
        <PointShown key={at} point={each} name={contact.name} />
      ))}
      {nickname && <Shown label={t('contacts.field.nickname')}>{nickname}</Shown>}
      {birthday && (
        <Shown label={t('contacts.field.birthday')}>
          <Birthday value={birthday} />
        </Shown>
      )}
      {note && <Shown label={t('contacts.field.note')}>{note}</Shown>}
      {contact.directory && (
        <section aria-label={t('contacts.directory')} className="mt-3 flex flex-col">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Building2 size={16} aria-hidden className="text-muted" />
            {t('contacts.directory')}
          </h3>
          <p className="text-xs text-muted">
            {contact.directory.host} · {t('contacts.directoryNote')}
          </p>
          {theirs.map((each, at) => (
            <PointShown key={at} point={each} name={contact.name} />
          ))}
        </section>
      )}
      {contact.sources.length > 0 && (
        <section aria-label={t('contacts.sources')} className="mt-3 flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold">{t('contacts.sources')}</h3>
          {contact.sources.map((each) => (
            <p key={`${each.kind}:${each.source}`} className="text-xs text-muted">
              {t(`contacts.source.${each.kind}`)} · {each.source} · {formatDate(each.taken_at)}
            </p>
          ))}
        </section>
      )}
      <p className="mt-3 text-xs text-muted">
        {t('contacts.changed')}: {formatDate(contact.changed_at)}
      </p>
      {removing && (
        <ConfirmDialog
          heading={t('contacts.deleteTitle')}
          confirmLabel={t('contacts.delete')}
          onConfirm={() => remove.mutate()}
          onClose={() => setRemoving(false)}
        >
          <strong>{contact.name || t('contacts.unnamed')}</strong> {t('contacts.deleteWarning')}
        </ConfirmDialog>
      )}
    </article>
  );
}

/** A day and a month, and a year where it is known. */
function BirthdayField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t, language } = useI18n();
  const [parts, setParts] = useState(() => {
    const [year, month, day] = value.startsWith('--')
      ? ['', ...value.slice(2).split('-')]
      : (value || '--').split('-');
    return { year, month, day: day ? String(Number(day)) : '' };
  });
  const months = useMemo(() => {
    const named = new Intl.DateTimeFormat(language, { month: 'long', timeZone: 'UTC' });
    return Array.from({ length: 12 }, (_, at) => named.format(Date.UTC(2000, at, 1)));
  }, [language]);
  const begun = Boolean(parts.day || parts.month || parts.year);

  function change(given: Partial<typeof parts>) {
    const now = { ...parts, ...given };
    setParts(now);
    const day = now.day.padStart(2, '0');
    const year = now.year ? now.year.padStart(4, '0') : '-';
    onChange(now.day && now.month ? `${year}-${now.month}-${day}` : '');
  }

  return (
    <fieldset className="flex min-w-0 flex-col gap-1 text-sm">
      <legend className="mb-1">{t('contacts.field.birthday')}</legend>
      <div className="flex flex-wrap gap-2">
        <input
          type="number"
          min={1}
          max={31}
          required={begun}
          aria-label={t('contacts.day')}
          placeholder={t('contacts.day')}
          value={parts.day}
          onChange={(event) => change({ day: event.target.value })}
          className={`${field} w-20`}
        />
        <select
          required={begun}
          aria-label={t('contacts.month')}
          value={parts.month}
          onChange={(event) => change({ month: event.target.value })}
          className={field}
        >
          <option value="">{t('contacts.month')}</option>
          {months.map((name, at) => (
            <option key={name} value={String(at + 1).padStart(2, '0')}>
              {name}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={1}
          max={9999}
          aria-label={t('contacts.year')}
          placeholder={t('contacts.year')}
          value={parts.year}
          onChange={(event) => change({ year: event.target.value })}
          className={`${field} w-28`}
        />
      </div>
    </fieldset>
  );
}

function PointsEditor({
  points,
  onChange,
}: {
  points: Point[];
  onChange: (points: Point[]) => void;
}) {
  const { t } = useI18n();
  const replace = (at: number, point: Point | null) =>
    onChange(points.flatMap((each, index) => (index !== at ? [each] : point ? [point] : [])));
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="mb-1 text-sm">{t('contacts.reach')}</legend>
      {points.map((point, at) => {
        const Icon = KIND_ICONS[point.kind];
        const known = LABELS[point.kind];
        const labels =
          !point.label || known.includes(point.label) ? known : [...known, point.label];
        const kind = t(`contacts.kind.${point.kind}`);
        return (
          <div key={at} className="flex items-start gap-2">
            <Icon size={16} aria-hidden className="mt-3 shrink-0 text-muted" />
            <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row">
              <select
                aria-label={`${kind}: ${t('contacts.label')}`}
                value={point.label}
                onChange={(event) => replace(at, { ...point, label: event.target.value })}
                className={`${field} self-start px-2 sm:w-32 sm:shrink-0`}
              >
                <option value="">{t('contacts.label.none')}</option>
                {labels.map((label) => (
                  <option key={label} value={label}>
                    {labelText(label, t)}
                  </option>
                ))}
              </select>
              {point.kind === 'address' ? (
                <div className="grid min-w-0 flex-1 grid-cols-2 gap-2">
                  {ADDRESS.map(([index, part]) => (
                    <input
                      key={part}
                      aria-label={t(`contacts.address.${part}`)}
                      placeholder={t(`contacts.address.${part}`)}
                      value={point.parts[index] ?? ''}
                      onChange={(event) => {
                        const parts = [...point.parts];
                        parts[index] = event.target.value;
                        replace(at, { ...point, parts });
                      }}
                      className={`${field} min-w-0 ${part === 'street' ? 'col-span-2' : ''}`}
                    />
                  ))}
                </div>
              ) : (
                <input
                  type={point.kind === 'phone' ? 'tel' : 'text'}
                  inputMode={
                    point.kind === 'phone' ? 'tel' : point.kind === 'email' ? 'email' : 'url'
                  }
                  aria-label={kind}
                  maxLength={2000}
                  value={point.value}
                  onChange={(event) => replace(at, { ...point, value: event.target.value })}
                  className={`${field} min-w-0 flex-1`}
                />
              )}
            </div>
            <button
              type="button"
              onClick={() => replace(at, null)}
              aria-label={`${kind}: ${t('contacts.removePoint')}`}
              title={t('contacts.removePoint')}
              className={`${iconButton} mt-1.5`}
            >
              <X size={16} aria-hidden />
            </button>
          </div>
        );
      })}
      <div className="flex flex-wrap gap-2">
        {KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            onClick={() => onChange([...points, blankPoint(kind)])}
            className={button}
          >
            <Plus size={16} aria-hidden />
            {t(`contacts.kind.${kind}`)}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

function ContactDialog({ contact, onClose }: { contact?: Contact; onClose: () => void }) {
  const { t } = useI18n();
  const box = useBox();
  const navigate = useNavigate();
  const changed = useChanged();
  const initial = contact?.fields ?? BLANK;
  const held = contact?.directory?.fields ?? {};
  const [fields, setFields] = useState<Fields>(initial);
  const [points, setPoints] = useState<Point[]>(
    () => contact?.points ?? [blankPoint('email'), blankPoint('phone')],
  );
  const [more, setMore] = useState(() =>
    MORE.some(
      (name) => initial[name] && (name !== 'name' || initial.name !== derivedName(initial)),
    ),
  );
  const save = useMutation({
    mutationFn: () => {
      const given = { ...fields };
      if (given.name === derivedName(initial) || given.name === derivedName(given)) given.name = '';
      const kept = points.filter((each) =>
        each.kind === 'address' ? each.parts.some((part) => part.trim()) : each.value.trim(),
      );
      const sent = { fields: given, points: kept };
      return contact
        ? patchJson<Contact>(`/api/contacts/${contact.id}`, sent)
        : postJson<Contact>(inBox('/api/contacts', box), sent);
    },
    onSuccess: (saved) => {
      changed(saved);
      if (!contact) navigate(inBox(`/contacts/${saved.id}`, box));
      onClose();
    },
  });

  function text(name: FieldName, wide = false) {
    const theirs = held[name] ?? '';
    const fixed = WORK.includes(name) && theirs !== '';
    return (
      <label className={`flex min-w-0 flex-col gap-1 text-sm ${wide ? 'sm:col-span-2' : ''}`}>
        {t(`contacts.field.${name}`)}
        <input
          value={fixed ? theirs : fields[name]}
          disabled={fixed}
          placeholder={name === 'name' ? derivedName(fields) || theirs : theirs}
          maxLength={LONGEST[name]}
          onChange={(event) => setFields((now) => ({ ...now, [name]: event.target.value }))}
          className={field}
        />
        {fixed && <span className="text-xs text-muted">{t('contacts.heldByDirectory')}</span>}
      </label>
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Modal heading={t(contact ? 'contacts.editTitle' : 'contacts.new')} wide onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {more && text('prefix')}
          {text('given')}
          {more && text('middle')}
          {text('family')}
          {more && text('suffix')}
          {more && text('name', true)}
          {more && text('nickname')}
        </div>
        {!more && (
          <button
            type="button"
            onClick={() => setMore(true)}
            className="-mt-2 self-start text-sm text-link hover:underline"
          >
            {t('contacts.more')}
          </button>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          {text('organisation', true)}
          {text('department')}
          {text('title')}
        </div>
        <PointsEditor points={points} onChange={setPoints} />
        {contact?.directory && <p className="text-xs text-muted">{t('contacts.directoryKept')}</p>}
        <BirthdayField
          value={fields.birthday}
          onChange={(birthday) => setFields((now) => ({ ...now, birthday }))}
        />
        <label className="flex flex-col gap-1 text-sm">
          {t('contacts.field.note')}
          <textarea
            rows={3}
            maxLength={LONGEST.note}
            value={fields.note}
            onChange={(event) => setFields((now) => ({ ...now, note: event.target.value }))}
            className={field}
          />
        </label>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ColleaguesDialog({ initial, onClose }: { initial: string; onClose: () => void }) {
  const { t } = useI18n();
  const box = useBox();
  const navigate = useNavigate();
  const changed = useChanged();
  const [typed, setTyped] = useState(initial);
  const settled = useSettled(typed.trim(), 300);
  const found = useQuery({
    queryKey: [...CONTACTS, 'colleagues', box, settled],
    queryFn: () =>
      getJson<{ people: Colleague[]; unanswered: string[] }>(
        inBox(`/api/contacts/colleagues?${new URLSearchParams({ q: settled })}`, box),
      ),
    enabled: settled.length >= 2,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
  const add = useMutation({
    mutationFn: (colleague: Colleague) =>
      postJson<Contact>(inBox('/api/contacts/colleagues', box), {
        account: colleague.account,
        address: colleague.address,
        name: colleague.name,
      }),
    onSuccess: (made) => {
      changed(made);
      navigate(inBox(`/contacts/${made.id}`, box));
      onClose();
    },
  });
  const answer = settled.length >= 2 ? found.data : undefined;
  const people = answer?.people ?? [];

  return (
    <Modal heading={t('contacts.colleague')} wide onClose={onClose}>
      <p className="text-sm text-muted">{t('contacts.colleagueNote')}</p>
      <input
        type="search"
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        placeholder={t('contacts.colleagueSearch')}
        aria-label={t('contacts.colleagueSearch')}
        className={field}
      />
      {settled.length < 2 ? (
        <p className="text-sm text-muted">{t('contacts.colleagueShort')}</p>
      ) : found.isPending ? (
        <Loading />
      ) : found.isError ? (
        <p className="text-sm text-danger">{errorMessage(found.error, t)}</p>
      ) : (
        people.length === 0 && <p className="text-sm text-muted">{t('contacts.colleagueNone')}</p>
      )}
      {people.length > 0 && (
        <ul className="flex max-h-96 flex-col overflow-y-auto">
          {people.map((each) => (
            <li
              key={`${each.account}:${each.address}`}
              className="flex items-center gap-3 border-b border-line py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm">{each.name || each.address}</p>
                <p className="truncate text-xs text-muted">
                  {[each.title, each.company, each.address].filter(Boolean).join(' · ')}
                </p>
              </div>
              {each.contact !== null ? (
                <Link
                  to={inBox(`/contacts/${each.contact}`, box)}
                  onClick={onClose}
                  className={button}
                >
                  {t('contacts.open')}
                </Link>
              ) : (
                <button
                  type="button"
                  disabled={add.isPending}
                  onClick={() => add.mutate(each)}
                  className={button}
                >
                  <UserRoundPlus size={16} aria-hidden />
                  {t('contacts.add')}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {answer?.unanswered.map((address) => (
        <p key={address} className="text-sm text-danger">
          {address}: {t('contacts.unanswered')}
        </p>
      ))}
      {add.isError && <p className="text-sm text-danger">{errorMessage(add.error, t)}</p>}
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}
