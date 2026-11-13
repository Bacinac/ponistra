import { FitAddon } from '@xterm/addon-fit';
import { Terminal as Xterm, type ITheme } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { RotateCcw, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { postJson } from './api';
import { useI18n } from './i18n';
import { useHeldRelease } from './release';
import { button, iconButton } from './styles';
import { codeText, errorMessage } from './tree';
import { onScheme } from './theme';

const PATH = '/api/workspace/terminal';
const EXITED = 4000;
const ANSI = [
  'black',
  'red',
  'green',
  'yellow',
  'blue',
  'magenta',
  'cyan',
  'white',
  'brightBlack',
  'brightRed',
  'brightGreen',
  'brightYellow',
  'brightBlue',
  'brightMagenta',
  'brightCyan',
  'brightWhite',
] as const;

/** The terminal's colours as theme.css has them for the scheme in force where it stands. */
function look(element: HTMLElement): ITheme {
  const probe = element.appendChild(document.createElement('span'));
  probe.style.display = 'none';
  const resolved = (color: string) => {
    probe.style.color = color;
    return getComputedStyle(probe).color;
  };
  const theme: ITheme = {
    background: resolved('var(--raised)'),
    foreground: resolved('var(--ink)'),
    cursor: resolved('var(--accent)'),
    cursorAccent: resolved('var(--raised)'),
    selectionBackground: resolved('var(--selected)'),
    selectionForeground: resolved('var(--ink)'),
    ...Object.fromEntries(ANSI.map((name, index) => [name, resolved(`var(--terminal-${index})`)])),
  };
  probe.remove();
  return theme;
}

/** A login shell in the project's folder of the workspace (KR25), ended when this is closed. */
export function TerminalPanel({
  folder,
  name,
  onClose,
}: {
  folder: string;
  name: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const host = useRef<HTMLDivElement>(null);
  const [opened, setOpened] = useState(0);
  const [ended, setEnded] = useState<'exited' | 'dropped' | null>(null);
  const [failure, setFailure] = useState<Error | null>(null);
  const [refused, setRefused] = useState<'copy' | 'paste' | null>(null);
  useHeldRelease(true);

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
    const sent = (data: string | Uint8Array<ArrayBuffer>) => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(data);
    };
    postJson(PATH).then(
      () => {
        if (gone) return;
        const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const opening = new WebSocket(`${scheme}//${location.host}${PATH}`);
        socket = opening;
        opening.binaryType = 'arraybuffer';
        opening.onopen = () =>
          opening.send(JSON.stringify({ folder, cols: terminal.cols, rows: terminal.rows }));
        opening.onmessage = (event) => {
          if (event.data instanceof ArrayBuffer) terminal.write(new Uint8Array(event.data));
        };
        opening.onclose = (event) => {
          if (!gone) setEnded(event.code === EXITED ? 'exited' : 'dropped');
        };
        terminal.focus();
      },
      (error: Error) => {
        if (!gone) setFailure(error);
      },
    );
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
        navigator.clipboard.readText().then(
          (text) => {
            setRefused(null);
            terminal.paste(text);
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
      element.removeEventListener('contextmenu', clicked);
      unscheme();
      sized.disconnect();
      typed.dispose();
      raw.dispose();
      resized.dispose();
      socket?.close();
      terminal.dispose();
    };
  }, [folder, opened]);

  const reopen = () => {
    setEnded(null);
    setFailure(null);
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
          onClick={onClose}
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
      {(ended || failure) && (
        <div role="status" className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className={ended === 'exited' ? 'text-muted' : 'text-danger'}>
            {failure ? errorMessage(failure, t) : t(`workspace.terminal.${ended!}`)}
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
