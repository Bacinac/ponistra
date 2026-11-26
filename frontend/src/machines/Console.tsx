import { FitAddon } from '@xterm/addon-fit';
import { Terminal as Xterm } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { useEffect, useId, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import { useI18n } from '../i18n';
import { button, primaryButton } from '../styles';
import { look } from '../terminalLook';
import { onScheme } from '../theme';
import {
  guestPath,
  MachineError,
  socketUrl,
  useMachineApi,
  type ConsoleTicket,
  type ConsoleType,
  type MachineApi,
} from './api';
import { Failure } from './parts';

/** Why a console is not shown: the guest is another account's, it refused (another client holds
 * a text console, the guest is not running), or the connection ended. */
type Outcome =
  | { kind: 'open' }
  | { kind: 'foreign' }
  | { kind: 'refused'; error: Error }
  | { kind: 'ended'; error?: Error };

const REFUSED = 1011;

async function ticket(
  api: MachineApi,
  guest: string,
  type: ConsoleType,
  force: boolean,
  size?: { width: number; height: number },
): Promise<ConsoleTicket> {
  return api.send<ConsoleTicket>('POST', `${guestPath(guest)}/console`, {
    type,
    ...size,
    ...(force && { force }),
  });
}

function failed(error: unknown, set: (outcome: Outcome) => void) {
  if (error instanceof MachineError && error.status === 403) set({ kind: 'foreign' });
  else set({ kind: 'refused', error: error as Error });
}

/** A guest's console: a VM's screen over SPICE, or a text console (a container's /dev/console, a
 * VM's serial port). The guest's own login answers, never a shell the agent opens. */
export function Console() {
  const { t } = useI18n();
  const { name = '' } = useParams();
  const [search] = useSearchParams();
  const type: ConsoleType = search.get('type') === 'vga' ? 'vga' : 'console';
  const [attempt, setAttempt] = useState({ count: 0, force: false });
  const [outcome, setOutcome] = useState<Outcome>({ kind: 'open' });
  const again = (force: boolean) => {
    setOutcome({ kind: 'open' });
    setAttempt(({ count }) => ({ count: count + 1, force }));
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link to=".." relative="path" className="text-sm text-link hover:underline">
          ← {name}
        </Link>
        <h2 className="text-base font-semibold">
          {t(type === 'vga' ? 'machine.console.screen' : 'machine.console.text')} · {name}
        </h2>
      </div>
      {outcome.kind === 'foreign' && <p className="text-sm">{t('machine.guest.foreignConsole')}</p>}
      {outcome.kind === 'refused' && (
        <div className="flex flex-wrap items-center gap-3">
          <Failure error={outcome.error} />
          {type === 'console' &&
            outcome.error instanceof MachineError &&
            outcome.error.status === 409 && (
              <button type="button" className={button} onClick={() => again(true)}>
                {t('machine.console.takeOver')}
              </button>
            )}
        </div>
      )}
      {outcome.kind === 'ended' && (
        <div className="flex flex-wrap items-center gap-3">
          {outcome.error ? (
            <Failure error={outcome.error} />
          ) : (
            <p className="text-sm text-muted">{t('machine.console.ended')}</p>
          )}
          <button type="button" className={primaryButton} onClick={() => again(false)}>
            {t('machine.console.reconnect')}
          </button>
        </div>
      )}
      {outcome.kind !== 'foreign' &&
        (type === 'vga' ? (
          <Screen key={attempt.count} guest={name} force={attempt.force} setOutcome={setOutcome} />
        ) : (
          <Text key={attempt.count} guest={name} force={attempt.force} setOutcome={setOutcome} />
        ))}
    </div>
  );
}

function Text({
  guest,
  force,
  setOutcome,
}: {
  guest: string;
  force: boolean;
  setOutcome: (outcome: Outcome) => void;
}) {
  const { t } = useI18n();
  const api = useMachineApi();
  const host = useRef<HTMLDivElement>(null);
  const [connected, setConnected] = useState(false);

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
    const typed = terminal.onData((data) => sent(encoder.encode(data)));
    const raw = terminal.onBinary((data) =>
      sent(Uint8Array.from(data, (char) => char.charCodeAt(0))),
    );
    const resized = terminal.onResize(({ cols, rows }) =>
      sent(JSON.stringify({ width: cols, height: rows })),
    );
    ticket(api, guest, 'console', force, {
      width: Math.min(terminal.cols, 1000),
      height: Math.min(terminal.rows, 1000),
    })
      .then((opened) => {
        if (gone) return;
        socket = new WebSocket(socketUrl(api, opened.path), 'binary');
        socket.binaryType = 'arraybuffer';
        socket.onopen = () => {
          setConnected(true);
          terminal.focus();
        };
        socket.onmessage = (event) => {
          if (event.data instanceof ArrayBuffer) terminal.write(new Uint8Array(event.data));
        };
        socket.onclose = (event) => {
          setConnected(false);
          if (gone) return;
          setOutcome({
            kind: 'ended',
            error:
              event.code === REFUSED ? new Error(event.reason || String(event.code)) : undefined,
          });
        };
      })
      .catch((error) => {
        if (!gone) failed(error, setOutcome);
      });
    const sized = new ResizeObserver(fitted);
    sized.observe(element);
    const unscheme = onScheme(() => {
      terminal.options.theme = look(element);
    });
    return () => {
      gone = true;
      socket?.close();
      sized.disconnect();
      unscheme();
      typed.dispose();
      raw.dispose();
      resized.dispose();
      terminal.dispose();
    };
  }, [api, guest, force, setOutcome]);

  return (
    <>
      {connected && <p className="text-xs text-muted">{t('machine.console.enter')}</p>}
      <div
        ref={host}
        aria-label={t('machine.console.text')}
        className="h-[70dvh] min-h-64 overflow-hidden rounded border border-line bg-raised p-1 font-mono"
      />
    </>
  );
}

