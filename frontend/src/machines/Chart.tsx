import { useLayoutEffect, useRef, useState, type PointerEvent } from 'react';
import { CHART_COLORS, onScreen } from '../editor/colors';
import { useI18n } from '../i18n';

export interface Series {
  label: string;
  values: number[];
}

const HEIGHT = 160;
const PAD = { top: 8, right: 8, bottom: 22, left: 64 };

/** A measure over time: one line per series in the chart palette's order, one axis from zero,
 * a crosshair with every series' value under the pointer and their extremes as a table. */
export function Chart({
  title,
  times,
  series,
  format,
}: {
  title: string;
  times: Date[];
  series: Series[];
  format: (value: number) => string;
}) {
  const { t, formatTime, formatShortDay } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useLayoutEffect(() => {
    const element = box.current!;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    setWidth(element.clientWidth);
    return () => observer.disconnect();
  }, []);

  const count = times.length;
  const top = Math.max(...series.flatMap((each) => each.values), 0) || 1;
  const plotWidth = Math.max(width - PAD.left - PAD.right, 1);
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const x = (index: number) => PAD.left + (count > 1 ? (index / (count - 1)) * plotWidth : 0);
  const y = (value: number) => PAD.top + plotHeight - (value / top) * plotHeight;
  const days = count > 1 && times[count - 1].getTime() - times[0].getTime() > 86_400_000;
  const when = (date: Date) =>
    days ? `${formatShortDay(date)} ${formatTime(date)}` : formatTime(date);
  const ticks = count > 1 ? [0, Math.floor((count - 1) / 2), count - 1] : [0];

  const pointed = (event: PointerEvent<SVGSVGElement>) => {
    const left = event.clientX - event.currentTarget.getBoundingClientRect().left - PAD.left;
    const index = Math.round((left / plotWidth) * (count - 1));
    setHover(count ? Math.max(0, Math.min(count - 1, index)) : null);
  };

  return (
    <figure className="flex min-w-0 flex-col gap-1">
      <figcaption className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-sm font-medium">{title}</span>
        {series.length > 1 &&
          series.map((each, index) => (
            <span key={each.label} className="flex items-center gap-1.5 text-xs text-muted">
              <span
                aria-hidden
                className="inline-block h-0.5 w-3 rounded-full"
                style={{ background: onScreen(CHART_COLORS[index]) }}
              />
              {each.label}
            </span>
          ))}
      </figcaption>
      <div ref={box} className="relative">
        {width > 0 && count > 0 && (
          <svg
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={title}
            className="block touch-none select-none"
            onPointerMove={pointed}
            onPointerDown={pointed}
            onPointerLeave={() => setHover(null)}
          >
            {[0, 0.5, 1].map((share) => (
              <g key={share}>
                <line
                  x1={PAD.left}
                  x2={PAD.left + plotWidth}
                  y1={y(top * share)}
                  y2={y(top * share)}
                  className="stroke-line"
                  strokeWidth={1}
                />
                <text
                  x={PAD.left - 6}
                  y={y(top * share)}
                  dy="0.32em"
                  textAnchor="end"
                  className="fill-muted text-[11px] tabular-nums"
                >
                  {format(top * share)}
                </text>
              </g>
            ))}
            {ticks.map((index, at) => (
              <text
                key={index}
                x={x(index)}
                y={HEIGHT - 6}
                textAnchor={at === 0 ? 'start' : at === ticks.length - 1 ? 'end' : 'middle'}
                className="fill-muted text-[11px] tabular-nums"
              >
                {when(times[index])}
              </text>
            ))}
            {series.map((each, index) => (
              <polyline
                key={each.label}
                fill="none"
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
                style={{ stroke: onScreen(CHART_COLORS[index]) }}
                points={each.values.map((value, at) => `${x(at)},${y(value)}`).join(' ')}
              />
            ))}
            {hover !== null && (
              <g>
                <line
                  x1={x(hover)}
                  x2={x(hover)}
                  y1={PAD.top}
                  y2={PAD.top + plotHeight}
                  className="stroke-muted"
                  strokeWidth={1}
                />
                {series.map((each, index) => (
                  <circle
                    key={each.label}
                    cx={x(hover)}
                    cy={y(each.values[hover])}
                    r={4}
                    strokeWidth={2}
                    className="stroke-raised"
                    style={{ fill: onScreen(CHART_COLORS[index]) }}
                  />
                ))}
              </g>
            )}
          </svg>
        )}
        {hover !== null && (
          <div
            role="status"
            className="pointer-events-none absolute top-0 z-10 rounded border border-line bg-raised px-2 py-1 text-xs shadow-lg"
            style={x(hover) > width / 2 ? { right: width - x(hover) + 8 } : { left: x(hover) + 8 }}
          >
            <div className="text-muted">{when(times[hover])}</div>
            {series.map((each, index) => (
              <div key={each.label} className="flex items-center gap-1.5 tabular-nums">
                <span
                  aria-hidden
                  className="inline-block size-2 rounded-full"
                  style={{ background: onScreen(CHART_COLORS[index]) }}
                />
                {series.length > 1 && <span className="text-muted">{each.label}</span>}
                <span>{format(each.values[hover])}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted">{t('machine.chart.table')}</summary>
        <table className="mt-1 tabular-nums [&_td]:pr-4 [&_th]:pr-4 [&_th]:text-left [&_th]:font-medium [&_th]:text-muted">
          <thead>
            <tr>
              <th />
              <th>{t('machine.chart.lowest')}</th>
              <th>{t('machine.chart.average')}</th>
              <th>{t('machine.chart.highest')}</th>
              <th>{t('machine.chart.last')}</th>
            </tr>
          </thead>
          <tbody>
            {series.map((each) => (
              <tr key={each.label}>
                <th scope="row">{each.label}</th>
                <td>{format(Math.min(...each.values))}</td>
                <td>{format(each.values.reduce((sum, value) => sum + value, 0) / count)}</td>
                <td>{format(Math.max(...each.values))}</td>
                <td>{format(each.values[count - 1])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
