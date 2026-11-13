import { QueryClient } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { followQueries, queriesTrail, reportCrash } from './crashes';

const report = {
  path: '/mail',
  message: 'boom',
  stack: 'at x',
  components: 'at Shell',
  queries: '',
};

function stubFetch(...answers: (Response | Error)[]) {
  const fetch = vi.fn();
  for (const answer of answers) {
    if (answer instanceof Error) fetch.mockRejectedValueOnce(answer);
    else fetch.mockResolvedValueOnce(answer);
  }
  vi.stubGlobal('document', { cookie: 'csrftoken=t' });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('reportCrash', () => {
  it('sends what broke the page to the server', async () => {
    const fetch = stubFetch(new Response(null, { status: 204 }));
    reportCrash(report);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    const [path, init] = fetch.mock.calls[0];
    expect(path).toBe('/api/crashes');
    expect(JSON.parse(init.body)).toEqual(report);
  });

  it('waits for the network a waking device has not got back yet', async () => {
    const fetch = stubFetch(new TypeError('Failed to fetch'), new Response(null, { status: 204 }));
    const window = new EventTarget();
    vi.stubGlobal('navigator', { onLine: false });
    vi.stubGlobal('window', window);
    reportCrash(report);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    await new Promise((resolve) => setTimeout(resolve));
    window.dispatchEvent(new Event('online'));
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  });

  it('tries again a while later when the network is there but the server is not reached', async () => {
    vi.useFakeTimers();
    const fetch = stubFetch(new TypeError('Failed to fetch'), new Response(null, { status: 204 }));
    vi.stubGlobal('navigator', { onLine: true });
    reportCrash(report);
    await vi.advanceTimersByTimeAsync(0);
    expect(fetch).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(5000);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

describe('queriesTrail', () => {
  it('tells when which query took data of which shape', async () => {
    const client = new QueryClient();
    const leave = followQueries(client);
    client.setQueryData(['calendar', 'window'], { holidays: [] });
    await client.fetchQuery({ queryKey: ['tree', 'favourites'], queryFn: () => [1, 2] });
    leave();
    const [first, ...rest] = queriesTrail().split('\n');
    expect(first).toMatch(/^release unknown, crashed at \d+$/);
    expect(rest.slice(-2)).toEqual([
      expect.stringMatching(/^\d+ success manual \["calendar","window"\] \{holidays\}$/),
      expect.stringMatching(/^\d+ success \["tree","favourites"\] \[2\]$/),
    ]);
  });
});