interface SpiceConnection {
  stop(): void;
  inputs?: { state: string; send_msg(message: unknown): void };
  ws?: WebSocket;
}

/** Ctrl+Alt+Del, which the browser keeps for itself, sent as the three keys' scan codes. */
async function ctrlAltDel(connection: SpiceConnection) {
  const [messages, { Constants }, { KeyNames }] = await Promise.all([
    import('@spice-project/spice-html5/src/spicemsg.js'),
    import('@spice-project/spice-html5/src/enums.js'),
    import('@spice-project/spice-html5/src/atKeynames.js'),
  ]);
  const inputs = connection.inputs;
  if (inputs?.state !== 'ready') return;
  const codes = [KeyNames.KEY_LCtrl, KeyNames.KEY_Alt, KeyNames.KEY_KP_Decimal];
  const send = (type: number, key: { code: number }) => {
    const message = new messages.SpiceMiniData();
    message.build_msg(type, key);
    inputs.send_msg(message);
  };
  for (const code of codes) {
    const key = new messages.SpiceMsgcKeyDown();
    key.code = code;
    send(Constants.SPICE_MSGC_INPUTS_KEY_DOWN, key);
  }
  for (const code of [...codes].reverse()) {
    const key = new messages.SpiceMsgcKeyUp();
    key.code = 0x80 | code;
    send(Constants.SPICE_MSGC_INPUTS_KEY_UP, key);
  }
}

function Screen({
  guest,
  force,
  setOutcome,
}: {
  guest: string;
  force: boolean;
  setOutcome: (outcome: Outcome) => void;
}) {
  const { t } = useI18n();
  const api = useMachineApi();
  const screen = useId();
  const connection = useRef<SpiceConnection | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let gone = false;
    let refusal: Error | undefined;
    Promise.all([ticket(api, guest, 'vga', force), import('@spice-project/spice-html5')])
      .then(([opened, spice]) => {
        if (gone) return;
        const made: SpiceConnection = new spice.SpiceMainConn({
          uri: socketUrl(api, opened.path),
          password: '',
          screen_id: screen,
          onsuccess: () => setConnected(true),
          onagent: (agent) => spice.resize_helper(agent),
          onerror: (error: Error) => {
            setConnected(false);
            // The refusal's own close listener runs after the client's, which reports first.
            setTimeout(() => {
              if (gone) return;
              connection.current?.stop();
              connection.current = null;
              setOutcome({ kind: 'ended', error: refusal ?? error });
            });
          },
        });
        // The main channel's close carries the agent's reason when the console could not open.
        made.ws?.addEventListener('close', (event) => {
          if (event.code === REFUSED) refusal = new Error(event.reason || String(event.code));
        });
        connection.current = made;
      })
      .catch((error) => {
        if (!gone) failed(error, setOutcome);
      });
    return () => {
      gone = true;
      connection.current?.stop();
      connection.current = null;
    };
  }, [api, guest, force, screen, setOutcome]);

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={button}
          disabled={!connected}
          onClick={() => connection.current && void ctrlAltDel(connection.current)}
        >
          {t('machine.console.ctrlAltDel')}
        </button>
      </div>
      <div
        id={screen}
        aria-label={t('machine.console.screen')}
        className="min-h-64 overflow-auto rounded border border-line bg-panel"
      />
    </>
  );
}
