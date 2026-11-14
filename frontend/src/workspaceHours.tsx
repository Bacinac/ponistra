import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { deleteJson, getJson, patchJson, postJson, putJson } from './api';
import { Cancel, Close, ConfirmDialog, Labelled, Modal, NumberField, Picker } from './dialogs';
import { Loading } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { button, field, primaryButton } from './styles';
import { codeText, errorMessage, Failure } from './tree';

type Seconds = Record<string, number>;

interface Month {
  month: string;
  projects: Seconds;
  total: number;
  wall: number;
}

interface Day {
  day: string;
  projects: Seconds;
  total: number;
  wall: number;
}

interface Worked {
  months: Month[];
  month: string | null;
  days: Day[];
}

const cell = 'px-2 py-2 whitespace-nowrap';
const number = `${cell} text-right tabular-nums`;

function useWorked(month: string | null) {
  return useQuery({
    queryKey: ['worked', month],
    queryFn: () =>
      getJson<Worked>(`/api/workspace/hours${month ? `?month=${encodeURIComponent(month)}` : ''}`),
    placeholderData: (previous) => previous,
  });
}

function useClock() {
  const { formatNumber } = useI18n();
  return (seconds: number) => {
    const minutes = Math.round(seconds / 60);
    return `${formatNumber(Math.floor(minutes / 60))}:${String(minutes % 60).padStart(2, '0')}`;
  };
}

function local(day: string): Date {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(year, month - 1, date);
}

/** The time worked on the workspace's projects (VT1): each month by project, and the chosen month
 * by day. */
export function Hours({ named }: { named: (project: string) => string }) {
  const { t } = useI18n();
  const [settings, setSettings] = useState(false);
  return (
    <div className="flex min-h-0 flex-col gap-4">
      <div className="flex justify-end">
        <button type="button" className={button} onClick={() => setSettings(true)}>
          {t('workspace.hours.settings')}
        </button>
      </div>
      <Worked named={named} />
      {settings && (
        <Modal wide heading={t('workspace.view.hours')} onClose={() => setSettings(false)}>
          <TimeSettings />
          <div className="flex justify-end">
            <Close />
          </div>
        </Modal>
      )}
    </div>
  );
}

