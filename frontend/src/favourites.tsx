import { Star, StarOff } from 'lucide-react';
import { useMemo } from 'react';
import { postJson } from './api';
import { useI18n } from './i18n';
import { MenuItem } from './menu';
import { errorMessage, useFavourites, useTreeChange } from './tree';

function useChange() {
  return useTreeChange(({ nodes, favourite }: { nodes: string[]; favourite: boolean }) =>
    postJson('/api/nodes/favourites', { nodes, favourite }),
  );
}

export function useFavouriteIds(): Set<string> {
  const { data } = useFavourites();
  return useMemo(() => new Set(data?.children.map((node) => node.id)), [data]);
}

/** Marking from a menu: the page holds it, as a menu closes before the answer and could not say
    that it failed. */
export function useFavouriteMarks() {
  return { ids: useFavouriteIds(), change: useChange() };
}

/** Adds the nodes to the user's favourites; removes them once all of them are. */
export function FavouriteItem({
  nodes,
  marks,
}: {
  nodes: { id: string }[];
  marks: ReturnType<typeof useFavouriteMarks>;
}) {
  const { t } = useI18n();
  const on = nodes.every((node) => marks.ids.has(node.id));
  return (
    <MenuItem
      icon={on ? StarOff : Star}
      label={t(on ? 'favourites.remove' : 'favourites.add')}
      disabled={marks.change.isPending}
      onSelect={() => marks.change.mutate({ nodes: nodes.map((node) => node.id), favourite: !on })}
    />
  );
}

export function FavouriteButton({
  id,
  size,
  className,
}: {
  id: string;
  size: number;
  className: string;
}) {
  const { t } = useI18n();
  const on = useFavouriteIds().has(id);
  const change = useChange();
  const label = t(on ? 'favourites.remove' : 'favourites.add');
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={label}
      title={change.error ? errorMessage(change.error, t) : label}
      disabled={change.isPending}
      onClick={() => change.mutate({ nodes: [id], favourite: !on })}
      className={className}
    >
      <Star
        size={size}
        aria-hidden
        className={change.error ? 'text-danger' : on ? 'fill-current text-accent' : ''}
      />
    </button>
  );
}
