import { en } from '../src/i18n/en';
import { hr, type MessageKey } from '../src/i18n/hr';

/** Where someone who liked the demo installs Ponistra. */
const INSTALL = 'https://boskovic.biz/ponistra';
const NOTICE_FOR = 6000;

const STYLE = `
.ponistra-demo-bar {
  position: fixed; z-index: 20; inset: 0 0 auto 0; height: var(--demo-bar); box-sizing: border-box;
  display: flex; align-items: center; justify-content: center; gap: .6rem; padding: 0 1rem;
  border-bottom: 1px solid var(--line); background: var(--raised);
  color: var(--ink); font: 13px/1.3 system-ui, sans-serif;
}
.ponistra-demo-bar strong {
  padding: .1rem .55rem; border-radius: 999px; background: var(--accent); color: var(--on-accent);
}
.ponistra-demo-bar span {
  min-width: 0; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ponistra-demo-bar a { color: var(--link); white-space: nowrap; }
@media (max-width: 40rem) { .ponistra-demo-bar span { display: none; } }
:root { --demo-bar: 2rem; }
html { padding-top: var(--demo-bar); }
html .h-dvh { height: calc(100dvh - var(--demo-bar)); }
html .min-h-dvh { min-height: calc(100dvh - var(--demo-bar)); }
.ponistra-demo-notice {
  position: fixed; z-index: 2147483000; left: 50%; bottom: max(1rem, env(safe-area-inset-bottom));
  transform: translateX(-50%); max-width: calc(100vw - 2rem); box-sizing: border-box;
  padding: .5rem .8rem; border-radius: .5rem; background: var(--ink); color: var(--surface);
  font: 14px/1.4 system-ui, sans-serif; box-shadow: 0 2px 10px rgb(0 0 0 / .2);
}
.ponistra-demo-notice[hidden] { display: none; }
`;

function said(key: MessageKey): string {
  return (document.documentElement.lang === 'en' ? en : hr)[key];
}

let notice: HTMLElement | null = null;
let hiding: ReturnType<typeof setTimeout> | null = null;

/** Says on the page that what the visitor did needs the server, never leaving it to fail unseen. */
export function tellServerNeeded(): void {
  if (!notice) return;
  notice.textContent = said('error.demo_server');
  notice.hidden = false;
  if (hiding) clearTimeout(hiding);
  hiding = setTimeout(() => {
    notice!.hidden = true;
  }, NOTICE_FOR);
}

/** A strip that says this is the demo, linking to its credits and to installing Ponistra, in the
 * language the app shows. */
export function installBanner(): void {
  const style = document.createElement('style');
  style.textContent = STYLE;
  document.head.append(style);

  const bar = document.createElement('div');
  bar.className = 'ponistra-demo-bar';
  bar.setAttribute('role', 'note');
  const label = document.createElement('strong');
  const note = document.createElement('span');
  const credits = document.createElement('a');
  credits.href = '/demo-credits.html';
  const install = document.createElement('a');
  install.href = INSTALL;
  install.rel = 'noopener';
  bar.append(label, note, credits, install);

  notice = document.createElement('div');
  notice.className = 'ponistra-demo-notice';
  notice.setAttribute('role', 'status');
  notice.hidden = true;

  const write = () => {
    label.textContent = said('demo.label');
    note.textContent = said('demo.note');
    credits.textContent = said('demo.credits');
    install.textContent = said('demo.install');
  };
  write();
  new MutationObserver(write).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['lang'],
  });
  document.body.append(bar, notice);
}

/** The demo cannot start: said in place of the app. */
export function failStart(key: MessageKey | null, error?: unknown): void {
  const root = document.getElementById('root')!;
  const text = document.createElement('p');
  text.style.cssText = 'margin: 2rem; font: 16px/1.5 system-ui, sans-serif; color: var(--danger)';
  text.textContent = key ? said(key) : `${said('error.unexpected')}: ${String(error)}`;
  root.replaceChildren(text);
  if (error) console.error('The demo did not start', error);
}