function Worked({ named }: { named: (project: string) => string }) {
  const { t, formatMonth, formatShortDay } = useI18n();
  const clock = useClock();
  const [month, setMonth] = useState<string | null>(null);
  const worked = useWorked(month);
  if (worked.isPending) return <Loading />;
  if (worked.isError) return <Failure error={worked.error} />;
  const { months, days } = worked.data;
  const shown = months.find((each) => each.month === worked.data.month) ?? null;
  if (!shown) return <p className="text-sm text-muted">{t('workspace.hours.none')}</p>;
  const projects = Object.entries(shown.projects)
    .sort(([one, first], [other, second]) => second - first || one.localeCompare(other))
    .map(([project]) => project);
  return (
    <div className="flex min-h-0 flex-col gap-6 overflow-y-auto">
      <section aria-label={t('workspace.hours.month')} className="flex flex-col gap-2">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted">{t('workspace.hours.month')}</span>
          <select
            value={shown.month}
            onChange={(event) => setMonth(event.target.value)}
            className={`${field} w-auto`}
          >
            {months.map((each) => (
              <option key={each.month} value={each.month}>
                {formatMonth(each.month)}
              </option>
            ))}
          </select>
        </label>
        <table className="w-full max-w-md border-collapse text-sm">
          <tbody>
            {projects.map((project) => (
              <tr key={project} className="border-b border-line">
                <td className={`${cell} w-full`}>{named(project)}</td>
                <td className={number}>{clock(shown.projects[project])}</td>
              </tr>
            ))}
            <tr className="border-b border-line font-semibold">
              <td className={cell}>{t('workspace.hours.total')}</td>
              <td className={number}>{clock(shown.total)}</td>
            </tr>
            <tr className="text-muted">
              <td className={cell}>{t('workspace.hours.wall')}</td>
              <td className={number}>{clock(shown.wall)}</td>
            </tr>
          </tbody>
        </table>
      </section>
      <section aria-label={t('workspace.hours.days')} className="flex flex-col gap-2">
        <h2 className="text-base font-semibold">{t('workspace.hours.days')}</h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="text-left text-muted">
              <tr className="border-b border-line">
                <th className={`${cell} font-normal`}>{t('workspace.hours.day')}</th>
                {projects.map((project) => (
                  <th key={project} className={`${number} font-normal`}>
                    {named(project)}
                  </th>
                ))}
                <th className={`${number} font-normal`}>{t('workspace.hours.total')}</th>
                <th className={`${number} font-normal`}>{t('workspace.hours.wall')}</th>
              </tr>
            </thead>
            <tbody>
              {days.map((day) => (
                <tr key={day.day} className="border-b border-line">
                  <td className={cell}>{formatShortDay(local(day.day))}</td>
                  {projects.map((project) => (
                    <td key={project} className={number}>
                      {day.projects[project] ? clock(day.projects[project]) : '·'}
                    </td>
                  ))}
                  <td className={`${number} font-semibold`}>{clock(day.total)}</td>
                  <td className={`${number} text-muted`}>{clock(day.wall)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

type Kind = 'clockify' | 'taskstreamer';

const KINDS: Kind[] = ['clockify', 'taskstreamer'];

interface Sheet {
  kind: Kind;
  address: string;
  person: string;
  offered: { id: string; name: string }[];
  projects: Record<string, string>;
  excluded: string[];
  label: string;
  since: string;
  nightly: boolean;
  error: string | null;
  written_at: string | null;
  due: number;
}

interface Sheets {
  projects: string[];
  removal: number | null;
  sheets: Partial<Record<Kind, Sheet>>;
}

interface Wrote {
  written: number;
  left: number;
  error: string | null;
}

interface ComparedDay {
  day: string;
  state: 'before' | 'open' | 'same' | 'differs';
  projects: { project: string; measured: number; own: number; others: number }[];
}

const SHEETS = ['worked', 'sheets'];

const STATES: Record<ComparedDay['state'], MessageKey> = {
  before: 'workspace.sheets.state.before',
  open: 'workspace.sheets.state.open',
  same: 'workspace.sheets.state.same',
  differs: 'workspace.sheets.state.differs',
};

function useSheets() {
  return useQuery({
    queryKey: SHEETS,
    queryFn: () => getJson<Sheets>('/api/workspace/sheets'),
  });
}

function useNamed() {
  const { t } = useI18n();
  return (project: string) =>
    project ? project.charAt(0).toUpperCase() + project.slice(1) : t('workspace.general');
}

function thisMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

function SheetForm({
  kind,
  sheet,
  projects,
  onClose,
}: {
  kind: Kind;
  sheet: Sheet | undefined;
  projects: string[];
  onClose: () => void;
}) {
  const { t } = useI18n();
  const named = useNamed();
  const queryClient = useQueryClient();
  const [key, setKey] = useState('');
  const [address, setAddress] = useState(sheet?.address ?? '');
  const [person, setPerson] = useState(sheet?.person ?? '');
  const [label, setLabel] = useState(sheet?.label ?? t('workspace.sheets.labelDefault'));
  const [since, setSince] = useState(sheet?.since ?? new Date().toLocaleDateString('sv'));
  const [nightly, setNightly] = useState(sheet?.nightly ?? false);
  const [mapped, setMapped] = useState<Record<string, string>>(sheet?.projects ?? {});
  const [excluded, setExcluded] = useState<string[]>(sheet?.excluded ?? []);
  const save = useMutation({
    mutationFn: (refresh: boolean) =>
      putJson<Sheet>(`/api/workspace/sheets/${kind}`, {
        ...(key ? { key } : {}),
        address,
        person,
        label,
        since,
        nightly,
        projects: Object.fromEntries(Object.entries(mapped).filter(([, theirs]) => theirs.trim())),
        excluded,
        refresh,
      }),
    onSuccess: async (_saved, refresh) => {
      await queryClient.invalidateQueries({ queryKey: SHEETS });
      if (!refresh) onClose();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(false);
  };
  const shownProjects = [...new Set([...projects, ...Object.keys(mapped), ...excluded])];
  return (
    <Modal heading={t(`workspace.sheets.${kind}`)} wide onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Labelled label={t('workspace.sheets.key')}>
          {(id) => (
            <input
              id={id}
              type="password"
              autoComplete="off"
              required={!sheet}
              value={key}
              placeholder={sheet ? t('workspace.sheets.keyKept') : undefined}
              onChange={(event) => setKey(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        {kind === 'taskstreamer' && (
          <>
            <Labelled label={t('workspace.sheets.address')}>
              {(id) => (
                <input
                  id={id}
                  type="url"
                  required
                  value={address}
                  onChange={(event) => setAddress(event.target.value)}
                  className={field}
                />
              )}
            </Labelled>
            <Labelled label={t('workspace.sheets.person')}>
              {(id) => (
                <input
                  id={id}
                  type="email"
                  required
                  value={person}
                  onChange={(event) => setPerson(event.target.value)}
                  className={field}
                />
              )}
            </Labelled>
          </>
        )}
        <Labelled label={t('workspace.sheets.label')}>
          {(id) => (
            <input
              id={id}
              required
              maxLength={100}
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <Labelled label={t('workspace.sheets.since')}>
          {(id) => (
            <input
              id={id}
              type="date"
              required
              value={since}
              onChange={(event) => setSince(event.target.value)}
              className={`${field} w-auto`}
            />
          )}
        </Labelled>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={nightly}
            onChange={(event) => setNightly(event.target.checked)}
          />
          {t('workspace.sheets.nightly')}
        </label>
        {sheet && (
          <section aria-label={t('workspace.sheets.projects')} className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold">{t('workspace.sheets.projects')}</h3>
              {kind === 'clockify' && (
                <button
                  type="button"
                  className={button}
                  disabled={save.isPending}
                  onClick={() => save.mutate(true)}
                >
                  {t('workspace.sheets.refresh')}
                </button>
              )}
            </div>
            <table className="w-full border-collapse text-sm">
              <thead className="text-left text-muted">
                <tr className="border-b border-line">
                  <th className={`${cell} font-normal`}>{t('workspace.sheets.project')}</th>
                  <th className={`${cell} w-full font-normal`}>{t('workspace.sheets.target')}</th>
                  <th className={`${cell} font-normal`}>{t('workspace.sheets.excluded')}</th>
                </tr>
              </thead>
              <tbody>
                {shownProjects.map((project) => {
                  const out = excluded.includes(project);
                  const target = mapped[project] ?? '';
                  const setTarget = (theirs: string) =>
                    setMapped((now) => ({ ...now, [project]: theirs }));
                  return (
                    <tr key={project} className="border-b border-line">
                      <td className={cell}>{named(project)}</td>
                      <td className="px-2 py-1">
                        {kind === 'clockify' ? (
                          <select
                            aria-label={named(project)}
                            value={target}
                            disabled={out}
                            onChange={(event) => setTarget(event.target.value)}
                            className={field}
                          >
                            <option value="">{t('workspace.sheets.notWritten')}</option>
                            {sheet.offered.map((each) => (
                              <option key={each.id} value={each.id}>
                                {each.name}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <input
                            aria-label={named(project)}
                            value={target}
                            disabled={out}
                            maxLength={255}
                            placeholder={t('workspace.sheets.notWritten')}
                            onChange={(event) => setTarget(event.target.value)}
                            className={field}
                          />
                        )}
                      </td>
                      <td className={`${cell} text-center`}>
                        <input
                          type="checkbox"
                          aria-label={`${t('workspace.sheets.excluded')}: ${named(project)}`}
                          checked={out}
                          onChange={(event) =>
                            setExcluded((now) =>
                              event.target.checked
                                ? [...now, project]
                                : now.filter((each) => each !== project),
                            )
                          }
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton} disabled={save.isPending}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Compared({ kind, sheet }: { kind: Kind; sheet: Sheet }) {
  const { t, formatMonth, formatShortDay } = useI18n();
  const clock = useClock();
  const [month, setMonth] = useState(thisMonth);
  const compared = useQuery({
    queryKey: [...SHEETS, kind, month],
    queryFn: () =>
      getJson<{ days: ComparedDay[] }>(
        `/api/workspace/sheets/${kind}/compare?month=${encodeURIComponent(month)}`,
      ),
    staleTime: Infinity,
  });
  const names = new Map(sheet.offered.map((each) => [each.id, each.name]));
  return (
    <section aria-label={t('workspace.sheets.compare')} className="flex flex-col gap-2">
      <label className="flex items-center gap-2 text-sm">
        <span className="text-muted">{t('workspace.hours.month')}</span>
        <input
          type="month"
          value={month}
          onChange={(event) => event.target.value && setMonth(event.target.value)}
          className={`${field} w-auto`}
        />
      </label>
      {compared.isPending ? (
        <Loading />
      ) : compared.isError ? (
        <p className="text-sm text-danger">{errorMessage(compared.error, t)}</p>
      ) : compared.data.days.length === 0 ? (
        <p className="text-sm text-muted">
          {formatMonth(month)}: {t('workspace.hours.none')}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead className="text-left text-muted">
              <tr className="border-b border-line">
                <th className={`${cell} font-normal`}>{t('workspace.hours.day')}</th>
                <th className={`${cell} font-normal`}>{t('workspace.sheets.project')}</th>
                <th className={`${number} font-normal`}>{t('workspace.sheets.measured')}</th>
                <th className={`${number} font-normal`}>{t('workspace.sheets.own')}</th>
                <th className={`${number} font-normal`}>{t('workspace.sheets.others')}</th>
                <th className={`${cell} font-normal`} />
              </tr>
            </thead>
            <tbody>
              {compared.data.days.flatMap((day) =>
                day.projects.map((each, index) => (
                  <tr key={`${day.day} ${each.project}`} className="border-b border-line">
                    <td className={cell}>{index === 0 && formatShortDay(local(day.day))}</td>
                    <td className={cell}>{names.get(each.project) ?? each.project}</td>
                    <td className={number}>{clock(each.measured)}</td>
                    <td className={number}>{clock(each.own)}</td>
                    <td className={`${number} text-muted`}>
                      {each.others ? clock(each.others) : '·'}
                    </td>
                    <td
                      className={`${cell} ${day.state === 'differs' ? 'text-danger' : 'text-muted'}`}
                    >
                      {index === 0 && t(STATES[day.state])}
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SheetCard({ kind, sheets }: { kind: Kind; sheets: Sheets }) {
  const { t, formatDate, formatDays, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const sheet = sheets.sheets[kind];
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [comparing, setComparing] = useState(false);
  const write = useMutation({
    mutationFn: () => postJson<Wrote>(`/api/workspace/sheets/${kind}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: SHEETS }),
  });
  const remove = useMutation({
    mutationFn: () => deleteJson(`/api/workspace/sheets/${kind}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SHEETS }),
  });
  return (
    <section
      aria-label={t(`workspace.sheets.${kind}`)}
      className="flex flex-col gap-2 rounded border border-line p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold">{t(`workspace.sheets.${kind}`)}</h3>
        <div className="flex flex-wrap gap-2">
          {sheet && (
            <>
              <button
                type="button"
                className={button}
                disabled={write.isPending}
                onClick={() => write.mutate()}
              >
                {t('workspace.sheets.write')}
              </button>
              <button
                type="button"
                className={button}
                aria-pressed={comparing}
                onClick={() => setComparing(!comparing)}
              >
                {t('workspace.sheets.compare')}
              </button>
              <button type="button" className={button} onClick={() => setRemoving(true)}>
                {t('workspace.sheets.remove')}
              </button>
            </>
          )}
          <button type="button" className={button} onClick={() => setEditing(true)}>
            {t(sheet ? 'workspace.sheets.edit' : 'workspace.sheets.setUp')}
          </button>
        </div>
      </div>
      {sheet && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted">{t('workspace.sheets.since')}</dt>
          <dd>{formatDays(sheet.since, sheet.since)}</dd>
          <dt className="text-muted">{t('workspace.sheets.mode')}</dt>
          <dd>{t(sheet.nightly ? 'workspace.sheets.nightly' : 'workspace.sheets.byHand')}</dd>
          <dt className="text-muted">{t('workspace.sheets.due')}</dt>
          <dd>{formatNumber(sheet.due)}</dd>
          {sheet.written_at && (
            <>
              <dt className="text-muted">{t('workspace.sheets.writtenAt')}</dt>
              <dd>{formatDate(sheet.written_at)}</dd>
            </>
          )}
        </dl>
      )}
      {sheet?.error && <p className="text-sm text-danger">{codeText(sheet.error, t)}</p>}
      {write.isSuccess && !write.data.error && (
        <p className="text-sm text-muted">
          {t('workspace.sheets.wrote')}: {formatNumber(write.data.written)}
        </p>
      )}
      {write.isError && <p className="text-sm text-danger">{errorMessage(write.error, t)}</p>}
      {sheet && comparing && <Compared kind={kind} sheet={sheet} />}
      {editing && (
        <SheetForm
          kind={kind}
          sheet={sheet}
          projects={sheets.projects}
          onClose={() => setEditing(false)}
        />
      )}
      {removing && (
        <ConfirmDialog
          heading={t('workspace.sheets.removeHeading')}
          confirmLabel={t('workspace.sheets.remove')}
          onConfirm={() => remove.mutate()}
          onClose={() => setRemoving(false)}
        >
          {t('workspace.sheets.removeText')}
        </ConfirmDialog>
      )}
    </section>
  );
}

type Removing = 'never' | 'now' | 'after';

function Removal({ after }: { after: number | null }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const change = useMutation({
    mutationFn: (given: number | null) =>
      patchJson<Sheets>('/api/workspace/sheets', { after: given }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SHEETS }),
  });
  const chosen: Removing = after === null ? 'never' : after === 0 ? 'now' : 'after';
  return (
    <section aria-label={t('workspace.removal.heading')} className="flex flex-col gap-3">
      <h2 className="text-base font-semibold">{t('workspace.removal.heading')}</h2>
      <div className="flex flex-wrap items-end gap-3">
        <Picker<Removing>
          label={t('workspace.removal.label')}
          value={chosen}
          options={[
            ['never', t('workspace.removal.never')],
            ['now', t('workspace.removal.now')],
            ['after', t('workspace.removal.after')],
          ]}
          onChange={(value) => change.mutate(value === 'never' ? null : value === 'now' ? 0 : 30)}
        />
        {chosen === 'after' && (
          <NumberField
            label={t('workspace.removal.days')}
            value={after ?? 30}
            min={1}
            max={365}
            step={1}
            onChange={(value) => change.mutate(value)}
          />
        )}
      </div>
      {change.isError && <p className="text-sm text-danger">{errorMessage(change.error, t)}</p>}
    </section>
  );
}

/** Where the time worked is written for others to read (VT2), and when the transcripts it was
 * measured from are removed (VT3). */
export function TimeSettings() {
  const { t } = useI18n();
  const sheets = useSheets();
  if (sheets.isPending) return <Loading />;
  if (sheets.isError) return <p className="text-sm text-danger">{errorMessage(sheets.error, t)}</p>;
  return (
    <div className="flex flex-col gap-6">
      <section aria-label={t('workspace.sheets.heading')} className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">{t('workspace.sheets.heading')}</h2>
        {KINDS.map((kind) => (
          <SheetCard key={kind} kind={kind} sheets={sheets.data} />
        ))}
      </section>
      <Removal after={sheets.data.removal} />
    </div>
  );
}
