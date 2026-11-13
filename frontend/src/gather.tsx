import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { ApiError, getJson } from './api';
import { Cancel, Modal } from './dialogs';
import { RunBar } from './editor/RunBar';
import { startOnNodes, stopRun, undoRun, UNDER_WAY, type Run } from './editor/runs';
import { useI18n } from './i18n';
import { field, primaryButton } from './styles';
import {
  errorMessage,
  nodeHref,
  TREE,
  useOpen,
  useTreeChange,
  type ListedNode,
  type TreeNode,
} from './tree';

const ACTION = 'nodes.extract';
const TRANSLATE = 'file.translate';
const COLUMNS = 30;
const COLUMN = 100;
const CHECK_EVERY = 2000;

/** A run over documents and the document it writes into. */
export interface Gathering {
  run: Run;
  document: TreeNode;
}

/** Whether the installation's AI is on, which an action over documents needs. */
/** The run as the server has it, asked now and then while it is under way; once it ends, the
 * folders are listed again with the document it wrote. */
function useFollowed(run: Run | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ['run', run?.id],
    queryFn: async () => {
      const found = (await getJson<{ run: Run }>(`/api/runs/${run!.id}`)).run;
      if (!UNDER_WAY.has(found.state)) queryClient.invalidateQueries({ queryKey: TREE });
      return found;
    },
    enabled: run !== null,
    initialData: run ?? undefined,
    refetchInterval: ({ state }) =>
      state.data && UNDER_WAY.has(state.data.state) ? CHECK_EVERY : false,
  });
}

/** The run as it goes, stopped, taken back or its document opened from its bar, and why it
 * failed, or why stopping or taking it back did. */
export function useFollowedRun(started: Gathering | null, onClose: () => void, inline = false) {
  const opened = useOpen();
  const run = useFollowed(started?.run ?? null).data;
  const undo = useTreeChange(undoRun);
  const [stopping, setStopping] = useState<Error | null>(null);
  const under = run !== undefined && UNDER_WAY.has(run.state);
  const failed =
    run?.state === 'failed' ? new ApiError(`/api/runs/${run.id}`, 422, run.error) : null;
  const bar = run && started && (under || run.state === 'done' || run.state === 'stopped') && (
    <RunBar
      inline={inline}
      running={
        under
          ? [
              {
                run: run.id,
                action: run.action,
                user: null,
                model: run.model,
                through: run.items?.through,
                of: run.items?.of,
              },
            ]
          : []
      }
      done={under ? null : run}
      onStop={(id) => {
        setStopping(null);
        stopRun(id).catch(setStopping);
      }}
      onUndo={() => undo.mutate(run.id, { onSuccess: onClose })}
      onClose={onClose}
      onOpen={() => opened(nodeHref(started.document))}
    />
  );
  return {
    bar,
    failure: undo.error ?? stopping ?? failed,
    reset: () => {
      undo.reset();
      setStopping(null);
    },
  };
}

/** Asks the name of the document the data of the documents chosen goes into, and the columns
 * of its table, which Claude chooses where none are given. */
export function GatherDialog({
  nodes,
  name,
  onStarted,
  onClose,
}: {
  nodes: readonly ListedNode[];
  /** What the document is named after: the one node chosen, or the folder. */
  name: string | null;
  onStarted: (started: Gathering) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [title, setTitle] = useState(name ? `${name} – ${t('gather.name')}` : t('gather.name'));
  const [written, setWritten] = useState('');
  const start = useTreeChange((parameters: object) =>
    startOnNodes(
      ACTION,
      nodes.map((node) => node.id),
      parameters,
    ),
  );
  const columns = [
    ...new Set(
      written
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
    ),
  ];
  const invalid = columns.length > COLUMNS || columns.some((column) => column.length > COLUMN);
  const named = title.trim();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (invalid || !named) return;
    start.mutate(columns.length > 0 ? { title: named, columns } : { title: named }, {
      onSuccess: (started) => {
        onStarted(started);
        onClose();
      },
    });
  }

  return (
    <Modal heading={t('action.nodesExtract')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('tree.name')}
          <input
            required
            autoFocus
            maxLength={200}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onFocus={(event) => event.currentTarget.select()}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('gather.columns')}
          <textarea
            rows={4}
            value={written}
            onChange={(event) => setWritten(event.target.value)}
            aria-invalid={invalid}
            className={field}
          />
          <span className={invalid ? 'text-danger' : 'text-muted'}>
            {t(invalid ? 'gather.columnsInvalid' : 'gather.columnsNote')}
          </span>
        </label>
        <p className="text-sm text-muted">{t('gather.note')}</p>
        <p className="text-sm text-muted">{t('ai.consent.body')}</p>
        {start.isError && <p className="text-sm text-danger">{errorMessage(start.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="submit"
            disabled={invalid || !named || start.isPending}
            className={primaryButton}
          >
            {t('gather.run')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Asks before a PDF file goes to Claude to be translated into the interface's language, page by
 * page into a new document beside it. */
export function TranslateDialog({
  file,
  onStarted,
  onClose,
}: {
  file: TreeNode;
  onStarted: (started: Gathering) => void;
  onClose: () => void;
}) {
  const { t, language } = useI18n();
  const start = useTreeChange(() => startOnNodes(TRANSLATE, [file.id], { language }));

  function submit(event: FormEvent) {
    event.preventDefault();
    start.mutate(undefined, {
      onSuccess: (started) => {
        onStarted(started);
        onClose();
      },
    });
  }

  return (
    <Modal heading={t('translation.file')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <p className="text-sm text-muted">{t('ai.consent.body')}</p>
        {start.isError && <p className="text-sm text-danger">{errorMessage(start.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" autoFocus disabled={start.isPending} className={primaryButton}>
            {t('translation.translate')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
