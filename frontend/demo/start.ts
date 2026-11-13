import { failStart, installBanner, tellServerNeeded } from './banner';
import { installClock } from './clock';
import { loadLive, loadMeta, loadResponses, missing } from './recording';
import { installFetch, Server } from './server';
import { installSockets } from './sockets';

const LANGUAGE = 'ponistra.language';

/** The demo speaks the recording's language until the visitor picks another. */
function chooseLanguage(language: string): void {
  try {
    if (!localStorage.getItem(LANGUAGE)) localStorage.setItem(LANGUAGE, language);
    document.documentElement.lang = localStorage.getItem(LANGUAGE)!;
  } catch {
    document.documentElement.lang = language;
  }
}

/** The worker answers what the page loads without fetch (images, frames, media, downloads) from
 * the recording, and the app starts only once it does. */
async function startWorker(): Promise<boolean> {
  if (!('serviceWorker' in navigator)) return false;
  navigator.serviceWorker.addEventListener('message', ({ data }) => {
    if (data?.demo === 'missing') missing(data.key);
    if (data?.demo) tellServerNeeded();
  });
  await navigator.serviceWorker.register('/sw.js');
  await navigator.serviceWorker.ready;
  if (navigator.serviceWorker.controller) return true;
  await new Promise((done) =>
    navigator.serviceWorker.addEventListener('controllerchange', done, { once: true }),
  );
  return true;
}

async function start(): Promise<void> {
  const [meta, answers, live] = await Promise.all([loadMeta(), loadResponses(), loadLive()]);
  installClock(meta.at);
  chooseLanguage(meta.language);
  const server = new Server(new Map(Object.entries(answers)), live);
  installFetch(server);
  installSockets(server);
  if (!(await startWorker())) return failStart('demo.noWorker');
  installBanner();
  await import('../src/main');
}

start().catch((error: unknown) => failStart(null, error));
