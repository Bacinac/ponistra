import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronRight, ListTodo, Plus, Trash2 } from 'lucide-react';
import { useEffect, useId, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { MiniMonth } from './calendar';
import { dayOf, type Occurrence } from './calendarData';
import { Cancel, Modal } from './dialogs';
import { Frame, Loaded, Loading, PrimaryAction } from './frame';
import { useI18n } from './i18n';
import { dangerButton, field, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';

export const TASKS = ['tasks'] as const;

export interface TaskSource {
  kind: 'mail' | 'event' | 'document' | 'message';
  label: string;
  link: string;
}

export interface Task {
  id: number;
  text: string;
  due: string | null;
  done: boolean;
  done_at: string | null;
  source: TaskSource | null;
  changed_at: string;
}

/** What a task is made from: the line it starts as, its day where one is at hand, and where it
 * leads back to. */
export interface Draft {
  text: string;
  due?: string;
  source?: TaskSource;
}

export function useTasks() {
  return useQuery({
    queryKey: TASKS,
    queryFn: () => getJson<{ tasks: Task[] }>('/api/tasks'),
  });
}

function useTaskChange<V>(mutationFn: (variables: V) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TASKS }),
  });
}

/** A task on its day among the events, drawn by the views like one and opened as itself. */
export function taskShown(task: Task): Occurrence {
  return {
    event: -task.id,
    master: -task.id,
    calendar: -1,
    recurrence_id: null,
    summary: task.text,
    location: '',
    conference: '',
    all_day: true,
    start: task.due!,
    end: task.due!,
    status: task.done ? 'cancelled' : 'confirmed',
    busy: false,
    private: false,
    recurring: false,
    moved: false,
    response: '',
    attendees: 0,
    task: task.id,
  };
}

