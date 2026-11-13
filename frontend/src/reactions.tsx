import { SmilePlus } from 'lucide-react';
import { Suspense, useState, type ReactNode } from 'react';
import { Modal } from './dialogs';
import { Loading } from './frame';
import { useI18n } from './i18n';
import { lazily } from './lazily';
import { MenuEmojis, MenuItem } from './menu';

const EmojiGrid = lazily(() => import('./emojiPicker'), 'EmojiGrid');

/** An emoji given to a message, by whom, and whether the reader is among them. */
export interface Reaction {
  emoji: string;
  people: string[];
  mine: boolean;
}

export const QUICK = ['👍', '❤️', '😂', '😮', '😢', '🙏'] as const;

/** The emoji a menu offers to react with: the usual ones at a glance, the rest one step away. */
export function ReactionItems({
  onPick,
  onMore,
}: {
  onPick: (emoji: string) => void;
  onMore: () => void;
}) {
  const { t } = useI18n();
  return (
    <>
      <MenuEmojis emojis={QUICK} label={t('reactions.react')} onSelect={onPick} />
      <MenuItem icon={SmilePlus} label={t('reactions.more')} onSelect={onMore} />
    </>
  );
}

export function EmojiDialog({
  onPick,
  onClose,
}: {
  onPick: (emoji: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <Modal heading={t('reactions.choose')} onClose={onClose}>
      <Suspense fallback={<Loading />}>
        <EmojiGrid
          onPick={(emoji) => {
            onClose();
            onPick(emoji);
          }}
        />
      </Suspense>
    </Modal>
  );
}

/** The items of a menu that reacts with an emoji, and the dialog of the whole set they open. */
export function useReacting(onPick: (emoji: string) => void) {
  const [choosing, setChoosing] = useState(false);
  return {
    items: <ReactionItems onPick={onPick} onMore={() => setChoosing(true)} />,
    dialog: choosing ? <EmojiDialog onPick={onPick} onClose={() => setChoosing(false)} /> : null,
  } satisfies Record<string, ReactNode>;
}

/** The message's reactions, one chip per emoji with how many gave it; a chip gives the reader's
    own reaction, or takes it back where `onTake` can. */
export function Reactions({
  reactions,
  onGive,
  onTake,
  disabled,
}: {
  reactions: Reaction[];
  onGive: (emoji: string) => void;
  onTake?: (emoji: string) => void;
  disabled?: boolean;
}) {
  const { t, formatNumber } = useI18n();
  if (reactions.length === 0) return null;
  return (
    <ul aria-label={t('reactions.list')} className="flex flex-wrap gap-1">
      {reactions.map((reaction) => (
        <li key={reaction.emoji}>
          <button
            type="button"
            aria-pressed={reaction.mine}
            title={reaction.people.join(', ')}
            disabled={disabled || (reaction.mine && !onTake)}
            onClick={() => (reaction.mine ? onTake?.(reaction.emoji) : onGive(reaction.emoji))}
            className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-sm leading-5 ${reaction.mine ? 'border-accent bg-selected' : 'border-line bg-raised hover:bg-hover'} disabled:cursor-default`}
          >
            <span aria-hidden>{reaction.emoji}</span>
            <span className="sr-only">{`${reaction.emoji} ${reaction.people.join(', ')}`}</span>
            <span aria-hidden className="text-xs text-muted">
              {formatNumber(reaction.people.length)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
