import { FitAddon } from '@xterm/addon-fit';
import { Terminal as Xterm } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { RotateCcw, X } from 'lucide-react';
import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { postJson, unavailable } from './api';
import { clipboardHeld } from './clipboard';
import { useI18n } from './i18n';
import { useHeldRelease } from './release';
import { button, iconButton } from './styles';
import { codeText, errorMessage } from './tree';
import { look } from './terminalLook';
import { onScheme } from './theme';

const PATH = '/api/workspace/terminal';
// A socket that died on its way never reports closing, so the page asks and waits for the answer.
const PINGED = 20_000;
const ANSWERED_WITHIN = 10_000;
const FIRST_RETRY = 1_000;
const LAST_RETRY = 15_000;
const EXITED = 4000;
const TAKEN = 4409;
// Refused, a project the workspace does not know, too many terminals: trying again changes nothing.
const ENDED = new Set([4403, 4404, 4429]);
const CLOSE = { close: true };

/** A login shell in the project's folder of the workspace (KR25). It outlives this panel and its
 * connection: a connection lost is opened again and shown what the shell wrote meanwhile, and
 * only closing the panel or the shell's exit ends it. Another socket speaking the same protocol
 * (`path`) is told in its first message what `opensWith` names in place of the folder. */
export function TerminalPanel({
  folder = '',
  path = PATH,
  opensWith,
  name,
  onClose,
}: {
  folder?: string;
  path?: string;
  opensWith?: Record<string, string>;
  name: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const host = useRef<HTMLDivElement>(null);
  const [opened, setOpened] = useState(0);
  const closing = useEffectEvent(onClose);
  const [failure, setFailure] = useState<Error | null>(null);
  const [state, setState] = useState<'open' | 'lost' | 'taken' | 'unopened'>('open');
  const [refused, setRefused] = useState<'copy' | 'paste' | null>(null);
  const ending = useRef<() => void>(onClose);
  useHeldRelease(true);
  const told = JSON.stringify(opensWith ?? { folder });

  useEffect(() => {
    const element = host.current!;
    const terminal = new Xterm({
      cursorBlink: true,
      fontFamily: getComputedStyle(element).fontFamily,
      fontSize: 13,
      scrollback: 5000,
      theme: look(element),
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(element);
    // Hidden behind another view the element has no size, which would fit it to two columns.
    const fitted = () => {
      if (element.clientWidth && element.clientHeight) fit.fit();
    };
    fitted();
    const encoder = new TextEncoder();
    let socket: WebSocket | null = null;
    let gone = false;
    let pinging: ReturnType<typeof setInterval> | undefined;
    let unanswered: ReturnType<typeof setTimeout> | undefined;
    let retrying: ReturnType<typeof setTimeout> | undefined;
    let delay = FIRST_RETRY;
    const quiet = () => {
      clearInterval(pinging);
      clearTimeout(unanswered);
      unanswered = undefined;
    };
    const sent = (data: string | Uint8Array<ArrayBuffer>) => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(data);
    };
    const retried = () => {
      if (gone) return;
      setState('lost');
      retrying = setTimeout(connected, delay);
      delay = Math.min(delay * 2, LAST_RETRY);
    };
    const now = () => {
      if (retrying === undefined || gone) return;
      clearTimeout(retrying);
      connected();
    };
    const dropped = (lost: WebSocket) => {
      if (lost !== socket) return;
      socket = null;
      quiet();
      lost.onclose = lost.onmessage = null;
      lost.close();
      retried();
    };
    function connected() {
      retrying = undefined;
      postJson(path).then(
        () => {
          if (gone) return;
          const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
          const opening = new WebSocket(`${scheme}//${location.host}${path}`);
          socket = opening;
          opening.binaryType = 'arraybuffer';
          let fresh = true;
          opening.onopen = () => {
            const first = { ...JSON.parse(told), cols: terminal.cols, rows: terminal.rows };
            opening.send(JSON.stringify(first));
            pinging = setInterval(() => {
              opening.send('ping');
              unanswered ??= setTimeout(() => dropped(opening), ANSWERED_WITHIN);
            }, PINGED);
          };
          opening.onmessage = (event) => {
            if (event.data instanceof ArrayBuffer) {
              if (fresh) {
                fresh = false;
                delay = FIRST_RETRY;
                setState('open');
                terminal.reset();
              }
              terminal.write(new Uint8Array(event.data));
            } else if (event.data === 'pong') {
              clearTimeout(unanswered);
              unanswered = undefined;
            }
          };
          opening.onclose = ({ code }) => {
            if (gone || opening !== socket) return;
            socket = null;
            quiet();
            if (code === EXITED) {
              gone = true;
              closing();
            } else if (code === TAKEN) setState('taken');
            else if (ENDED.has(code)) setState('unopened');
            else retried();
          };
          terminal.focus();
        },
        (error: Error) => {
          if (gone) return;
          if (unavailable(error)) retried();
          else setFailure(error);
        },
      );
    }
    connected();
    ending.current = () => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(CLOSE));
      gone = true;
      closing();
    };
    const shown = () => {
      if (!document.hidden) now();
    };
    window.addEventListener('online', now);
    document.addEventListener('visibilitychange', shown);
    const typed = terminal.onData((data) => sent(encoder.encode(data)));
    const raw = terminal.onBinary((data) => sent(Uint8Array.from(data, (c) => c.charCodeAt(0))));
    const resized = terminal.onResize(({ cols, rows }) => sent(JSON.stringify({ cols, rows })));
    // A right click copies what is selected, or pastes where nothing is, as Windows Terminal does.
    const clicked = (event: MouseEvent) => {
      event.preventDefault();
      if (terminal.hasSelection()) {
        navigator.clipboard.writeText(terminal.getSelection()).then(
          () => setRefused(null),
          () => setRefused('copy'),
        );
        terminal.clearSelection();
      } else
        clipboardHeld().then(
          ({ text }) => {
            setRefused(null);
            if (text) terminal.paste(text);
          },
          () => setRefused('paste'),
        );
      terminal.focus();
    };
    element.addEventListener('contextmenu', clicked);
    const sized = new ResizeObserver(fitted);
    sized.observe(element);
    const unscheme = onScheme(() => {
      terminal.options.theme = look(element);
    });
    return () => {
      gone = true;
      quiet();
      clearTimeout(retrying);
      window.removeEventListener('online', now);
      document.removeEventListener('visibilitychange', shown);
      element.removeEventListener('contextmenu', clicked);
      unscheme();
      sized.disconnect();
      typed.dispose();
      raw.dispose();
      resized.dispose();
      socket?.close();
      terminal.dispose();
    };
  }, [path, told, opened]);

  const reopen = () => {
    setFailure(null);
    setState('open');
    setOpened((count) => count + 1);
  };
  return (
    <section aria-label={t('workspace.terminal')} className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">{name}</h2>
        <button
          type="button"
          aria-label={t('workspace.terminal.close')}
          title={t('workspace.terminal.close')}
          onClick={() => ending.current()}
          className={iconButton}
        >
          <X size={16} aria-hidden />
        </button>
      </div>
      <div className="relative min-h-[60dvh] flex-1 overflow-hidden rounded border border-line bg-raised p-1">
        <div ref={host} className="absolute inset-1 font-mono" />
      </div>
      {refused && (
        <p role="status" className="mt-2 text-sm text-danger">
          {refused === 'copy' ? t('workspace.copyFailed') : codeText('clipboard_refused', t)}
        </p>
      )}
      {!failure && state === 'lost' && (
        <p role="status" className="mt-2 text-sm text-muted">
          {t('workspace.terminal.lost')}
        </p>
      )}
      {(failure || state === 'taken' || state === 'unopened') && (
        <div role="status" className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-danger">
            {failure
              ? errorMessage(failure, t)
              : t(state === 'taken' ? 'workspace.terminal.taken' : 'workspace.terminal.unopened')}
          </span>
          <button type="button" onClick={reopen} className={button}>
            <RotateCcw size={14} aria-hidden />
            {t('workspace.terminal.reopen')}
          </button>
        </div>
      )}
    </section>
  );
}
