import { useQuery, useQueryClient } from '@tanstack/react-query';
import { LoaderCircle, MessageSquarePlus, SendHorizontal, Square, Undo2 } from 'lucide-react';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Panel } from '../frame';
import { useI18n } from '../i18n';
import { button, field, iconButton } from '../styles';
import { codeText, errorMessage } from '../tree';
import { conversationOf, useAgent, type Turn } from './agent';
import { stopRun, undoRun, UNDER_WAY } from './runs';

const UNDOABLE: ReadonlySet<Turn['state']> = new Set(['done', 'stopped', 'interrupted']);
const WATCH_EVERY = 2000;

/** The conversation with the agent beside the document, over the tab shown: each turn a run the
 * user stops or takes back, a turn that asks how a request is meant offering its answers. */
export function AgentPanel({ tab, onClose }: { tab: string | null; onClose: () => void }) {
  const { t } = useI18n();
  const agent = useAgent();
  const queryClient = useQueryClient();
  const [thread, setThread] = useState<string | null>(null);
  const [request, setRequest] = useState('');
  const [failure, setFailure] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const found = useQuery({
    queryKey: ['agent', tab, thread],
    queryFn: () => conversationOf(tab!, thread),
    enabled: tab !== null,
    refetchInterval: (query) =>
      query.state.data?.turns.some((turn) => UNDER_WAY.has(turn.state)) ? WATCH_EVERY : false,
  });
  const turns = found.data?.turns ?? [];
  const busy = turns.some((turn) => UNDER_WAY.has(turn.state));
  const last = turns.at(-1);

  useEffect(() => {
    if (thread === null && found.data?.thread) setThread(found.data.thread);
  }, [thread, found.data?.thread]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' });
  }, [turns.length, last?.state]);

  function refresh() {
    const key = ['agent', tab];
    // A thread's first read still in flight was asked before the run existed, and a refetch of a
    // query without data joins it rather than cancelling it.
    void queryClient
      .cancelQueries({ queryKey: key })
      .then(() => queryClient.invalidateQueries({ queryKey: key }));
  }

  function send(text: string) {
    const asked = text.trim();
    const ask = agent?.asker.current;
    if (!asked || !ask || busy) return;
    const into = thread ?? crypto.randomUUID();
    setThread(into);
    setRequest('');
    ask(asked, into, refresh);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send(request);
  }

  function act(work: Promise<unknown>) {
    work.then(refresh, (error: Error) => setFailure(errorMessage(error, t)));
  }

  function fresh() {
    setThread(crypto.randomUUID());
    setFailure(null);
  }

  return (
    <Panel title={t('agent.title')} onClose={onClose}>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={fresh}
          disabled={busy || !turns.length}
          className={`${button} flex items-center gap-2`}
        >
          <MessageSquarePlus size={16} aria-hidden />
          {t('agent.new')}
        </button>
      </div>
      <ol className="flex flex-col gap-3">
        {turns.map((turn) => (
          <li key={turn.id} className="flex flex-col gap-2">
            <p className="self-end rounded-lg bg-selected px-3 py-2 text-sm whitespace-pre-wrap">
              {turn.request}
            </p>
            <TurnOf
              turn={turn}
              last={turn === last}
              onChoose={send}
              onStop={() => act(stopRun(turn.id))}
              onUndo={() => act(undoRun(turn.id))}
            />
          </li>
        ))}
      </ol>
      {failure && <p className="text-sm text-danger">{failure}</p>}
      <div ref={end} />
      <form onSubmit={submit} className="sticky bottom-0 mt-auto flex items-end gap-2 bg-surface">
        <label className="sr-only" htmlFor="agent-request">
          {t('agent.request')}
        </label>
        <textarea
          id="agent-request"
          rows={2}
          maxLength={4000}
          value={request}
          onChange={(event) => setRequest(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) submit(event);
          }}
          className={`${field} min-h-16 flex-1 resize-none`}
        />
        <button
          type="submit"
          aria-label={t('agent.send')}
          disabled={!request.trim() || busy || !agent?.asker.current}
          className={iconButton}
        >
          <SendHorizontal size={18} />
        </button>
      </form>
    </Panel>
  );
}

function TurnOf({
  turn,
  last,
  onChoose,
  onStop,
  onUndo,
}: {
  turn: Turn;
  last: boolean;
  onChoose: (answer: string) => void;
  onStop: () => void;
  onUndo: () => void;
}) {
  const { t } = useI18n();
  if (UNDER_WAY.has(turn.state)) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted">
        <LoaderCircle aria-hidden className="size-4 shrink-0 animate-spin" />
        <span className="flex-1">{t('run.writing')}</span>
        {turn.state === 'running' && (
          <button type="button" onClick={onStop} className={`${button} flex items-center gap-2`}>
            <Square size={14} aria-hidden />
            {t('run.stop')}
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2 text-sm">
      {turn.state === 'failed' && <p className="text-danger">{codeText(turn.error, t)}</p>}
      {turn.reply && <p className="whitespace-pre-wrap">{turn.reply}</p>}
      {last && turn.state === 'done' && turn.offers.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {turn.offers.map((offer) => (
            <button key={offer} type="button" onClick={() => onChoose(offer)} className={button}>
              {offer}
            </button>
          ))}
        </div>
      )}
      {turn.state === 'undone' && <p className="text-muted">{t('agent.undone')}</p>}
      {turn.state === 'stopped' && <p className="text-muted">{t('run.stopped')}</p>}
      {turn.changed && UNDOABLE.has(turn.state) && (
        <button
          type="button"
          onClick={onUndo}
          className={`${button} flex items-center gap-2 self-start`}
        >
          <Undo2 size={14} aria-hidden />
          {t('agent.undo')}
        </button>
      )}
    </div>
  );
}
