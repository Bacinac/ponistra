import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileUp, Pencil, Plus, Trash2 } from 'lucide-react';
import { useMemo, useState, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { useSession } from './auth';
import { CALENDAR } from './calendarData';
import { Cancel, ConfirmDialog, Modal, Picker } from './dialogs';
import { Loaded, PrimaryAction } from './frame';
import { useI18n } from './i18n';
import { MenuItem } from './menu';
import { AdminFrame } from './settings';
import { field, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';
import { useFilePicker } from './upload';

const WORKDAYS = [...CALENDAR, 'workdays'];

interface Span {
  first: string;
  last: string;
  name: string;
}

interface Closure extends Span {
  id: number;
}

interface Workdays {
  country: string;
  subdivision: string;
  opens: string;
  closes: string;
  /** Each country the installation may work in, with its regions whose holidays differ. */
  countries: Record<string, [string, string][]>;
  holidays: { date: string; hr: string; en: string }[];
  closures: Closure[];
}

type Dialog =
  | { type: 'edit'; closure?: Closure }
  | { type: 'delete'; closure: Closure }
  | { type: 'import'; spans: Span[] };

/** A change to the days off moves the series that mind them, so the calendar reads again. */
function useWorkdaysChange<V, R>(mutationFn: (variables: V) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CALENDAR }),
  });
}

