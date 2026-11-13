import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderInput, Plus, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router';
import { getJson, postJson } from './api';
import { ChoiceBar, ChoiceBox, useChoice, type Choice } from './choice';
import { MoveDialog } from './dialogs';
import { FavouriteButton, FavouriteItem, useFavouriteMarks } from './favourites';
import { Frame, Loading } from './frame';
import { useI18n } from './i18n';
import { ActionsMenu, ContextMenuArea, MenuItem } from './menu';
import { iconButton, primaryButton } from './styles';
import {
  errorMessage,
  Failure,
  nodeHref,
  TREE,
  useToTrash,
  type Role,
  type TreeNode,
} from './tree';

export interface Note extends TreeNode {
  role: Role;
  /** The text after the note's first line, as much as its card shows. */
  excerpt: string;
}

const NOTES = [...TREE, 'notes'];

export function useNotes() {
  return useQuery({
    queryKey: NOTES,
    queryFn: () => getJson<{ folder: string | null; notes: Note[] }>('/api/notes'),
  });
}

/** A new note in the user's notes, with the text and link given, opened as it is made. */
export function useNewNote() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const queryClient = useQueryClient();
  // A page that only makes the note gives way to it, so going back does not make another.
  const asked = new URLSearchParams(search);
  const replace = pathname === '/share' || asked.has('new') || asked.has('voice');
  return useMutation({
    mutationFn: (given: { text?: string; link?: string } = {}) =>
      postJson<TreeNode>('/api/notes', {
        title: t('notes.untitled'),
        ...given,
      }),
    onSuccess: (note) => {
      void queryClient.invalidateQueries({ queryKey: TREE });
      void navigate(nodeHref(note), { replace });
    },
  });
}

function wantsNote(event: KeyboardEvent): boolean {
  return (
    !event.defaultPrevented &&
    event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey &&
    event.code === 'KeyN'
  );
}

/** Alt+N makes a new note from any page. */
export function useNoteShortcut() {
  const { mutate } = useNewNote();
  useEffect(() => {
    function make(event: KeyboardEvent) {
      if (!wantsNote(event)) return;
      event.preventDefault();
      mutate({});
    }
    window.addEventListener('keydown', make);
    return () => window.removeEventListener('keydown', make);
  }, [mutate]);
}

function NoteCard({ note, choice }: { note: Note; choice: Choice<string> }) {
  const { t, formatDate } = useI18n();
  const marks = useFavouriteMarks();
  const toTrash = useToTrash();
  const picked = choice.has(note.id);
  const failed = toTrash.error ?? marks.change.error;
  const items = (
    <>
      <FavouriteItem nodes={[note]} marks={marks} />
      <MenuItem
        icon={Trash2}
        label={t('tree.toTrash')}
        disabled={toTrash.isPending}
        onSelect={() => toTrash.mutate([note.id])}
      />
    </>
  );
  return (
    <ContextMenuArea items={items}>
      <li
        className={`relative flex min-h-32 flex-col gap-1 rounded-lg border p-3 shadow-sm select-none [-webkit-touch-callout:none] hover:border-accent ${picked ? 'border-accent bg-selected' : 'border-line bg-raised'}`}
      >
        {choice.many > 0 && (
          <ChoiceBox
            checked={picked}
            onToggle={(range) => choice.toggle(note.id, range)}
            className="absolute right-3 bottom-3 z-10"
          />
        )}
        <Link
          {...choice.opener(note.id)}
          to={nodeHref(note)}
          className="min-w-0 pr-16 font-semibold break-words after:absolute after:inset-0"
        >
          {note.title}
        </Link>
        {note.excerpt && (
          <p className="line-clamp-4 text-sm break-words text-muted">{note.excerpt}</p>
        )}
        <span className="mt-auto text-xs text-muted">{formatDate(note.updated_at)}</span>
        {failed && <span className="text-xs text-danger">{errorMessage(failed, t)}</span>}
        <div className="absolute top-2 right-2 z-10 flex items-center">
          <FavouriteButton
            id={note.id}
            size={16}
            className="rounded p-1 text-muted hover:bg-hover"
          />
          <ActionsMenu>{items}</ActionsMenu>
        </div>
      </li>
    </ContextMenuArea>
  );
}

export function NotesPage() {
  const { t } = useI18n();
  const notes = useNotes();
  const make = useNewNote();
  const [params] = useSearchParams();
  const asked = params.has('new');
  const made = useRef(false);
  const shown = notes.data?.notes ?? [];
  const choice = useChoice(shown.map((note) => note.id));
  const chosen = shown.filter((note) => choice.has(note.id));
  const toTrash = useToTrash();
  const [moving, setMoving] = useState<Note[] | null>(null);
  useEffect(() => {
    if (!asked || made.current) return;
    made.current = true;
    make.mutate({});
  }, [asked, make]);
  return (
    <Frame title={t('notes.title')}>
      <section
        className="flex w-full max-w-5xl flex-col gap-4"
        onKeyDown={(event) =>
          choice.onKeyDown(event, () =>
            toTrash.mutate(
              chosen.map((note) => note.id),
              { onSuccess: () => choice.choose([]) },
            ),
          )
        }
      >
        <div>
          <button
            type="button"
            onClick={() => make.mutate({})}
            disabled={make.isPending}
            className={primaryButton}
          >
            <Plus size={16} aria-hidden />
            {t('notes.new')}
          </button>
        </div>
        {make.error && <p className="text-sm text-danger">{errorMessage(make.error, t)}</p>}
        {toTrash.error && <p className="text-sm text-danger">{errorMessage(toTrash.error, t)}</p>}
        {choice.many > 0 && (
          <ChoiceBar all={choice.all}>
            <button
              type="button"
              aria-label={t('tree.move')}
              title={t('tree.move')}
              onClick={() => setMoving(chosen)}
              className={iconButton}
            >
              <FolderInput size={16} aria-hidden />
            </button>
            <button
              type="button"
              aria-label={t('tree.toTrash')}
              title={t('tree.toTrash')}
              disabled={toTrash.isPending}
              onClick={() =>
                toTrash.mutate(
                  chosen.map((note) => note.id),
                  { onSuccess: () => choice.choose([]) },
                )
              }
              className={iconButton}
            >
              <Trash2 size={16} aria-hidden />
            </button>
          </ChoiceBar>
        )}
        {notes.isPending ? (
          <Loading />
        ) : notes.isError ? (
          <Failure error={notes.error} />
        ) : notes.data.notes.length === 0 ? (
          <p className="text-muted">{t('notes.empty')}</p>
        ) : (
          <ul
            aria-label={t('notes.title')}
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          >
            {notes.data.notes.map((note) => (
              <NoteCard key={note.id} note={note} choice={choice} />
            ))}
          </ul>
        )}
        {moving && (
          <MoveDialog
            nodes={moving}
            onClose={() => {
              setMoving(null);
              choice.choose([]);
            }}
          />
        )}
      </section>
    </Frame>
  );
}
