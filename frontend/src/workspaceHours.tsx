import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { getJson } from './api';
import { Loading } from './frame';
import { useI18n } from './i18n';
import { field } from './styles';
import { Failure } from './tree';

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

function local(day: string): Date {
  const [year, month, date] = day.split('-').map(Number);
  return new Date(year, month - 1, date);
}

/** The time worked on the workspace's projects (VT1): each month by project, and the chosen month
 * by day. */
export function Hours({ named }: { named: (project: string) => string }) {
  const { t, formatMonth, formatNumber, formatShortDay } = useI18n();
  const [month, setMonth] = useState<string | null>(null);
  const worked = useWorked(month);
  if (worked.isPending) return <Loading />;
  if (worked.isError) return <Failure error={worked.error} />;
  const { months, days } = worked.data;
  const shown = months.find((each) => each.month === worked.data.month) ?? null;
  const clock = (seconds: number) => {
    const minutes = Math.round(seconds / 60);
    return `${formatNumber(Math.floor(minutes / 60))}:${String(minutes % 60).padStart(2, '0')}`;
  };
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
