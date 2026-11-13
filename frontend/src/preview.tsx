import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { lazy, Suspense, useState } from 'react';
import { Audience } from './access';
import { getJson } from './api';
import { BoardView } from './board';
import { formatSize } from './explorer';
import { Loading, Panel } from './frame';
import type { Column } from './split';
import { useI18n } from './i18n';
import { sourceHref } from './imported';
import { iconButton } from './styles';
import { Failure, kindLabel, kindOf, nodeKey, NodeIcon, type ListedNode } from './tree';
import { savedName } from './upload';

const TextView = lazy(() => import('./TextView'));

/** As much of a text file as a glance shows. */
const GLANCED_TEXT = 64 * 1024;

type Block =
  | { type: string; text: string; level: number | null }
  | { type: 'table'; rows: string[][] }
  | { type: 'image'; blob: string; alt: string };

interface Beginning {
  blocks: Block[];
  more: boolean;
}

/** The chosen items at a glance beside the folder: one shown as it reads, several counted. What
 * is kept in the browser lets no original out. */
export function PreviewPanel({
  chosen,
  kept,
  column,
  onClose,
}: {
  chosen: ListedNode[];
  kept: boolean;
  column?: Column;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const [single] = chosen;
  const sized = chosen.filter((node) => node.size !== null);
  const size = sized.reduce((sum, node) => sum + node.size!, 0);
  return (
    <Panel title={t('preview.title')} column={column} onClose={onClose}>
      {chosen.length === 0 ? (
        <p className="text-sm text-muted">{t('preview.none')}</p>
      ) : chosen.length > 1 ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-muted">{t('explorer.selected')}</dt>
          <dd>{formatNumber(chosen.length)}</dd>
          {sized.length > 0 && (
            <>
              <dt className="text-muted">{t('explorer.size')}</dt>
              <dd>{formatSize(size, formatNumber)}</dd>
            </>
          )}
        </dl>
      ) : (
        <Glance key={single.id} node={single} kept={kept} />
      )}
    </Panel>
  );
}

function Glance({ node, kept }: { node: ListedNode; kept: boolean }) {
  const { t, formatDate, formatNumber } = useI18n();
  const kind = kindOf(node);
  return (
    <>
      <h3 className="flex items-start gap-2 font-semibold break-words">
        <NodeIcon node={node} decorative />
        <span className="min-w-0">{node.title}</span>
      </h3>
      <Shown node={node} />
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-muted">{t('explorer.kind')}</dt>
        <dd>{kindLabel(kind, node.extension, t)}</dd>
        {node.size !== null && (
          <>
            <dt className="text-muted">{t('explorer.size')}</dt>
            <dd>{formatSize(node.size, formatNumber)}</dd>
          </>
        )}
        {node.origin && (
          <>
            <dt className="text-muted">{t('preview.source')}</dt>
            <dd className="flex items-center justify-between gap-2">
              <span>
                {kindLabel('other', node.origin.extension, t)} ·{' '}
                {formatSize(node.origin.size, formatNumber)}
              </span>
              {kept ? (
                <button
                  type="button"
                  disabled
                  title={t('confined.hint')}
                  aria-label={t('import.original')}
                  className={`${iconButton} -my-1.5 disabled:opacity-60`}
                >
                  <Download size={16} aria-hidden />
                </button>
              ) : (
                <a
                  href={sourceHref(node)}
                  title={t('import.original')}
                  aria-label={t('import.original')}
                  className={`${iconButton} -my-1.5`}
                >
                  <Download size={16} aria-hidden />
                </a>
              )}
            </dd>
          </>
        )}
        <dt className="text-muted">{t('explorer.updated')}</dt>
        <dd>{formatDate(node.updated_at)}</dd>
        {node.updated_by && (
          <>
            <dt className="text-muted">{t('explorer.updatedBy')}</dt>
            <dd>{node.updated_by.name}</dd>
          </>
        )}
        <dt className="text-muted">{t('access.title')}</dt>
        <dd>
          <Audience node={node} />
        </dd>
      </dl>
    </>
  );
}

export function Shown({ node }: { node: ListedNode }) {
  const file = `/api/nodes/${node.id}/file`;
  switch (kindOf(node)) {
    case 'document':
    case 'table':
    case 'slides':
      return <DocumentBeginning node={node} />;
    case 'file':
      return <Picture node={node} />;
    case 'image':
      return node.media_type === 'image/svg+xml' ? (
        <img src={file} alt={node.title} className={PICTURE} />
      ) : (
        <Picture node={node} />
      );
    case 'board':
      return (
        <BoardView
          node={node}
          className="block min-h-96 w-full flex-1 rounded border border-line"
        />
      );
    case 'text':
      return (
        <div className="h-96 shrink-0 overflow-hidden rounded border border-line">
          <Suspense fallback={<Loading />}>
            <TextView nodeId={node.id} name={savedName(node)} most={GLANCED_TEXT} />
          </Suspense>
        </div>
      );
    case 'video':
      return <video src={file} controls preload="metadata" className="w-full rounded" />;
    case 'audio':
      return <audio src={file} controls preload="metadata" className="w-full" />;
    case 'link':
      return (
        <>
          <a
            href={node.href ?? ''}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm break-all text-link hover:underline"
          >
            {node.href}
          </a>
          {node.description && <p className="text-sm text-muted">{node.description}</p>}
        </>
      );
    default:
      return null;
  }
}

const PICTURE = 'max-h-96 w-full shrink-0 rounded border border-line object-contain';

/** An image or a PDF's first page drawn small, which the server draws on the spot for a file
 * it has not come to yet. */
function Picture({ node }: { node: ListedNode }) {
  const [missing, setMissing] = useState(false);
  if (missing) return null;
  return (
    <img
      src={`/api/nodes/${node.id}/picture${node.picture ? `?v=${node.picture}` : ''}`}
      alt={node.title}
      onError={() => setMissing(true)}
      className={PICTURE}
    />
  );
}

function DocumentBeginning({ node }: { node: ListedNode }) {
  const { t } = useI18n();
  const beginning = useQuery({
    queryKey: [...nodeKey(node.id), 'beginning'],
    queryFn: () => getJson<Beginning>(`/api/nodes/${node.id}/beginning`),
  });
  if (beginning.isPending) return <Loading />;
  if (beginning.isError) return <Failure error={beginning.error} />;
  const { blocks, more } = beginning.data;
  if (blocks.length === 0) return <p className="text-sm text-muted">{t('preview.empty')}</p>;
  return (
    <div className="flex shrink-0 flex-col gap-2 overflow-hidden rounded border border-line p-3 text-sm">
      {blocks.map((block, index) =>
        'rows' in block ? (
          <table key={index} className="w-full table-fixed border-collapse text-xs">
            <tbody>
              {block.rows.map((row, at) => (
                <tr key={at}>
                  {row.map((cell, col) => (
                    <td key={col} className="truncate border border-line px-1 py-0.5">
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : 'blob' in block ? (
          <img
            key={index}
            src={`/api/images/${block.blob}`}
            alt={block.alt}
            className="max-h-40 max-w-full self-start object-contain"
          />
        ) : (
          <p key={index} className={written(block)}>
            {block.text}
          </p>
        ),
      )}
      {more && <p className="text-muted">…</p>}
    </div>
  );
}

function written(block: { type: string; level: number | null }): string {
  if (block.type === 'title') return 'text-lg font-semibold';
  if (block.type !== 'heading') return 'line-clamp-4';
  return block.level === 1 ? 'text-base font-semibold' : 'font-semibold';
}