export function TaskDialog({
  task,
  draft,
  onClose,
}: {
  task?: Task;
  draft?: Draft;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [form, setForm] = useState({
    text: task?.text ?? draft?.text ?? '',
    due: task?.due ?? draft?.due ?? '',
    done: task?.done ?? false,
  });
  const source = task ? task.source : (draft?.source ?? null);
  const save = useTaskChange(() => {
    const body = { text: form.text.trim(), due: form.due || null, done: form.done };
    return task
      ? patchJson(`/api/tasks/${task.id}`, body)
      : postJson('/api/tasks', { ...body, source });
  });
  const remove = useTaskChange(() => deleteJson(`/api/tasks/${task!.id}`));
  const set = (changes: Partial<typeof form>) => setForm({ ...form, ...changes });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!form.text.trim()) return;
    save.mutate(undefined, { onSuccess: onClose });
  }

  const error = save.error ?? remove.error;
  return (
    <Modal heading={t(task ? 'tasks.edit' : 'tasks.new')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('tasks.text')}
          <input
            type="text"
            required
            autoFocus
            maxLength={1000}
            value={form.text}
            onChange={(event) => set({ text: event.target.value })}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('tasks.due')}
          <input
            type="date"
            value={form.due}
            onChange={(event) => set({ due: event.target.value })}
            className={field}
          />
        </label>
        {task && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.done}
              onChange={(event) => set({ done: event.target.checked })}
            />
            {t('tasks.done')}
          </label>
        )}
        {source && (
          <p className="text-sm text-muted">
            {t(`tasks.from.${source.kind}`)}:{' '}
            <Link to={source.link} className="text-link hover:underline" onClick={onClose}>
              {source.label || source.link}
            </Link>
          </p>
        )}
        {error && <p className="text-sm text-danger">{errorMessage(error, t)}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          {task && (
            <button
              type="button"
              onClick={() => remove.mutate(undefined, { onSuccess: onClose })}
              disabled={remove.isPending}
              className={`${dangerButton} mr-auto`}
            >
              <Trash2 size={16} aria-hidden />
              {t('tasks.delete')}
            </button>
          )}
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t(task ? 'tree.save' : 'tree.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Row({ task, onOpen }: { task: Task; onOpen: (task: Task) => void }) {
  const { t, formatDate } = useI18n();
  const toggle = useTaskChange((done: boolean) => patchJson(`/api/tasks/${task.id}`, { done }));
  // Ticked at once, as a box is; the list regroups when the server has it.
  const [done, setDone] = useState(task.done);
  useEffect(() => setDone(task.done), [task.done]);
  const overdue = !task.done && task.due !== null && task.due < dayOf(new Date());
  return (
    <li className="flex min-w-0 items-center gap-3 rounded px-2 py-1 hover:bg-hover">
      <input
        type="checkbox"
        checked={done}
        onChange={(event) => {
          setDone(event.target.checked);
          toggle.mutate(event.target.checked);
        }}
        aria-label={`${t('tasks.done')}: ${task.text}`}
        className="size-4 shrink-0"
      />
      <button
        type="button"
        onClick={() => onOpen(task)}
        className="flex min-w-0 flex-1 flex-col text-left hover:underline"
      >
        <span className={`truncate text-sm ${task.done ? 'text-muted line-through' : ''}`}>
          {task.text}
        </span>
        {(task.due || task.source) && (
          <span className="flex items-center gap-1 truncate text-xs text-muted">
            {task.due && (
              <span className={overdue ? 'text-danger' : ''}>{formatDate(task.due)}</span>
            )}
            {task.due && task.source && <span>·</span>}
            {task.source && <span className="truncate">{task.source.label}</span>}
          </span>
        )}
      </button>
    </li>
  );
}

type Group = 'overdue' | 'today' | 'later' | 'undated' | 'done';

function groupOf(task: Task, today: string): Group {
  if (task.done) return 'done';
  if (task.due === null) return 'undated';
  if (task.due < today) return 'overdue';
  return task.due === today ? 'today' : 'later';
}

const GROUPS: Group[] = ['overdue', 'today', 'later', 'undated', 'done'];

function List({ tasks }: { tasks: Task[] }) {
  const { t } = useI18n();
  const [dialog, setDialog] = useState<{ task?: Task } | null>(null);
  const [query, setQuery] = useSearchParams();
  const wanted = Number(query.get('task'));
  useEffect(() => {
    if (!wanted) return;
    const task = tasks.find((each) => each.id === wanted);
    if (task) setDialog({ task });
    const rest = new URLSearchParams(query);
    rest.delete('task');
    setQuery(rest, { replace: true });
  }, [wanted, tasks, query, setQuery]);
  const headings = useId();
  const today = dayOf(new Date());
  const grouped = new Map<Group, Task[]>(GROUPS.map((each) => [each, []]));
  for (const task of tasks) grouped.get(groupOf(task, today))!.push(task);
  return (
    <Frame
      title={t('tasks.title')}
      folders={false}
      side={<MiniMonth day={today} view="day" />}
      primary={<PrimaryAction icon={Plus} label={t('tasks.new')} onClick={() => setDialog({})} />}
    >
      <div className="flex w-full max-w-3xl flex-col gap-6">
        <p className="text-sm text-muted">{t('tasks.note')}</p>
        {tasks.length === 0 && <p className="text-sm text-muted">{t('tasks.none')}</p>}
        {GROUPS.filter((group) => grouped.get(group)!.length > 0).map((group) => (
          <section
            key={group}
            aria-labelledby={`${headings}-${group}`}
            className="flex flex-col gap-1"
          >
            <h2
              id={`${headings}-${group}`}
              className="px-2 text-xs font-semibold tracking-wide text-muted uppercase"
            >
              {t(`tasks.group.${group}`)}
            </h2>
            <ul className="flex flex-col">
              {grouped.get(group)!.map((task) => (
                <Row key={task.id} task={task} onOpen={(task) => setDialog({ task })} />
              ))}
            </ul>
          </section>
        ))}
      </div>
      {dialog && <TaskDialog task={dialog.task} onClose={() => setDialog(null)} />}
    </Frame>
  );
}

export function TasksPage() {
  const tasks = useTasks();
  return <Loaded query={tasks}>{(data) => <List tasks={data.tasks} />}</Loaded>;
}

/** The tasks due, on Today: what is for today and what was for before. */
export function TasksTile() {
  const { t } = useI18n();
  const tasks = useTasks();
  const heading = useId();
  const [dialog, setDialog] = useState<{ task?: Task } | null>(null);
  const today = dayOf(new Date());
  const due = (tasks.data?.tasks ?? []).filter(
    (each) => !each.done && each.due !== null && each.due <= today,
  );
  return (
    <section aria-labelledby={heading} className="flex flex-col gap-2 rounded-xl bg-raised p-3">
      <div className="flex items-center gap-2 px-2">
        <h2 id={heading} className="font-semibold">
          {t('tasks.due.title')}
        </h2>
        <button
          type="button"
          onClick={() => setDialog({})}
          aria-label={t('tasks.new')}
          title={t('tasks.new')}
          className={iconButton}
        >
          <Plus size={16} aria-hidden />
        </button>
        <Link
          to="/tasks"
          className="ml-auto flex items-center gap-0.5 rounded text-sm text-link hover:underline"
        >
          {t('tasks.title')}
          <ChevronRight size={16} aria-hidden />
        </Link>
      </div>
      {tasks.isPending ? (
        <Loading />
      ) : tasks.isError ? (
        <p className="px-2 text-sm text-danger">{errorMessage(tasks.error, t)}</p>
      ) : due.length === 0 ? (
        <p className="flex items-center gap-2 px-2 text-sm text-muted">
          <ListTodo size={14} aria-hidden />
          {t('tasks.due.none')}
        </p>
      ) : (
        <ul className="flex flex-col">
          {due.map((task) => (
            <Row key={task.id} task={task} onOpen={(task) => setDialog({ task })} />
          ))}
        </ul>
      )}
      {dialog && (
        <TaskDialog
          task={dialog.task}
          draft={dialog.task ? undefined : { due: today, text: '' }}
          onClose={() => setDialog(null)}
        />
      )}
    </section>
  );
}
