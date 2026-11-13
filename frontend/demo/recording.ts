/** What the walk through the backend recorded (`scripts/demo.sh`), served beside the demo. */
export const RECORDING = '/demo-recording';

export interface Credit {
  work: string;
  author: string;
  licence: string;
  source: string;
  change?: string;
}

export interface Meta {
  /** When the walk recorded, which the demo's clock starts from. */
  at: string;
  language: string;
  credits: Credit[];
}

/** An answer as the backend gave it: JSON, or a body kept by its digest in `blobs/`. */
export type Recorded =
  { status: number; body: unknown } | { status: number; blob: string; type: string };

export type Frame = Record<string, unknown> & { type: string };

/** The page's own fetch, from before the demo answers it. */
export const realFetch = window.fetch.bind(window);

async function read<T>(path: string): Promise<T> {
  const response = await realFetch(`${RECORDING}/${path}`);
  if (!response.ok) throw new Error(`The demo's recording has no ${path}: ${response.status}`);
  return (await response.json()) as T;
}

let files: Promise<Set<string>> | null = null;

/** Fetches a recorded file the walk may not have made, as null when it did not. */
export async function recordedFile(path: string): Promise<Response | null> {
  files ??= read<string[]>('files.json').then((listed) => new Set(listed));
  if (!(await files).has(path)) return null;
  const response = await realFetch(`${RECORDING}/${path}`);
  if (!response.ok) throw new Error(`The demo's recording lost ${path}: ${response.status}`);
  return response;
}

export async function loadMeta(): Promise<Meta> {
  return read<Meta>('meta.json');
}

export async function loadResponses(): Promise<Record<string, Recorded>> {
  return read<Record<string, Recorded>>('responses.json');
}

export async function loadLive(): Promise<Frame | null> {
  const response = await recordedFile('live.json');
  return response && ((await response.json()) as Frame);
}

/** A gap in the recording, which the walk of a built demo fails on: never said of what the demo
 * declines on purpose. */
export function missing(key: string): void {
  console.warn('demo-missing ' + JSON.stringify({ key }));
}
