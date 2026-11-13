import { Check, X } from 'lucide-react';
import type { RefObject } from 'react';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { iconButton } from '../styles';
import { runAction } from './actions';
import type { Context } from './command';
import { kindsOf, proposalsAt, type Kind } from './proposals';

function kindOf(kinds: Kind[]): MessageKey {
  if (kinds.includes('insertion') && kinds.includes('deletion')) return 'proposal.replacement';
  if (kinds.includes('insertion')) return 'proposal.insertion';
  if (kinds.includes('deletion')) return 'proposal.deletion';
  return 'proposal.formatting';
}

/** The proposals at the cursor, above its line: what each does, who proposed it and when, with
 * accepting and rejecting it where the tab can be edited. */
export function ProposalPopover({
  context,
  around,
  editable,
}: {
  context: Context;
  around: RefObject<HTMLElement | null>;
  editable: boolean;
}) {
  const { t, formatDate } = useI18n();
  const { view } = context;
  const found = proposalsAt(view.state);
  if (!found.length || !around.current) return null;
  const at = view.coordsAtPos(view.state.selection.from);
  const box = around.current.getBoundingClientRect();
  const keep = (event: { preventDefault: () => void }) => event.preventDefault();
  return (
    <div
      role="toolbar"
      aria-label={t('commandGroup.review')}
      onMouseDown={keep}
      style={{ left: Math.max(0, at.left - box.left), bottom: box.bottom - at.top + 4 }}
      className="absolute z-20 flex max-w-[min(28rem,100%)] flex-col gap-0.5 rounded border border-line bg-raised p-1 text-sm shadow-lg"
    >
      {found.map((proposal) => (
        <div key={proposal.id} className="flex min-w-0 items-center gap-2">
          <span className="min-w-0 truncate px-1">
            <span className="font-medium">{t(kindOf(kindsOf(view.state, proposal)))}</span>
            {' · '}
            {proposal.author}
            {proposal.date && <span className="text-muted"> · {formatDate(proposal.date)}</span>}
          </span>
          {editable && (
            <span className="ml-auto flex shrink-0 items-center">
              <button
                type="button"
                title={t('action.proposalAccept')}
                aria-label={t('action.proposalAccept')}
                onClick={() => runAction(context, 'proposal.accept', { ids: [proposal.id] })}
                className={iconButton}
              >
                <Check size={16} aria-hidden />
              </button>
              <button
                type="button"
                title={t('action.proposalReject')}
                aria-label={t('action.proposalReject')}
                onClick={() => runAction(context, 'proposal.reject', { ids: [proposal.id] })}
                className={iconButton}
              >
                <X size={16} aria-hidden />
              </button>
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
