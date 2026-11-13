import {
  Baseline,
  Bold,
  ImagePlus,
  Italic,
  Link,
  List,
  ListOrdered,
  Minus,
  RemoveFormatting,
  Strikethrough,
  Underline,
  type LucideIcon,
} from 'lucide-react';
import { baseKeymap, toggleMark } from 'prosemirror-commands';
import { history, redo, undo } from 'prosemirror-history';
import { inputRules, wrappingInputRule } from 'prosemirror-inputrules';
import { keymap } from 'prosemirror-keymap';
import type { MarkType, Node, NodeType } from 'prosemirror-model';
import { liftListItem, sinkListItem, splitListItem, wrapInList } from 'prosemirror-schema-list';
import { EditorState, type Command } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import 'prosemirror-view/style/prosemirror.css';
import { useEffect, useRef, useState, type FormEvent, type RefObject } from 'react';
import { upload } from './api';
import { reachable, useReachable } from './live';
import { queueing } from './offline';
import { Cancel, Modal } from './dialogs';
import { TEXT_COLORS } from './editor/colors';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import {
  mailHtml,
  mailSchema,
  MAIL_FONT,
  MAIL_FONTS,
  MAIL_IMAGES,
  MAIL_SIZE,
  MAIL_SIZES,
  MAIL_SPACING,
  MAIL_SPACINGS,
} from './mailText';
import { Menu, MenuItem } from './menu';
import { field, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';
import { useFilePicker } from './upload';

const { strong, em, underline, strike, font, size, color, link } = mailSchema.marks;
const { paragraph, bullet_list, ordered_list, list_item, image, hard_break, horizontal_rule } =
  mailSchema.nodes;

function marked(state: EditorState, type: MarkType): boolean {
  const { empty, $from, from, to } = state.selection;
  if (empty) return type.isInSet(state.storedMarks ?? $from.marks()) !== undefined;
  return state.doc.rangeHasMark(from, to, type);
}

function valueAt(state: EditorState, type: MarkType, attribute: string): unknown {
  const { $from } = state.selection;
  return type.isInSet(state.storedMarks ?? $from.marks())?.attrs[attribute] ?? null;
}

const ruled: Command = (state, dispatch) => {
  dispatch?.(state.tr.replaceSelectionWith(horizontal_rule.create()).scrollIntoView());
  return true;
};

/** Puts the mark on what is chosen, or on what is typed next; without attributes, takes it off. */
function styled(type: MarkType, attrs: Record<string, unknown> | null): Command {
  return (state, dispatch) => {
    const { empty, from, to } = state.selection;
    if (dispatch) {
      if (empty) {
        dispatch(
          attrs ? state.tr.addStoredMark(type.create(attrs)) : state.tr.removeStoredMark(type),
        );
      } else {
        const tr = state.tr.removeMark(from, to, type);
        dispatch(attrs ? tr.addMark(from, to, type.create(attrs)) : tr);
      }
    }
    return true;
  };
}

function spacingAt(state: EditorState): number {
  return state.selection.$from.parent.attrs.spacing ?? MAIL_SPACING;
}

function spaced(spacing: number): Command {
  return (state, dispatch) => {
    const { from, to } = state.selection;
    const tr = state.tr;
    state.doc.nodesBetween(from, to, (node, pos) => {
      if (node.type !== paragraph) return true;
      tr.setNodeAttribute(pos, 'spacing', spacing === MAIL_SPACING ? null : spacing);
      return false;
    });
    dispatch?.(tr);
    return true;
  };
}

function inList(state: EditorState, type: NodeType): boolean {
  const { $from } = state.selection;
  for (let depth = $from.depth; depth > 0; depth--) {
    if ($from.node(depth).type === type) return true;
  }
  return false;
}

function listed(type: NodeType): Command {
  return (state, dispatch) =>
    inList(state, type)
      ? liftListItem(list_item)(state, dispatch)
      : wrapInList(type)(state, dispatch);
}

const clear: Command = (state, dispatch) => {
  const { from, to, empty } = state.selection;
  if (dispatch) dispatch(empty ? state.tr.setStoredMarks([]) : state.tr.removeMark(from, to));
  return true;
};

/** The link under the cursor: its words' extent and where it leads. */
function linkAt(state: EditorState): { from: number; to: number; href: string } | null {
  const { $from } = state.selection;
  const found = link.isInSet($from.marks()) ?? link.isInSet($from.nodeAfter?.marks ?? []);
  if (!found) return null;
  const start = $from.start();
  const runs: [number, number][] = [];
  $from.parent.forEach((child, offset) => {
    if (!found.isInSet(child.marks)) return;
    const last = runs.at(-1);
    if (last && last[1] === start + offset) last[1] += child.nodeSize;
    else runs.push([start + offset, start + offset + child.nodeSize]);
  });
  const run = runs.find(([from, to]) => from <= $from.pos && $from.pos <= to);
  return run ? { from: run[0], to: run[1], href: found.attrs.href } : null;
}

function LinkDialog({ view, onClose }: { view: EditorView; onClose: () => void }) {
  const { t } = useI18n();
  const [initial] = useState(() => {
    const found = linkAt(view.state);
    const { from, to } = found ?? view.state.selection;
    return { from, to, text: view.state.doc.textBetween(from, to), href: found?.href ?? '' };
  });
  const [text, setText] = useState(initial.text);
  const [href, setHref] = useState(initial.href);
  const [invalid, setInvalid] = useState(false);

  function submit(event: FormEvent) {
    event.preventDefault();
    const address = /^[^\s@]+@[^\s@]+$/.test(href.trim()) ? `mailto:${href.trim()}` : href.trim();
    if (!/^(https?:\/\/|mailto:|tel:)\S+$/i.test(address)) {
      setInvalid(true);
      return;
    }
    const mark = link.create({ href: address });
    const words = text || href;
    const { state } = view;
    view.dispatch(
      state.tr
        .replaceWith(initial.from, initial.to, mailSchema.text(words, [mark]))
        .removeStoredMark(link),
    );
    onClose();
  }

  return (
    <Modal heading={t('command.link')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('link.text')}
          <input value={text} onChange={(event) => setText(event.target.value)} className={field} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('link.href')}
          <input
            autoFocus
            required
            value={href}
            aria-invalid={invalid}
            onChange={(event) => {
              setHref(event.target.value);
              setInvalid(false);
            }}
            placeholder="https://"
            className={field}
          />
        </label>
        {invalid && <p className="text-sm text-danger">{t('mail.linkInvalid')}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

const tool = 'h-7 rounded border border-line bg-transparent px-1 text-sm text-ink hover:bg-hover';

function Tool({
  icon: Icon,
  name,
  active,
  disabled,
  onRun,
}: {
  icon: LucideIcon;
  name: string;
  active?: boolean;
  disabled?: boolean;
  onRun: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={name}
      title={name}
      aria-pressed={active}
      disabled={disabled}
      onMouseDown={(event) => event.preventDefault()}
      onClick={onRun}
      className={`${iconButton} aria-pressed:bg-selected aria-pressed:text-accent`}
    >
      <Icon size={16} aria-hidden />
    </button>
  );
}

/** What the user writes mail with: text formatted as mail carries it, lists, links and images,
    on the light paper mail is written for. */
export function MailEditor({
  label,
  initial,
  onChange,
  viewRef,
  autoFocus,
  rows = 14,
}: {
  label: string;
  initial: Node;
  /** Told the HTML after each change. */
  onChange: (html: string) => void;
  viewRef?: RefObject<EditorView | null>;
  autoFocus?: boolean;
  rows?: number;
}) {
  const { t, formatNumber } = useI18n();
  const mount = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const [state, setState] = useState<EditorState | null>(null);
  const [linking, setLinking] = useState(false);
  const [failure, setFailure] = useState<Error | 'unsupported' | null>(null);
  const changed = useRef(onChange);
  changed.current = onChange;
  const [start] = useState(initial);
  const offline = queueing(useReachable());

  async function insertImages(files: File[]) {
    const editor = view.current;
    if (!editor || queueing(reachable())) return;
    const shown = files.filter((file) => MAIL_IMAGES.includes(file.type));
    if (shown.length < files.length) setFailure('unsupported');
    try {
      for (const file of shown) {
        const stored = await upload(file);
        editor.dispatch(
          editor.state.tr.replaceSelectionWith(
            image.create({ blob: stored.sha256, alt: file.name }),
          ),
        );
      }
    } catch (error) {
      setFailure(error as Error);
    }
    editor.focus();
  }
  const adding = useRef(insertImages);
  adding.current = insertImages;
  const picker = useFilePicker((files) => void insertImages(files), {
    accept: MAIL_IMAGES.join(','),
  });

  useEffect(() => {
    const opened = () => setLinking(true);
    const editor = new EditorView(mount.current, {
      state: EditorState.create({
        doc: start,
        plugins: [
          history(),
          inputRules({
            rules: [
              wrappingInputRule(/^\s*([-*])\s$/, bullet_list),
              wrappingInputRule(/^(\d+)\.\s$/, ordered_list),
            ],
          }),
          keymap({
            'Mod-z': undo,
            'Shift-Mod-z': redo,
            'Mod-y': redo,
            'Mod-b': toggleMark(strong),
            'Mod-i': toggleMark(em),
            'Mod-u': toggleMark(underline),
            'Shift-Mod-x': toggleMark(strike),
            'Shift-Mod-8': listed(bullet_list),
            'Shift-Mod-7': listed(ordered_list),
            'Mod-k': () => {
              opened();
              return true;
            },
            'Shift-Enter': (state, dispatch) => {
              dispatch?.(state.tr.replaceSelectionWith(hard_break.create()).scrollIntoView());
              return true;
            },
            Enter: splitListItem(list_item),
            Tab: sinkListItem(list_item),
            'Shift-Tab': liftListItem(list_item),
          }),
          keymap(baseKeymap),
        ],
      }),
      attributes: {
        role: 'textbox',
        'aria-multiline': 'true',
        'aria-label': label,
        class: 'mail-text min-h-full px-3 py-2 outline-none',
      },
      handlePaste: (_, event) => {
        const files = [...(event.clipboardData?.files ?? [])];
        if (!files.length) return false;
        void adding.current(files);
        return true;
      },
      handleDrop: (_, event) => {
        const files = [...((event as DragEvent).dataTransfer?.files ?? [])];
        if (!files.length) return false;
        void adding.current(files);
        return true;
      },
      dispatchTransaction(tr) {
        const next = editor.state.apply(tr);
        editor.updateState(next);
        setState(next);
        if (tr.docChanged) changed.current(mailHtml(next.doc));
      },
    });
    view.current = editor;
    if (viewRef) viewRef.current = editor;
    setState(editor.state);
    if (autoFocus) editor.focus();
    return () => {
      editor.destroy();
      view.current = null;
      if (viewRef) viewRef.current = null;
    };
  }, [start, label, viewRef, autoFocus]);

  function run(command: Command) {
    const editor = view.current;
    if (!editor) return;
    command(editor.state, editor.dispatch);
    editor.focus();
  }

  const painted = state ? valueAt(state, color, 'name') : null;
  const face = (state && valueAt(state, font, 'name')) ?? MAIL_FONT;
  const points = (state && valueAt(state, size, 'points')) ?? MAIL_SIZE;
  return (
    <div className="flex min-h-0 flex-col overflow-hidden rounded-lg border border-line focus-within:border-focus">
      <div
        role="toolbar"
        aria-label={t('mail.formatting')}
        className="flex flex-wrap items-center gap-0.5 border-b border-line px-1 py-0.5"
      >
        <select
          aria-label={t('mail.font')}
          title={t('mail.font')}
          value={String(face)}
          onChange={(event) => {
            const name = event.target.value;
            run(styled(font, name === MAIL_FONT ? null : { name }));
          }}
          className={tool}
        >
          {MAIL_FONTS.map(({ name, stack }) => (
            <option key={name} value={name} style={{ fontFamily: stack }}>
              {name}
            </option>
          ))}
        </select>
        <select
          aria-label={t('mail.size')}
          title={t('mail.size')}
          value={String(points)}
          onChange={(event) => {
            const chosen = Number(event.target.value);
            run(styled(size, chosen === MAIL_SIZE ? null : { points: chosen }));
          }}
          className={`${tool} w-16`}
        >
          {MAIL_SIZES.map((each) => (
            <option key={each} value={each}>
              {formatNumber(each)}
            </option>
          ))}
        </select>
        <span aria-hidden className="mx-1 h-5 w-px bg-line" />
        <Tool
          icon={Bold}
          name={t('command.bold')}
          onRun={() => run(toggleMark(strong))}
          active={!!state && marked(state, strong)}
        />
        <Tool
          icon={Italic}
          name={t('command.italic')}
          onRun={() => run(toggleMark(em))}
          active={!!state && marked(state, em)}
        />
        <Tool
          icon={Underline}
          name={t('command.underline')}
          onRun={() => run(toggleMark(underline))}
          active={!!state && marked(state, underline)}
        />
        <Tool
          icon={Strikethrough}
          name={t('command.strike')}
          onRun={() => run(toggleMark(strike))}
          active={!!state && marked(state, strike)}
        />
        <Menu
          align="start"
          onCloseFocus={() => view.current?.focus()}
          trigger={
            <button
              type="button"
              aria-label={t('command.color')}
              title={t('command.color')}
              onMouseDown={(event) => event.preventDefault()}
              className={iconButton}
            >
              <Baseline size={16} aria-hidden />
            </button>
          }
        >
          <MenuItem
            icon={Baseline}
            label={t('color.auto')}
            checked={painted === null}
            onSelect={() => run(styled(color, null))}
          />
          {Object.entries(TEXT_COLORS).map(([name, swatch]) => (
            <MenuItem
              key={name}
              icon={Baseline}
              swatch={swatch.light}
              label={t(`color.${name}` as MessageKey)}
              checked={painted === name}
              onSelect={() => run(styled(color, { name }))}
            />
          ))}
        </Menu>
        <select
          aria-label={t('mail.spacing')}
          title={t('mail.spacing')}
          value={state ? String(spacingAt(state)) : String(MAIL_SPACING)}
          onChange={(event) => run(spaced(Number(event.target.value)))}
          className={`${tool} w-16`}
        >
          {MAIL_SPACINGS.map((each) => (
            <option key={each} value={each}>
              {formatNumber(each)}
            </option>
          ))}
        </select>
        <span aria-hidden className="mx-1 h-5 w-px bg-line" />
        <Tool
          icon={List}
          name={t('command.bulletList')}
          onRun={() => run(listed(bullet_list))}
          active={!!state && inList(state, bullet_list)}
        />
        <Tool
          icon={ListOrdered}
          name={t('command.numberList')}
          onRun={() => run(listed(ordered_list))}
          active={!!state && inList(state, ordered_list)}
        />
        <span aria-hidden className="mx-1 h-5 w-px bg-line" />
        <Tool
          icon={Link}
          name={t('command.link')}
          onRun={() => setLinking(true)}
          active={!!state && linkAt(state) !== null}
        />
        {picker.element}
        <Tool icon={ImagePlus} name={t('command.image')} disabled={offline} onRun={picker.open} />
        <Tool icon={Minus} name={t('command.horizontalRule')} onRun={() => run(ruled)} />
        <Tool
          icon={RemoveFormatting}
          name={t('command.clearFormatting')}
          onRun={() => run(clear)}
        />
      </div>
      <div
        ref={mount}
        style={{ minHeight: `${rows * 1.5}rem` }}
        className="min-h-0 flex-1 resize-y overflow-y-auto bg-raised text-ink scheme-light"
      />
      {failure !== null && (
        <p className="px-3 py-1 text-sm text-danger">
          {failure === 'unsupported' ? t('mail.imageUnsupported') : errorMessage(failure, t)}
        </p>
      )}
      {linking && view.current && (
        <LinkDialog
          view={view.current}
          onClose={() => {
            setLinking(false);
            view.current?.focus();
          }}
        />
      )}
    </div>
  );
}
