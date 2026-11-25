import { useState } from 'react';
import { Headed } from '../headed';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import {
  MachineError,
  SPANS,
  useHistory,
  usePressure,
  type PressureNow,
  type Span,
  type Values,
} from './api';
import { Chart } from './Chart';
import { card, Failure, Loaded, Pill, table, useFormats } from './parts';

export function Pressure() {
  const { t } = useI18n();
  const now = usePressure();
  const gathering = now.error instanceof MachineError && now.error.status === 503;
  return (
    <div className="flex flex-col gap-6">
      {gathering ? (
        <p className="text-sm text-muted">{t('machine.pressure.gathering')}</p>
      ) : (
        <Loaded query={now}>{(data) => <Now now={data} />}</Loaded>
      )}
      <PressureHistory />
    </div>
  );
}

function Now({ now }: { now: PressureNow }) {
  const { t } = useI18n();
  const format = useFormats();
  const { machine } = now;
  return (
    <>
      <section className={card} aria-label={t('machine.pressure.causes')}>
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold">{t('machine.pressure.causes')}</h2>
          <span className="text-xs text-muted">{format.date(now.at)}</span>
        </div>
        {now.causes.length === 0 ? (
          <p className="text-sm text-muted">{t('machine.pressure.calm')}</p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {now.causes.map((cause) => (
              <li key={cause.resource} className="flex flex-wrap items-center gap-2">
                <Pill tone={cause.level === 'congested' ? 'bad' : 'quiet'}>
                  {t(`machine.pressure.${cause.level}`)}
                </Pill>
                <span className="font-medium">{t(`machine.resource.${cause.resource}`)}</span>
                <span className="tabular-nums text-muted">{format.percent(cause.wait)}</span>
                <span>{cause.text}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <Headed heading={t('machine.pressure.lastMinute')}>
        <dl className="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-3 text-sm">
          {(
            [
              ['machine.measure.cpu', `${format.number(machine.cpu)} ${t('machine.cores')}`],
              ['machine.measure.cpuWait', format.percent(machine.cpu_wait)],
              ['machine.measure.memory', format.bytes(machine.memory)],
              ['machine.measure.memoryWait', format.percent(machine.memory_wait)],
              ['machine.measure.memoryStall', format.percent(machine.memory_stall)],
              ['machine.measure.ioWait', format.percent(machine.io_wait)],
              ['machine.measure.ioStall', format.percent(machine.io_stall)],
              ['machine.measure.read', format.rate(machine.read)],
              ['machine.measure.write', format.rate(machine.write)],
              ['machine.measure.receive', format.rate(machine.receive)],
              ['machine.measure.send', format.rate(machine.send)],
            ] as const
          ).map(([label, value]) => (
            <div key={label} className="rounded border border-line px-3 py-2">
              <dt className="text-xs text-muted">{t(label)}</dt>
              <dd className="text-base font-medium tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      </Headed>
      {now.guests.length > 0 && (
        <Headed heading={t('machine.pressure.guests')}>
          <div className="overflow-x-auto">
            <table className={table}>
              <thead>
                <tr>
                  <th>{t('machine.guest')}</th>
                  <th>{t('machine.resource.cpu')}</th>
                  <th>{t('machine.resource.memory')}</th>
                  <th>{t('machine.share.disk')}</th>
                  <th>{t('machine.share.network')}</th>
                  <th>{t('machine.limits')}</th>
                </tr>
              </thead>
              <tbody>
                {now.guests.map((guest) => (
                  <tr key={guest.name}>
                    <td>
                      {guest.name}
                      <span className="ml-2 text-xs text-muted">{guest.kind}</span>
                    </td>
                    <td className="tabular-nums">
                      {format.percent(guest.share.cpu)}
                      <span className="block text-xs text-muted">
                        {format.number(guest.values.cpu)} {t('machine.cores')}
                      </span>
                    </td>
                    <td className="tabular-nums">
                      {format.percent(guest.share.memory)}
                      <span className="block text-xs text-muted">
                        {format.bytes(guest.values.memory)}
                      </span>
                    </td>
                    <td className="tabular-nums">{format.percent(guest.share.disk)}</td>
                    <td className="tabular-nums">{format.percent(guest.share.network)}</td>
                    <td className="text-xs text-muted">
                      {[guest.cpu_limit, guest.memory_limit].filter(Boolean).join(' · ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Headed>
      )}
    </>
  );
}

type Measure = keyof Values;

const CHARTS: {
  title: MessageKey;
  measures: { key: Measure; label: MessageKey }[];
  unit: 'cores' | 'percent' | 'bytes' | 'rate';
}[] = [
  {
    title: 'machine.measure.cpu',
    measures: [{ key: 'cpu', label: 'machine.measure.cpu' }],
    unit: 'cores',
  },
  {
    title: 'machine.chart.waiting',
    measures: [
      { key: 'cpu_wait', label: 'machine.resource.cpu' },
      { key: 'memory_wait', label: 'machine.resource.memory' },
      { key: 'io_wait', label: 'machine.resource.io' },
    ],
    unit: 'percent',
  },
  {
    title: 'machine.chart.stalled',
    measures: [
      { key: 'memory_stall', label: 'machine.resource.memory' },
      { key: 'io_stall', label: 'machine.resource.io' },
    ],
    unit: 'percent',
  },
  {
    title: 'machine.measure.memory',
    measures: [{ key: 'memory', label: 'machine.measure.memory' }],
    unit: 'bytes',
  },
  {
    title: 'machine.chart.disk',
    measures: [
      { key: 'read', label: 'machine.measure.read' },
      { key: 'write', label: 'machine.measure.write' },
    ],
    unit: 'rate',
  },
  {
    title: 'machine.chart.network',
    measures: [
      { key: 'receive', label: 'machine.measure.receive' },
      { key: 'send', label: 'machine.measure.send' },
    ],
    unit: 'rate',
  },
];

/** The machine's values, or one guest's, over a span chosen above the charts. */
export function PressureHistory({ guest }: { guest?: string }) {
  const { t } = useI18n();
  const format = useFormats();
  const [span, setSpan] = useState<Span>('90m');
  const history = useHistory(span, guest);
  const units = {
    cores: (value: number) => format.number(value),
    percent: format.percent,
    bytes: format.bytes,
    rate: format.rate,
  };
  return (
    <Headed
      heading={t('machine.pressure.history')}
      action={
        <div role="group" aria-label={t('machine.pressure.span')} className="flex gap-1">
          {SPANS.map((each) => (
            <button
              key={each}
              type="button"
              aria-pressed={span === each}
              onClick={() => setSpan(each)}
              className="rounded px-2 py-1 text-sm text-muted hover:bg-hover aria-pressed:bg-selected aria-pressed:font-semibold aria-pressed:text-accent"
            >
              {t(`machine.span.${each}`)}
            </button>
          ))}
        </div>
      }
    >
      {history.error instanceof MachineError && history.error.status === 503 ? (
        <p className="text-sm text-muted">{t('machine.pressure.gathering')}</p>
      ) : history.error ? (
        <Failure error={history.error} />
      ) : !history.data ? (
        <p className="text-sm text-muted">{t('machine.loading')}</p>
      ) : history.data.points.length === 0 ? (
        <p className="text-sm text-muted">{t('machine.pressure.gathering')}</p>
      ) : (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          {CHARTS.map((chart) => (
            <Chart
              key={chart.title}
              title={t(chart.title)}
              times={history.data.points.map((point) => new Date(point.at))}
              series={chart.measures.map((measure) => ({
                label: t(measure.label),
                values: history.data.points.map((point) => point.values[measure.key]),
              }))}
              format={units[chart.unit]}
            />
          ))}
        </div>
      )}
    </Headed>
  );
}
