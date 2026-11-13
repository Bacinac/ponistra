// @vitest-environment jsdom
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { I18nProvider } from './i18n';
import { type Host, Limits, Machine, type Usage } from './workspaceLimits';

const RESETS = '2026-11-15T21:00:00.000Z';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime('2026-11-12T12:30:00.000Z');
});

afterEach(() => {
  vi.useRealTimers();
});

function shown(usage: Usage | null, onMeasure?: () => void) {
  return render(
    <I18nProvider>
      <Limits usage={usage} onMeasure={onMeasure} />
    </I18nProvider>,
  );
}

test('each window of the plan shows how much of it is used, a weekly one near its end in red', () => {
  const { container } = shown({
    at: '2026-11-12T12:20:00.000Z',
    windows: [
      { kind: 'session', name: null, percent: 12.4, resets: '2026-11-12T15:00:00.000Z' },
      { kind: 'week', name: null, percent: 82, resets: RESETS },
      { kind: 'model', name: 'Fable', percent: 4, resets: RESETS },
    ],
    credits: null,
    error: null,
  });
  const meters = screen.getAllByRole('meter');
  expect(meters.map((meter) => meter.getAttribute('aria-label'))).toEqual([
    'Sesija',
    'Tjedno',
    'Fable',
  ]);
  expect(meters.map((meter) => meter.getAttribute('aria-valuenow'))).toEqual(['12.4', '82', '4']);
  expect(screen.getByText('82 %').className).toContain('text-danger');
  expect(screen.getByText('4 %').className).not.toContain('text-danger');
  const measure = screen.getByRole('button', {
    name: /^izmjereno/,
    description: 'Izmjeri potrošnju sada',
  });
  expect(measure.textContent).toMatch(/^izmjereno \d/);
  // The time of the measure stands on the heading's line, above the bars.
  const order = [...container.querySelectorAll('h3, [role="meter"], button')];
  expect(order.indexOf(measure)).toBe(1);
  expect(screen.getByRole('region', { name: 'Anthropic' }).contains(measure)).toBe(true);
  expect(screen.queryByText(/Krediti|Troše/)).toBeNull();
});

test('credits spent past a limit and a measure that could not be read are said aloud', () => {
  shown({
    at: '2026-11-12T12:20:00.000Z',
    windows: [{ kind: 'model', name: 'Fable', percent: 100, resets: RESETS }],
    credits: { used: 1.5, currency: 'USD', using: true },
    error: 'unread: seven_day',
  });
  expect(screen.getByText(/^Troše se krediti:/).className).toContain('text-danger');
  screen.getByText('1,5 USD');
  expect(screen.getByText('Limiti se ne mogu pročitati').title).toBe('unread: seven_day');
});

test('nothing shows before the first measure', () => {
  const { container } = shown(null);
  expect(container.textContent).toBe('');
});

test('a click on the limits measures them again', async () => {
  const measured = vi.fn();
  const { container } = shown(
    {
      at: '2026-11-12T12:20:00.000Z',
      windows: [{ kind: 'week', name: null, percent: 61, resets: RESETS }],
      credits: null,
      error: null,
    },
    measured,
  );
  const limits = within(container);
  await userEvent.click(limits.getByRole('meter', { name: 'Tjedno' }));
  await userEvent.click(
    limits.getByRole('button', { name: /^izmjereno/, description: 'Izmjeri potrošnju sada' }),
  );
  expect(measured).toHaveBeenCalledTimes(2);
});

const GB = 1_000_000_000;

function machine(host: Host | null, onMeasure?: () => void) {
  return render(
    <I18nProvider>
      <Machine host={host} onMeasure={onMeasure} />
    </I18nProvider>,
  );
}

test('the server shows its processor, memory, swap and disk at a glance, a full one in red', async () => {
  const measured = vi.fn();
  const { container } = machine(
    {
      at: '2026-11-12T15:50:00.000Z',
      load: 2.4,
      cpus: 12,
      memory: { total: 64 * GB, available: 16 * GB },
      swap: { total: 8 * GB, free: 7 * GB },
      disk: { total: 800 * GB, free: 40 * GB },
      error: null,
    },
    measured,
  );
  const server = within(container).getByRole('region', { name: 'Radni prostor' });
  const button = within(server).getByRole('button');
  expect(button.textContent).toBe('Procesor20 %Memorija75 %Swap13 %Disk95 %');
  expect(within(server).getByText('95 %').className).toContain('text-danger');
  expect(within(server).getByText('75 %').className).not.toContain('text-danger');
  expect(within(server).getByTitle('Disk: zauzeto 760 GB od 800 GB')).toBeTruthy();
  expect(within(server).getByTitle('Procesor: opterećenje 2,4 na 12 niti')).toBeTruthy();
  await userEvent.click(button);
  expect(measured).toHaveBeenCalledOnce();
});

test('a server without swap leaves it out, and one that cannot be measured says so', () => {
  const { container, unmount } = machine({
    at: '2026-11-12T15:50:00.000Z',
    load: 1,
    cpus: 8,
    memory: { total: 32 * GB, available: 16 * GB },
    swap: null,
    disk: { total: 100 * GB, free: 50 * GB },
    error: null,
  });
  expect(within(container).queryByText('Swap')).toBeNull();
  unmount();
  const failed = machine({
    at: '2026-11-12T15:50:00.000Z',
    load: null,
    cpus: null,
    memory: null,
    swap: null,
    disk: null,
    error: 'unread',
  });
  within(failed.container).getByText('Stanje poslužitelja ne može se pročitati');
});
