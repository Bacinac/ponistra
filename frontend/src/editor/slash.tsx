import { Plugin, PluginKey, type EditorState } from 'prosemirror-state';
import type { EditorView } from 'prosemirror-view';
import type { RefObject } from 'react';
import { useI18n } from '../i18n';
import { shortcutLabel } from '../keys';
import type { Choice } from '../palette';

interface Slash {
  from: number;
  query: string;
  index: number;
}

type Meta = { open: number } | { index: number } | 'close';
type ChoicesFor = (view: EditorView, query: string) => Choice[];

export const slashKey = new PluginKey<Slash | null>('slash');

function close(view: EditorView): void {
  view.dispatch(view.state.tr.setMeta(slashKey, 'close'));
}

export function choose(view: EditorView, choice: Choice): void {
  const slash = slashKey.getState(view.state);
  if (!slash || choice.disabled) return;
  view.dispatch(
    view.state.tr.delete(slash.from, view.state.selection.head).setMeta(slashKey, 'close'),
  );
  choice.run();
}

/** "/" at the start of a line or after a space lists what Insert offers, filtered by what
 * follows it. */
export function slashMenu(choicesFor: ChoicesFor): Plugin {
  return new Plugin<Slash | null>({
    key: slashKey,
    choicesFor,
    state: {
      init: () => null,
      apply(tr, value, _old, state) {
        const meta: Meta | undefined = tr.getMeta(slashKey);
        if (meta === 'close') return null;
        if (meta && 'open' in meta) return { from: meta.open, query: '', index: 0 };
        if (!value) return null;
        const from = tr.mapping.map(value.from);
        const { empty, $head } = state.selection;
        if (!empty || $head.pos <= from || !state.doc.resolve(from).sameParent($head)) return null;
        if (state.doc.textBetween(from, from + 1) !== '/') return null;
        const query = state.doc.textBetween(from + 1, $head.pos);
        if (/\s/.test(query)) return null;
        if (meta && 'index' in meta) return { from, query, index: meta.index };
        return { from, query, index: query === value.query ? value.index : 0 };
      },
    },
    props: {
      handleTextInput(view, from, to, text) {
        if (text !== '/' || slashKey.getState(view.state)) return false;
        const $from = view.state.doc.resolve(from);
        if (!$from.parent.isTextblock) return false;
        const before = $from.parent.textBetween(
          Math.max(0, $from.parentOffset - 1),
          $from.parentOffset,
        );
        if (before && !/\s/.test(before)) return false;
        view.dispatch(view.state.tr.insertText(text, from, to).setMeta(slashKey, { open: from }));
        return true;
      },
      handleKeyDown(view, event) {
        const slash = slashKey.getState(view.state);
        if (!slash) return false;
        const list = choicesFor(view, slash.query);
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
          if (list.length) {
            const step = event.key === 'ArrowDown' ? 1 : list.length - 1;
            const index = (slash.index + step) % list.length;
            view.dispatch(view.state.tr.setMeta(slashKey, { index }));
          }
          return true;
        }
        if (event.key === 'Enter' || event.key === 'Tab') {
          const choice = list[slash.index];
          if (!choice) {
            close(view);
            return false;
          }
          choose(view, choice);
          return true;
        }
        if (event.key === 'Escape') {
          close(view);
          return true;
        }
        return false;
      },
      handleDOMEvents: {
        blur(view) {
          if (slashKey.getState(view.state)) close(view);
          return false;
        },
      },
    },
  });
}

export function SlashMenu({
  view,
  state,
  around,
}: {
  view: EditorView;
  state: EditorState;
  around: RefObject<HTMLElement | null>;
}) {
  const { t } = useI18n();
  const slash = slashKey.getState(state);
  if (!slash || !around.current) return null;
  const choicesFor: ChoicesFor = slashKey.get(state)!.spec.choicesFor;
  const list = choicesFor(view, slash.query);
  const at = view.coordsAtPos(slash.from);
  const box = around.current.getBoundingClientRect();
  return (
    <div
      onMouseDown={(event) => event.preventDefault()}
      style={{ left: at.left - box.left, top: at.bottom - box.top + 4 }}
      className="absolute z-30 flex w-64 flex-col rounded border border-line bg-raised p-1 text-ink shadow-lg"
    >
      {list.length === 0 ? (
        <p className="px-2 py-1.5 text-sm text-muted">
          {t('slash.none')} „{slash.query}”.
        </p>
      ) : (
        <ul role="listbox" aria-label={t('editor.insert')}>
          {list.map((choice, index) => (
            <li
              key={choice.id}
              role="option"
              aria-selected={index === slash.index}
              aria-disabled={choice.disabled}
              onClick={() => choose(view, choice)}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-hover aria-disabled:cursor-default aria-disabled:opacity-40 aria-selected:bg-selected"
            >
              <choice.icon size={16} aria-hidden className="text-muted" />
              <span className="grow">{choice.label}</span>
              {choice.keys && (
                <kbd className="font-sans text-xs text-muted">{shortcutLabel(choice.keys)}</kbd>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
