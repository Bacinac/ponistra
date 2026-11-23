import { useQueryClient } from '@tanstack/react-query';
import { Suspense, useEffect, useRef, useState } from 'react';
import { Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { lazily } from '../lazily';
import { codeText } from '../tree';
import { CONTAINERS, dockerError, logsPath, stackPath, streamed, type Verb } from './data';

const TerminalPanel = lazily(() => import('../Terminal'), 'TerminalPanel');

// What a log or an output keeps on the page; older lines leave at the top.
const KEPT = 400_000;
const TAIL = 500;

function Stream({ text, failure }: { text: string; failure: string | null }) {
  const end = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const element = end.current;
    if (element && element.scrollHeight - element.scrollTop - element.clientHeight < 80)
      element.scrollTop = element.scrollHeight;
  }, [text]);
  return (
    <div className="flex min-h-0 flex-col gap-2">
      <pre
        ref={end}
        tabIndex={0}
        className="h-[60dvh] overflow-auto rounded border border-line bg-raised p-2 font-mono text-xs whitespace-pre-wrap break-all"
      >
        {text}
      </pre>
      {failure && <p className="text-sm whitespace-pre-wrap text-danger">{failure}</p>}
    </div>
  );
}

function useStreamed(
  start: (heard: (text: string) => void, signal: AbortSignal) => Promise<void>,
  after?: () => void,
) {
  const { t } = useI18n();
  const [text, setText] = useState('');
  const [failure, setFailure] = useState<string | null>(null);
  const [running, setRunning] = useState(true);
  const begun = useRef(start);
  const ended = useRef(after);
  useEffect(() => {
    const aborted = new AbortController();
    begun
      .current((piece) => setText((was) => (was + piece).slice(-KEPT)), aborted.signal)
      .catch((error: Error) => {
        if (!aborted.signal.aborted) setFailure(dockerError(error, t));
      })
      .finally(() => {
        if (aborted.signal.aborted) return;
        setRunning(false);
        ended.current?.();
      });
    return () => aborted.abort();
  }, [t]);
  return { text, failure, running };
}

/** A container's log as it is written, its last lines first. */
export function LogsDialog({
  location,
  container,
  name,
  onClose,
}: {
  location: string;
  container: string;
  name: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { text, failure } = useStreamed((heard, signal) =>
    streamed(logsPath(location, container, TAIL), heard, signal),
  );
  return (
    <Modal heading={t('docker.logsOf').replace('{name}', name)} wide onClose={onClose}>
      <Stream text={text} failure={failure} />
    </Modal>
  );
}

/** compose running one verb in the stack's folder, what it writes as it goes, and how it ended. */
export function OutputDialog({
  location,
  path,
  verb,
  onClose,
}: {
  location: string;
  path: string;
  verb: Verb;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<number | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const { text, failure, running } = useStreamed(
    (heard, signal) => {
      let left = '';
      return streamed(
        stackPath(location, path),
        (piece) => {
          const lines = (left + piece).split('\n');
          left = lines.pop() ?? '';
          const shown: string[] = [];
          for (const line of lines) {
            if (!line) continue;
            const said = JSON.parse(line) as { line?: string; status?: number; error?: string };
            if (said.line !== undefined) shown.push(said.line);
            if (said.error) setRefused(said.error);
            if (said.status !== undefined) setStatus(said.status);
          }
          if (shown.length) heard(shown.join('\n') + '\n');
        },
        signal,
        { verb },
      );
    },
    () => queryClient.invalidateQueries({ queryKey: [CONTAINERS] }),
  );
  return (
    <Modal heading={t(`docker.verb.${verb}`)} wide onClose={onClose}>
      <Stream text={text} failure={failure ?? (refused && codeText(refused, t))} />
      <p role="status" className="mt-2 text-sm text-muted">
        {running
          ? t('docker.running')
          : status === 0
            ? t('docker.done')
            : status !== null && t('docker.failedWith').replace('{status}', String(status))}
      </p>
    </Modal>
  );
}

/** A shell in a running container, over the terminal the workspace's projects have. */
export function ShellDialog({
  location,
  container,
  name,
  onClose,
}: {
  location: string;
  container: string;
  name: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <Modal heading={t('docker.shellIn').replace('{name}', name)} wide onClose={onClose}>
      <Suspense>
        <TerminalPanel
          path="/api/containers/shell"
          opensWith={{ host: location, container }}
          name={name}
          onClose={onClose}
        />
      </Suspense>
    </Modal>
  );
}
