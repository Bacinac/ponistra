import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  csrfToken,
  deleteJson,
  getJson,
  onConfirm,
  patchJson,
  postJson,
  unavailable,
  upload,
} from './api';

afterEach(() => vi.unstubAllGlobals());

function stubBrowser(cookie: string, response: Response) {
  const fetch = vi.fn().mockResolvedValue(response);
  vi.stubGlobal('document', { cookie });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

describe('unavailable', () => {
  it('is a lost connection or a proxy without its backend, not a refusal or a fault', () => {
    expect(unavailable(new TypeError('Failed to fetch'))).toBe(true);
    expect(
      [502, 503, 504].map((status) => unavailable(new ApiError('/', status, undefined))),
    ).toEqual([true, true, true]);
    expect(
      [401, 403, 500].map((status) => unavailable(new ApiError('/', status, undefined))),
    ).toEqual([false, false, false]);
  });
});

describe('csrfToken', () => {
  it('reads the token among other cookies', () => {
    vi.stubGlobal('document', { cookie: 'sessionid=abc; csrftoken=t%2Bk; theme=dark' });
    expect(csrfToken()).toBe('t+k');
  });

  it('is empty without the cookie', () => {
    vi.stubGlobal('document', { cookie: 'sessionid=abc' });
    expect(csrfToken()).toBe('');
  });
});

describe('postJson', () => {
  it('sends the CSRF token read at call time', async () => {
    const fetch = stubBrowser('csrftoken=first', Response.json({ user: null }));
    await postJson('/api/auth/logout');
    expect(fetch.mock.calls[0][1].headers['X-CSRFToken']).toBe('first');
  });

  it('carries the server error code', async () => {
    stubBrowser('csrftoken=x', Response.json({ error: 'locked_out' }, { status: 429 }));
    const failure = await postJson('/api/auth/login').catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).code).toBe('locked_out');
  });
});

describe('a confirmation the backend asks for', () => {
  const asked = () => Response.json({ error: 'confirm_required' }, { status: 403 });

  function stubAnswers(...answers: Response[]) {
    const fetch = vi.fn();
    for (const answer of answers) fetch.mockResolvedValueOnce(answer);
    vi.stubGlobal('document', { cookie: 'csrftoken=t' });
    vi.stubGlobal('fetch', fetch);
    return fetch;
  }

  it('sends the request again once the user has confirmed', async () => {
    const fetch = stubAnswers(asked(), Response.json({ id: 1 }, { status: 201 }));
    const confirm = vi.fn().mockResolvedValue(true);
    const off = onConfirm(confirm);
    await expect(postJson('/api/app-passwords', { name: 'Telefon' })).resolves.toEqual({ id: 1 });
    off();
    expect(confirm).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[1]).toMatchObject([
      '/api/app-passwords',
      { method: 'POST', body: '{"name":"Telefon"}', headers: { 'X-CSRFToken': 't' } },
    ]);
  });

  it('fails with the refusal when the user turns it down', async () => {
    const fetch = stubAnswers(asked());
    const off = onConfirm(() => Promise.resolve(false));
    const failure = await postJson('/api/app-passwords').catch((error: unknown) => error);
    off();
    expect((failure as ApiError).code).toBe('confirm_required');
    expect(fetch).toHaveBeenCalledOnce();
  });

  it('leaves another refusal alone', async () => {
    stubAnswers(Response.json({ error: 'passkey_required' }, { status: 403 }));
    const confirm = vi.fn();
    const off = onConfirm(confirm);
    const failure = await postJson('/api/policy').catch((error: unknown) => error);
    off();
    expect((failure as ApiError).code).toBe('passkey_required');
    expect(confirm).not.toHaveBeenCalled();
  });
});

describe('patchJson and deleteJson', () => {
  it('send the CSRF token too', async () => {
    const fetch = stubBrowser('csrftoken=t', Response.json({}));
    await patchJson('/api/nodes/1', { title: 'Nacrt' });
    expect(fetch.mock.calls[0][1]).toMatchObject({
      method: 'PATCH',
      headers: { 'X-CSRFToken': 't' },
      body: '{"title":"Nacrt"}',
    });
  });

  it('resolve an empty 204 without parsing it', async () => {
    stubBrowser('csrftoken=t', new Response(null, { status: 204 }));
    await expect(deleteJson('/api/trash/1')).resolves.toBeUndefined();
  });
});

