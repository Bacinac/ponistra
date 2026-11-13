import { Lock, RotateCcw, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { postJson } from './api';
import {
  ActionButtons,
  ActionItems,
  ChoiceBar,
  ChoiceBox,
  useChoice,
  type RowAction,
} from './choice';
import { ContextMenuArea } from './menu';
import { ConfirmDialog } from './dialogs';
import { Frame, Loading } from './frame';
import { useI18n } from './i18n';
import { errorMessage, Failure, NodeIcon, useTrash, useTreeChange, type TreeNode } from './tree';

type Trashed = TreeNode & { role: string; kept: 'held' | 'retained' | null };

const purgeable = (node: Trashed) => node.role === 'own' && !node.kept;

export function TrashPage() {
  const { t, formatDate, formatNumber } = useI18n();
  const trash = useTrash();
  const items = trash.data?.items ?? [];
  const choice = useChoice(items.map((node) => node.id));
  const restore = useTreeChange((nodes: Trashed[]) =>
    postJson('/api/trash/restore', { nodes: nodes.map((node) => node.id) }),
  );
  const purge = useTreeChange((nodes: Trashed[]) =>
    postJson('/api/trash/purge', { nodes: nodes.map((node) => node.id) }),
  );
  const [doomed, setDoomed] = useState<Trashed[] | null>(null);
  const failure = restore.error ?? purge.error;
  const chosen = items.filter((node) => choice.has(node.id));
  const done = { onSuccess: () => choice.choose([]) };

  const actionsOf = (nodes: Trashed[]): RowAction[] => [
    {
      icon: RotateCcw,
      label: t('trash.restore'),
      disabled: restore.isPending,
      onSelect: () => restore.mutate(nodes, done),
    },
    {
      icon: Trash2,
      label: t('trash.purge'),
      disabled: purge.isPending || !nodes.every(purgeable),
      onSelect: () => setDoomed(nodes),
    },
  ];

  return (
    <Frame title={t('trash.title')}>
      {trash.isPending ? (
        <Loading />
      ) : trash.isError ? (
        <Failure error={trash.error} />
      ) : (
        <section
          className="flex w-full max-w-4xl flex-col gap-4"
          onKeyDown={(event) =>
            choice.onKeyDown(event, () => {
              if (chosen.every(purgeable)) setDoomed(chosen);
            })
          }
        >
          {items.length === 0 ? (
            <p className="text-muted">{t('trash.empty')}</p>
          ) : (
            <div className="flex flex-col">
              {choice.many > 0 && (
                <ChoiceBar all={choice.all}>
                  <ActionButtons actions={actionsOf(chosen)} />
                </ChoiceBar>
              )}
              <ul aria-label={t('trash.title')} className="flex flex-col">
                {items.map((node) => {
                  const picked = choice.has(node.id);
                  return (
                    <ContextMenuArea
                      key={node.id}
                      items={<ActionItems actions={actionsOf(picked ? chosen : [node])} />}
                    >
                      <li
                        className={`flex items-center gap-3 border-b border-line px-3 py-1.5 select-none [-webkit-touch-callout:none] ${picked ? 'bg-selected' : 'hover:bg-hover'}`}
                      >
                        {choice.many > 0 && (
                          <ChoiceBox
                            checked={picked}
                            onToggle={(range) => choice.toggle(node.id, range)}
                          />
                        )}
                        <button
                          type="button"
                          {...choice.opener(node.id)}
                          className="flex min-w-0 flex-1 items-center gap-3 py-0.5 text-left"
                        >
                          <NodeIcon node={node} />
                          <span className="min-w-0 flex-1 truncate">{node.title}</span>
                          {node.kept && (
                            <Lock
                              size={14}
                              role="img"
                              aria-label={t(`retention.kept.${node.kept}`)}
                              className="shrink-0 text-muted"
                            >
                              <title>{t(`retention.kept.${node.kept}`)}</title>
                            </Lock>
                          )}
                          <span className="hidden text-sm text-muted sm:block">
                            {formatDate(node.trashed_at!)}
                          </span>
                        </button>
                        {choice.many === 0 && <ActionButtons actions={actionsOf([node])} />}
                      </li>
                    </ContextMenuArea>
                  );
                })}
              </ul>
            </div>
          )}
          {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
          {doomed && (
            <ConfirmDialog
              heading={t('trash.purgeTitle')}
              confirmLabel={t('trash.purge')}
              onConfirm={() => purge.mutate(doomed, done)}
              onClose={() => setDoomed(null)}
            >
              {doomed.length === 1 ? (
                <>
                  <strong>{doomed[0].title}</strong> {t('trash.purgeWarning')}
                </>
              ) : (
                `${t('explorer.selected')}: ${formatNumber(doomed.length)}. ${t('trash.purgeChosen')}`
              )}
            </ConfirmDialog>
          )}
        </section>
      )}
    </Frame>
  );
}