function ClosureDialog({ closure, onClose }: { closure?: Closure; onClose: () => void }) {
  const { t } = useI18n();
  const [form, setForm] = useState<Span>({
    name: closure?.name ?? '',
    first: closure?.first ?? '',
    last: closure?.last ?? '',
  });
  const save = useWorkdaysChange((span: Span) =>
    closure
      ? patchJson(`/api/calendar/closures/${closure.id}`, span)
      : postJson('/api/calendar/closures', { closures: [span] }),
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ ...form, name: form.name.trim() }, { onSuccess: onClose });
  }

  return (
    <Modal heading={t(closure ? 'workdays.edit' : 'workdays.new')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('workdays.name')}
          <input
            type="text"
            required
            maxLength={200}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            className={field}
          />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('workdays.first')}
            <input
              type="date"
              required
              value={form.first}
              onChange={(event) => {
                const first = event.target.value;
                setForm({
                  ...form,
                  first,
                  last: !form.last || form.last < first ? first : form.last,
                });
              }}
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('workdays.last')}
            <input
              type="date"
              required
              min={form.first}
              value={form.last}
              onChange={(event) => setForm({ ...form, last: event.target.value })}
              className={field}
            />
          </label>
        </div>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {t(closure ? 'tree.save' : 'tree.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ImportDialog({ spans, onClose }: { spans: Span[]; onClose: () => void }) {
  const { t, formatDays, formatNumber } = useI18n();
  const [chosen, setChosen] = useState(() => new Set(spans.map((_, index) => index)));
  const add = useWorkdaysChange((picked: Span[]) =>
    postJson('/api/calendar/closures', { closures: picked }),
  );
  const toggle = (index: number) => {
    const next = new Set(chosen);
    if (!next.delete(index)) next.add(index);
    setChosen(next);
  };

  function submit(event: FormEvent) {
    event.preventDefault();
    add.mutate(
      spans.filter((_, index) => chosen.has(index)),
      { onSuccess: onClose },
    );
  }

  return (
    <Modal heading={t('workdays.import')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {spans.length === 0 ? (
          <p className="text-sm text-muted">{t('workdays.importNone')}</p>
        ) : (
          <>
            <p className="text-sm text-muted">{t('workdays.importNote')}</p>
            <ul className="flex max-h-80 flex-col gap-1 overflow-y-auto">
              {spans.map((span, index) => (
                <li key={index}>
                  <label className="flex items-baseline gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={chosen.has(index)}
                      onChange={() => toggle(index)}
                    />
                    <span className="min-w-0 flex-1 truncate">{span.name}</span>
                    <span className="whitespace-nowrap text-muted">
                      {formatDays(span.first, span.last)}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </>
        )}
        {add.isError && <p className="text-sm text-danger">{errorMessage(add.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          {spans.length > 0 && (
            <button
              type="submit"
              disabled={add.isPending || chosen.size === 0}
              className={primaryButton}
            >
              {`${t('workdays.importChosen')} (${formatNumber(chosen.size)})`}
            </button>
          )}
        </div>
      </form>
    </Modal>
  );
}

function Country({ workdays }: { workdays: Workdays }) {
  const { t, language, formatDays } = useI18n();
  const queryClient = useQueryClient();
  const countries = useMemo(() => {
    const names = new Intl.DisplayNames([language], { type: 'region' });
    return Object.keys(workdays.countries)
      .map((code) => [code, names.of(code) ?? code] as const)
      .sort((one, other) => one[1].localeCompare(other[1], language));
  }, [workdays.countries, language]);
  const save = useWorkdaysChange((chosen: { country: string; subdivision: string }) =>
    patchJson<Workdays>('/api/calendar/workdays', chosen),
  );
  const choose = (country: string, subdivision: string) =>
    save.mutate(
      { country, subdivision },
      { onSuccess: (data) => queryClient.setQueryData(WORKDAYS, data) },
    );
  const regions = workdays.countries[workdays.country] ?? [];
  return (
    <section className="flex flex-col gap-3">
      <p className="text-sm text-muted">{t('workdays.note')}</p>
      <div className="grid max-w-xl gap-3 sm:grid-cols-2">
        <Picker
          label={t('workdays.country')}
          value={workdays.country}
          options={countries}
          onChange={(country) => choose(country, '')}
        />
        {regions.length > 0 && (
          <Picker
            label={t('workdays.subdivision')}
            value={workdays.subdivision}
            options={[['', t('workdays.wholeCountry')], ...regions] as const}
            onChange={(subdivision) => choose(workdays.country, subdivision)}
          />
        )}
      </div>
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
      <h2 className="text-sm font-semibold">{t('workdays.holidays')}</h2>
      <ul className="flex max-w-xl flex-col text-sm">
        {workdays.holidays.map((each) => (
          <li key={`${each.date} ${each.en}`} className="flex gap-3 border-b border-line py-1.5">
            <span className="w-32 shrink-0 text-muted">{formatDays(each.date, each.date)}</span>
            <span>{language === 'hr' ? each.hr : each.en}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Hours({ workdays }: { workdays: Workdays }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [hours, setHours] = useState({ opens: workdays.opens, closes: workdays.closes });
  const save = useWorkdaysChange((chosen: { opens: string; closes: string }) =>
    patchJson<Workdays>('/api/calendar/workdays', chosen),
  );
  const kept = () => {
    if (!hours.opens || !hours.closes) return;
    if (hours.opens === workdays.opens && hours.closes === workdays.closes) return;
    save.mutate(hours, { onSuccess: (data) => queryClient.setQueryData(WORKDAYS, data) });
  };
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold">{t('workdays.hours')}</h2>
      <div className="grid max-w-xl grid-cols-2 gap-3">
        {(['opens', 'closes'] as const).map((each) => (
          <label key={each} className="flex flex-col gap-1 text-sm">
            {t(`workdays.${each}`)}
            <input
              type="time"
              required
              value={hours[each]}
              onChange={(event) => setHours({ ...hours, [each]: event.target.value })}
              onBlur={kept}
              className={field}
            />
          </label>
        ))}
      </div>
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
    </section>
  );
}

function Closures({ workdays }: { workdays: Workdays }) {
  const { t, formatDays } = useI18n();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const remove = useWorkdaysChange((closure: Closure) =>
    deleteJson(`/api/calendar/closures/${closure.id}`),
  );
  const read = useMutation({
    mutationFn: async (file: File) =>
      postJson<{ closures: Span[] }>('/api/calendar/closures/read', { ics: await file.text() }),
    onSuccess: (data) => setDialog({ type: 'import', spans: data.closures }),
  });
  const picker = useFilePicker(([file]) => read.mutate(file), {
    accept: '.ics,text/calendar',
    multiple: false,
  });
  const close = () => setDialog(null);
  const cell = 'px-2 py-2 whitespace-nowrap';
  return (
    <AdminFrame
      title={t('workdays.title')}
      primary={
        <PrimaryAction
          icon={Plus}
          label={t('workdays.new')}
          onClick={() => setDialog({ type: 'edit' })}
        />
      }
      more={
        <MenuItem
          icon={FileUp}
          label={t('workdays.import')}
          disabled={read.isPending}
          onSelect={picker.open}
        />
      }
    >
      {picker.element}
      <div className="flex w-full max-w-5xl flex-col gap-6">
        <Country workdays={workdays} />
        <Hours workdays={workdays} />
        <section className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold">{t('workdays.closures')}</h2>
          <p className="text-sm text-muted">{t('workdays.closuresNote')}</p>
          {read.isError && <p className="text-sm text-danger">{errorMessage(read.error, t)}</p>}
          {remove.isError && <p className="text-sm text-danger">{errorMessage(remove.error, t)}</p>}
          {workdays.closures.length === 0 ? (
            <p className="text-sm text-muted">{t('workdays.none')}</p>
          ) : (
            <table className="w-full border-collapse">
              <thead className="text-left text-sm text-muted">
                <tr className="border-b border-line">
                  <th className="w-full px-2 py-2 font-normal">{t('workdays.name')}</th>
                  <th className="px-2 py-2 font-normal">{t('workdays.days')}</th>
                  <th className="w-20" />
                </tr>
              </thead>
              <tbody>
                {workdays.closures.map((closure) => (
                  <tr key={closure.id} className="border-b border-line">
                    <td className={cell}>{closure.name}</td>
                    <td className={cell}>{formatDays(closure.first, closure.last)}</td>
                    <td className={`${cell} text-right`}>
                      <button
                        type="button"
                        onClick={() => setDialog({ type: 'edit', closure })}
                        aria-label={`${t('workdays.edit')}: ${closure.name}`}
                        className={iconButton}
                      >
                        <Pencil size={16} aria-hidden />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDialog({ type: 'delete', closure })}
                        aria-label={`${t('workdays.delete')}: ${closure.name}`}
                        className={iconButton}
                      >
                        <Trash2 size={16} aria-hidden />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
      {dialog?.type === 'edit' && <ClosureDialog closure={dialog.closure} onClose={close} />}
      {dialog?.type === 'import' && <ImportDialog spans={dialog.spans} onClose={close} />}
      {dialog?.type === 'delete' && (
        <ConfirmDialog
          heading={t('workdays.deleteTitle')}
          confirmLabel={t('workdays.delete')}
          onConfirm={() => remove.mutate(dialog.closure, { onSuccess: close })}
          onClose={close}
        >
          <strong>{dialog.closure.name}</strong> {t('workdays.deleteWarning')}
        </ConfirmDialog>
      )}
    </AdminFrame>
  );
}

export function WorkdaysPage() {
  const me = useSession().data?.user;
  const workdays = useQuery({
    queryKey: WORKDAYS,
    queryFn: () => getJson<Workdays>('/api/calendar/workdays'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return <Loaded query={workdays}>{(data) => <Closures workdays={data} />}</Loaded>;
}
