import { empty, keepAnswer, keeping, keptAnswer } from './kept';

export interface Revision {
  version: string;
}

export class ApiError extends Error {
  constructor(
    readonly path: string,
    readonly status: number,
    readonly code: string | undefined,
  ) {
    super(`${path}: HTTP ${status}${code ? ` ${code}` : ''}`);
  }
}

/** No answer from the backend itself: the connection, or the proxy before it while it restarts. */
export function unavailable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === 502 || error.status === 503 || error.status === 504;
}

export function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

async function refused(path: string, response: Response): Promise<never> {
  const body = await response.json().catch(() => ({}));
  throw new ApiError(path, response.status, body.error);
}

let confirming: (() => Promise<boolean>) | null = null;

/** Who asks the user to show again who they are, when the backend wants a recent confirmation
 * before what it was asked (D33); true once they have, and the request is sent again. */
export function onConfirm(confirm: () => Promise<boolean>): () => void {
  confirming = confirm;
  return () => {
    if (confirming === confirm) confirming = null;
  };
}

async function asksConfirmation(response: Response): Promise<boolean> {
  if (response.status !== 403 || !confirming) return false;
  const body = await response
    .clone()
    .json()
    .catch(() => ({}));
  return body.error === 'confirm_required';
}

function asked(path: string): string {
  const url = new URL(path, location.href);
  return url.pathname + url.search;
}

/** Fetches from the backend, which names in every answer the request it answered. A proxy on the
 * way has sent a request as another one sent alongside it, so the page got the other's answer; a
 * read is then asked again once, and anything else fails rather than take an answer not its own. */
export async function answered(path: string, init: RequestInit = {}): Promise<Response> {
  for (let tries = 0; ; tries++) {
    const response = await fetch(path, init);
    const other = response.headers.get('Answered-For');
    if (other === null) return response;
    const want = asked(path);
    if (other === want) return response;
    void response.body?.cancel();
    postJson('/api/crossed', { asked: want, answered: other }).catch((error: unknown) =>
      console.error('reporting a crossed answer failed', error),
    );
    if ((init.method ?? 'GET') !== 'GET' || tries > 0)
      throw new ApiError(path, response.status, 'answer_crossed');
  }
}

const SIGNED = ['/api/auth/session', '/api/auth/logout'];

/** The server said nobody is signed in: signed out, ended in the list of devices or run out, a
 * device that worked without the network empties itself (D45). */
function leftBy(path: string, response: Response, body?: unknown): boolean {
  if (response.status === 401) return true;
  return SIGNED.includes(path) && (body as { user?: unknown } | undefined)?.user === null;
}

function emptied(): void {
  if (keeping())
    empty().catch((error: unknown) => console.error('emptying the device failed', error));
}

/** What a read the server cannot answer was last answered on a device that keeps it (D45). */
async function kept<T>(path: string, init: RequestInit): Promise<{ body: T } | null> {
  if ((init.method ?? 'GET') !== 'GET') return null;
  try {
    return (await keptAnswer(path)) as { body: T } | null;
  } catch (error) {
    console.error('reading a kept answer failed', path, error);
    return null;
  }
}

async function request<T>(path: string, init: RequestInit = {}, fallback = true): Promise<T> {
  const sent = () =>
    answered(path, { ...init, headers: { Accept: 'application/json', ...init.headers } });
  let response: Response;
  try {
    response = await sent();
  } catch (error) {
    const held = fallback && (await kept<T>(path, init));
    if (held) return held.body;
    throw error;
  }
  if ((await asksConfirmation(response)) && (await confirming!())) response = await sent();
  if (!response.ok) {
    if (leftBy(path, response)) emptied();
    if (fallback && unavailable(new ApiError(path, response.status, undefined))) {
      const held = await kept<T>(path, init);
      if (held) return held.body;
    }
    return refused(path, response);
  }
  if (response.status === 204) return undefined as T;
  const body = (await response.json()) as T;
  if (leftBy(path, response, body)) emptied();
  else if ((init.method ?? 'GET') === 'GET')
    keepAnswer(path, body).catch((error: unknown) =>
      console.error('keeping an answer failed', path, error),
    );
  return body;
}

export function getJson<T>(path: string): Promise<T> {
  return request<T>(path);
}

/** A read only the server answers, never what a device kept of it. */
export function getFreshJson<T>(path: string): Promise<T> {
  return request<T>(path, {}, false);
}

export async function getBytes(path: string): Promise<Uint8Array> {
  const response = await answered(path);
  if (!response.ok) return refused(path, response);
  return new Uint8Array(await response.arrayBuffer());
}

function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export interface StoredFile {
  sha256: string;
  size: number;
  media_type: string;
}

function sendBytes<T>(
  method: string,
  path: string,
  body: Blob,
  headers: Record<string, string> = {},
): Promise<T> {
  return request<T>(path, {
    method,
    headers: {
      'Content-Type': body.type || 'application/octet-stream',
      'X-CSRFToken': csrfToken(),
      ...headers,
    },
    body,
  });
}

export function postBytes<T>(path: string, body: Blob): Promise<T> {
  return sendBytes<T>('POST', path, body);
}

export function putBytes<T>(path: string, body: Blob): Promise<T> {
  return sendBytes<T>('PUT', path, body);
}

interface Upload {
  id: string;
  size: number;
  received: number;
  chunk: number;
  blob: StoredFile | null;
}

const RETRIES = 5;

/** A failure the same piece may get past: the connection, a backend restarting, or a piece
 * already received whose answer was lost. */
function passing(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  return error.status === 409 || (error.status >= 500 && error.status !== 507);
}

/** Sends the file in the pieces the backend asks for; a piece that fails is sent again from
 * where the backend says it got to. `sent` hears how many bytes it has. */
async function sentInPieces(
  uploads: string,
  file: Blob,
  sent?: (bytes: number) => void,
): Promise<Upload & { blob: StoredFile }> {
  let state = await postJson<Upload>(uploads, { size: file.size });
  const path = `${uploads}/${state.id}`;
  let failed = 0;
  while (!state.blob) {
    try {
      if (failed) state = await getJson<Upload>(path);
      if (!state.blob)
        state = await sendBytes<Upload>(
          'PUT',
          path,
          file.slice(state.received, state.received + state.chunk),
          { 'Upload-Offset': String(state.received) },
        );
      failed = 0;
      sent?.(state.received);
    } catch (error) {
      if (!passing(error) || ++failed > RETRIES) throw error;
      await new Promise((done) => setTimeout(done, 500 * 2 ** failed));
    }
  }
  return { ...state, blob: state.blob };
}

export async function upload(file: Blob, sent?: (bytes: number) => void): Promise<StoredFile> {
  return (await sentInPieces('/api/uploads', file, sent)).blob;
}

/** Uploads the file through the link that asks someone outside for files, answering the
 * upload's id, which the link files into its folder. */
export async function uploadThrough(
  uploads: string,
  file: Blob,
  sent?: (bytes: number) => void,
): Promise<string> {
  return (await sentInPieces(uploads, file, sent)).id;
}

export function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  return send<T>('POST', path, body);
}

export function patchJson<T>(path: string, body: unknown): Promise<T> {
  return send<T>('PATCH', path, body);
}

export function putJson<T>(path: string, body: unknown): Promise<T> {
  return send<T>('PUT', path, body);
}

export function deleteJson(path: string): Promise<void> {
  return send<void>('DELETE', path);
}