describe('upload', () => {
  const stored = { sha256: 'ab', size: 10, media_type: 'application/pdf' };
  const state = (received: number, blob: typeof stored | null = null) =>
    Response.json({ id: 'u1', size: 10, received, chunk: 4, blob });

  function stubUploads(...answers: (Response | Error)[]) {
    const fetch = vi.fn();
    for (const answer of answers)
      if (answer instanceof Error) fetch.mockRejectedValueOnce(answer);
      else fetch.mockResolvedValueOnce(answer);
    vi.stubGlobal('document', { cookie: 'csrftoken=t' });
    vi.stubGlobal('fetch', fetch);
    return fetch;
  }

  it('sends the file in the pieces asked for, each at its offset, with the CSRF token', async () => {
    const fetch = stubUploads(state(0), state(4), state(8), state(10, stored));
    const file = new File(['%PDF-1.7\n%'], 'Ponuda.pdf', { type: 'application/pdf' });
    const sent: number[] = [];
    await expect(upload(file, (bytes) => sent.push(bytes))).resolves.toEqual(stored);
    expect(fetch.mock.calls[0]).toMatchObject([
      '/api/uploads',
      { method: 'POST', body: '{"size":10}' },
    ]);
    const pieces = fetch.mock.calls.slice(1);
    expect(
      pieces.map(([path, init]) => [path, init.method, init.headers['Upload-Offset']]),
    ).toEqual([
      ['/api/uploads/u1', 'PUT', '0'],
      ['/api/uploads/u1', 'PUT', '4'],
      ['/api/uploads/u1', 'PUT', '8'],
    ]);
    expect(pieces[0][1].headers['X-CSRFToken']).toBe('t');
    expect(await Promise.all(pieces.map(([, init]) => (init.body as Blob).text()))).toEqual([
      '%PDF',
      '-1.7',
      '\n%',
    ]);
    expect(sent).toEqual([4, 8, 10]);
  });

  it('sends a failed piece again from where the backend got to', async () => {
    vi.useFakeTimers();
    const fetch = stubUploads(
      state(0),
      new TypeError('Failed to fetch'),
      state(4),
      Response.json({ error: 'bad_gateway' }, { status: 502 }),
      state(10, stored),
    );
    const done = upload(new File(['0123456789'], 'x.bin'));
    await vi.runAllTimersAsync();
    await expect(done).resolves.toEqual(stored);
    expect(fetch.mock.calls.map(([path, init]) => [path, init?.method ?? 'GET'])).toEqual([
      ['/api/uploads', 'POST'],
      ['/api/uploads/u1', 'PUT'],
      ['/api/uploads/u1', 'GET'],
      ['/api/uploads/u1', 'PUT'],
      ['/api/uploads/u1', 'GET'],
    ]);
    vi.useRealTimers();
  });

  it('gives up on what no retry gets past', async () => {
    const fetch = stubUploads(state(0), Response.json({ error: 'no_room' }, { status: 507 }));
    const failure = await upload(new File(['0123456789'], 'x.bin')).catch((error) => error);
    expect((failure as ApiError).code).toBe('no_room');
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});

describe('an answer meant for another request', () => {
  function answering(...answers: Response[]) {
    const fetch = vi.fn();
    for (const answer of answers) fetch.mockResolvedValueOnce(answer);
    vi.stubGlobal('document', { cookie: 'csrftoken=t' });
    vi.stubGlobal('location', { href: 'https://ponistra.test/mail' });
    vi.stubGlobal('fetch', fetch);
    return fetch;
  }

  const answer = (body: unknown, path: string) =>
    Response.json(body, { headers: { 'Answered-For': path } });

  it('takes the answer named for what it asked, its query encoded as sent', async () => {
    answering(answer({ found: 1 }, '/api/search?q=%C5%A1to%20je'));
    expect(await getJson('/api/search?q=što je')).toEqual({ found: 1 });
  });

  it('asks a read again once and reports the crossing', async () => {
    const fetch = answering(
      answer({ children: [] }, '/api/nodes/favourites'),
      new Response(null, { status: 204 }),
      answer({ node: { id: 'n' } }, '/api/nodes/n'),
    );
    expect(await getJson('/api/nodes/n')).toEqual({ node: { id: 'n' } });
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      '/api/nodes/n',
      '/api/crossed',
      '/api/nodes/n',
    ]);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
      asked: '/api/nodes/n',
      answered: '/api/nodes/favourites',
    });
  });

  it('fails a read crossed twice', async () => {
    answering(
      answer({}, '/api/version'),
      new Response(null, { status: 204 }),
      answer({}, '/api/version'),
      new Response(null, { status: 204 }),
    );
    const failure = await getJson('/api/mail/later').catch((error: unknown) => error);
    expect((failure as ApiError).code).toBe('answer_crossed');
  });

  it('never sends a change again', async () => {
    const fetch = answering(answer({}, '/api/mail/drafts'), new Response(null, { status: 204 }));
    const failure = await postJson('/api/mail/send').catch((error: unknown) => error);
    expect((failure as ApiError).code).toBe('answer_crossed');
    expect(fetch.mock.calls.filter(([path]) => path === '/api/mail/send')).toHaveLength(1);
  });
});
