import * as AlertDialog from '@radix-ui/react-alert-dialog';
import * as Dialog from '@radix-ui/react-dialog';
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react';
import { upload } from './api';
import { IMPORTED } from './importable';
import { IMAGE_ACCEPT, useFilePicker } from './upload';
import { useI18n } from './i18n';
import { runJob } from './jobs';
import { button, dangerButton, field, overlay, primaryButton } from './styles';
import {
  Breadcrumbs,
  COMPANY,
  covers,
  errorMessage,
  kindOf,
  LinkIcon,
  NodeIcon,
  SHARED,
  useCompany,
  useFolder,
  useMove,
  useShared,
  useTreeChange,
  type Role,
  type Root,
  type TreeNode,
  stepTitle,
} from './tree';

const place =
  'fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100dvh-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-lg border border-line bg-raised p-5 text-ink shadow-xl';
const panel = `${place} w-[min(28rem,calc(100vw-2rem))]`;
const widePanel = `${place} w-[min(52rem,calc(100vw-2rem))]`;

let settled: Element | null = null;
document.addEventListener('focusin', ({ target }) => {
  if (target instanceof Element && !target.closest('[role="menu"], [role="dialog"]')) {
    settled = target;
  }
});

// Radix returns focus only to a Dialog.Trigger, and these dialogs open without one. A dialog
// opened from a menu item goes back where focus was before the menu, as the item is gone.
export function useReturnFocus(): (event: Event) => void {
  const [openers] = useState(() => [document.activeElement, settled]);
  return (event) => {
    event.preventDefault();
    const back = openers.find((each) => each instanceof HTMLElement && each.isConnected);
    (back as HTMLElement | undefined)?.focus();
  };
}

export function Modal({
  heading,
  wide,
  onClose,
  children,
}: {
  heading: string;
  wide?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const returnFocus = useReturnFocus();
  return (
    <Dialog.Root open onOpenChange={(open) => open || onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={overlay} />
        <Dialog.Content
          className={wide ? widePanel : panel}
          aria-describedby={undefined}
          onCloseAutoFocus={returnFocus}
        >
          <Dialog.Title className="text-lg font-semibold">{heading}</Dialog.Title>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// A label around a select would take the chosen option into the control's name.
export function Labelled({
  label,
  children,
}: {
  label: string;
  children: (id: string) => ReactNode;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1 text-sm">
      <label htmlFor={id} className="text-muted">
        {label}
      </label>
      {children(id)}
    </div>
  );
}

export function Picker<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly (readonly [T, string])[];
  onChange: (value: T) => void;
}) {
  return (
    <Labelled label={label}>
      {(id) => (
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value as T)}
          className={field}
        >
          {options.map(([option, text]) => (
            <option key={option} value={option}>
              {text}
            </option>
          ))}
        </select>
      )}
    </Labelled>
  );
}

export function NumberField({
  label,
  value,
  min,
  max,
  step,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  const [text, setText] = useState(String(value));
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    setText(String(value));
  }
  return (
    <Labelled label={label}>
      {(id) => (
        <input
          id={id}
          type="number"
          inputMode="decimal"
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            const number = event.target.valueAsNumber;
            if (Number.isFinite(number) && number >= min && number <= max) {
              setShown(number);
              onChange(number);
            }
          }}
          className={field}
        />
      )}
    </Labelled>
  );
}

export function Cancel() {
  const { t } = useI18n();
  return (
    <Dialog.Close asChild>
      <button type="button" className={button}>
        {t('tree.cancel')}
      </button>
    </Dialog.Close>
  );
}

export function Close() {
  const { t } = useI18n();
  return (
    <Dialog.Close asChild>
      <button type="button" className={button}>
        {t('frame.close')}
      </button>
    </Dialog.Close>
  );
}

/** A copy of the document under the name the user gives it, beside it where they may add to its
 * folder and among their own documents where they may not. */
export function CopyDialog({
  node,
  onDone,
  onClose,
}: {
  node: TreeNode;
  onDone: (copy: TreeNode) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <NameDialog
      heading={t('copy.make')}
      submitLabel={t('tree.create')}
      initial={`${t('copy.of')} ${node.title}`.slice(0, 200)}
      onSubmit={(title) => runJob<TreeNode>('copy', { document: node.id, title }, title)}
      onDone={onDone}
      onClose={onClose}
    />
  );
}

export function NameDialog<R>({
  heading,
  submitLabel,
  initial = '',
  maxLength = 200,
  note,
  onSubmit,
  onDone,
  onClose,
}: {
  heading: string;
  submitLabel: string;
  initial?: string;
  maxLength?: number;
  /** What the user should know before the thing is made. */
  note?: string;
  onSubmit: (title: string) => Promise<R>;
  onDone: (result: R) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [title, setTitle] = useState(initial);
  const save = useTreeChange(onSubmit);

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(title, { onSuccess: onDone });
  }

  return (
    <Modal heading={heading} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('tree.name')}
          <input
            required
            maxLength={maxLength}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onFocus={(event) => event.currentTarget.select()}
            className={field}
          />
        </label>
        {note && <p className="text-sm text-muted">{note}</p>}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {submitLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** A link's page and name: a link left without a name is called by its page's title, until a
 * name is given. */
/** The icon given a link: an image uploaded, an icon named as Homepage names its icons, or none,
 * for its site's. */
export type LinkIconGiven = { blob: string } | string | null;

export function LinkDialog({
  heading,
  submitLabel,
  link,
  onSubmit,
  onClose,
}: {
  heading: string;
  submitLabel: string;
  /** The link edited, whose icon the dialog changes too. */
  link?: TreeNode;
  onSubmit: (given: { href: string; title?: string; icon?: LinkIconGiven }) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [href, setHref] = useState(link?.href ?? '');
  const [title, setTitle] = useState(link?.title ?? '');
  const [picked, setPicked] = useState<{ file: File; src: string } | null>(null);
  const [iconName, setIconName] = useState('');
  const [removed, setRemoved] = useState(false);
  const save = useTreeChange(
    async ({ picked, ...given }: Parameters<typeof onSubmit>[0] & { picked?: File }) =>
      onSubmit(picked ? { ...given, icon: { blob: (await upload(picked)).sha256 } } : given),
  );
  useEffect(
    () => () => {
      if (picked) URL.revokeObjectURL(picked.src);
    },
    [picked],
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    const named = title.trim();
    const renamed = link ? named !== link.title : named !== '';
    const icon = iconName.trim() ? { icon: iconName.trim() } : removed ? { icon: null } : {};
    save.mutate(
      { href, ...(renamed ? { title: named } : {}), ...icon, picked: picked?.file },
      { onSuccess: onClose },
    );
  }

  const picker = useFilePicker(
    ([file]) => {
      setPicked({ file, src: URL.createObjectURL(file) });
      setIconName('');
      setRemoved(false);
    },
    { accept: IMAGE_ACCEPT, multiple: false },
  );

  return (
    <Modal heading={heading} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('tree.address')}
          <input
            required
            type="text"
            inputMode="url"
            autoComplete="url"
            maxLength={2000}
            value={href}
            onChange={(event) => setHref(event.target.value)}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t('tree.name')}
          <input
            required={link !== undefined}
            maxLength={200}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className={field}
          />
        </label>
        {link && (
          <fieldset className="flex flex-col gap-2 text-sm">
            <legend className="mb-1">{t('links.icon')}</legend>
            <div className="flex items-center gap-2">
              <LinkIcon
                link={{
                  ...link,
                  title: title || link.title,
                  picture: removed ? null : link.picture,
                }}
                src={picked?.src}
              />
              {picker.element}
              <button type="button" onClick={picker.open} className={button}>
                {t('links.pickIcon')}
              </button>
              {(picked || (link.picture && !removed)) && (
                <button
                  type="button"
                  onClick={() => {
                    setPicked(null);
                    setIconName('');
                    setRemoved(true);
                  }}
                  className={button}
                >
                  {t('links.removeIcon')}
                </button>
              )}
            </div>
            <label className="flex flex-col gap-1">
              {t('links.iconName')}
              <input
                maxLength={2000}
                value={iconName}
                onChange={(event) => {
                  setIconName(event.target.value);
                  setPicked(null);
                }}
                className={field}
              />
            </label>
          </fieldset>
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending} className={primaryButton}>
            {submitLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}

const ROOTS = [
  ['mine', 'tree.root', null],
  ['company', 'tree.company', COMPANY],
  ['shared', 'tree.shared', SHARED],
] as const;

const TOPS: Record<string, Exclude<Root, 'mine'>> = { [COMPANY]: 'company', [SHARED]: 'shared' };

function useBrowsing(start: string | null) {
  const [target, setTarget] = useState(start);
  const top = target === null ? undefined : TOPS[target];
  const folderListing = useFolder(top ? null : target);
  const tops = { company: useCompany(), shared: useShared() };
  const listing = top ? tops[top] : folderListing;
  const place = top ? undefined : folderListing.data;
  return {
    target,
    go: setTarget,
    place,
    children: (listing.data?.children ?? []).filter((child) => !child.boards),
    loaded: listing.isSuccess,
    error: listing.error,
    root: top ?? place?.root ?? 'mine',
    company: !!tops.company.data?.children.length,
  };
}

/** The user's folders and those shared with them, walked one level at a time. */
function Browser({
  browsing,
  shown,
  empty,
  onPick,
}: {
  browsing: ReturnType<typeof useBrowsing>;
  shown: TreeNode[];
  empty: string;
  /** What choosing a listed item that is not a folder does. */
  onPick?: (node: TreeNode) => void;
}) {
  const { t } = useI18n();
  return (
    <>
      <div className="flex gap-1 text-sm">
        {ROOTS.filter(([root]) => root !== 'company' || browsing.company).map(
          ([root, label, top]) => (
            <button
              key={root}
              type="button"
              aria-pressed={root === browsing.root}
              onClick={() => browsing.go(top)}
              className="rounded px-2 py-1 text-muted aria-pressed:bg-selected aria-pressed:text-ink"
            >
              {t(label)}
            </button>
          ),
        )}
      </div>
      <div className="text-sm">
        <Breadcrumbs
          path={browsing.place?.path ?? []}
          root={browsing.root}
          onSelect={browsing.go}
        />
      </div>
      <ul className="max-h-64 divide-y divide-line overflow-y-auto rounded border border-line">
        {shown.map((node) => (
          <li key={node.id}>
            <button
              type="button"
              onClick={() => (node.kind === 'folder' ? browsing.go(node.id) : onPick?.(node))}
              className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-hover"
            >
              <NodeIcon node={node} decorative />
              <span className="truncate">{stepTitle(node, t)}</span>
            </button>
          </li>
        ))}
        {browsing.loaded && shown.length === 0 && (
          <li className="px-3 py-2 text-sm text-muted">{empty}</li>
        )}
      </ul>
    </>
  );
}

export function MoveDialog({
  nodes,
  onClose,
}: {
  nodes: (TreeNode & { role: Role })[];
  onClose: () => void;
}) {
  const { t } = useI18n();
  const origin = nodes[0].parent;
  const browsing = useBrowsing(origin);
  const from = useFolder(origin).data;
  const move = useMove();
  const moving = new Set(nodes.map((node) => node.id));
  const folders = browsing.children.filter(
    (child) => child.kind === 'folder' && !moving.has(child.id),
  );
  const place = browsing.place;
  const keeping = new Set(
    from?.confined ? from.path.filter((step) => step.confined).map((step) => step.id) : [],
  );
  const escapes =
    keeping.size > 0 &&
    nodes.some((node) => !node.confined) &&
    !place?.path.some((step) => keeping.has(step.id));
  const allowed =
    !!place &&
    !escapes &&
    covers(place.role, 'edit') &&
    (browsing.target !== null || nodes.every((node) => covers(node.role, 'own')));
  const failure = browsing.error ?? move.error;

  return (
    <Modal heading={t('tree.moveTitle')} onClose={onClose}>
      <p className="truncate text-sm text-muted">{nodes.map((node) => node.title).join(', ')}</p>
      <Browser browsing={browsing} shown={folders} empty={t('tree.noSubfolders')} />
      {escapes && <p className="text-sm text-muted">{t('confined.hint')}</p>}
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      <div className="flex justify-end gap-2">
        <Cancel />
        <button
          type="button"
          disabled={browsing.target === origin || !allowed || move.isPending}
          onClick={() =>
            move.mutate({ ids: [...moving], parent: browsing.target }, { onSuccess: onClose })
          }
          className={primaryButton}
        >
          {t('tree.moveHere')}
        </button>
      </div>
    </Modal>
  );
}

/** A folder the user may add to, chosen from those they can reach, starting at their own. */
export function FolderPickDialog({
  heading,
  confirmLabel,
  onPick,
  onClose,
}: {
  heading: string;
  confirmLabel: string;
  onPick: (folder: string | null) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const browsing = useBrowsing(null);
  const folders = browsing.children.filter((child) => child.kind === 'folder');
  const place = browsing.place;
  return (
    <Modal heading={heading} onClose={onClose}>
      <Browser browsing={browsing} shown={folders} empty={t('tree.noSubfolders')} />
      {browsing.error && <p className="text-sm text-danger">{errorMessage(browsing.error, t)}</p>}
      <div className="flex justify-end gap-2">
        <Cancel />
        <button
          type="button"
          disabled={!place || !covers(place.role, 'edit')}
          onClick={() => onPick(browsing.target)}
          className={primaryButton}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

/** The files of a word processor whose text the server reads, by their media types. */
export const WORD_FILES = new Set(
  Object.keys(IMPORTED).filter((type) => /^\.(docx?|docm|dotx|dotm|odt|rtf)$/.test(IMPORTED[type])),
);

/** A file chosen from the folders the user can reach, starting beside `near`: a PDF, an image, a
 * text, a document of text or a word processor's file, or whatever the user may hand to others.
 * `actions` go beside the dialog's cancel. */
export function FilePickDialog({
  heading,
  near,
  kind,
  actions,
  onPick,
  onClose,
}: {
  heading: string;
  near?: TreeNode;
  kind: 'file' | 'image' | 'text' | 'shareable';
  actions?: ReactNode;
  onPick: (file: TreeNode) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const browsing = useBrowsing(near?.parent ?? null);
  const shown = browsing.children.filter((child) => {
    if (kind === 'text')
      return (
        child.kind === 'folder' ||
        kindOf(child) === 'document' ||
        (child.kind === 'file' && WORD_FILES.has(child.media_type ?? ''))
      );
    if (kind !== 'shareable') return child.kind === 'folder' || kindOf(child) === kind;
    if (child.kind === 'folder') return !child.confined;
    return child.kind !== 'link' && covers(child.role, 'own');
  });
  return (
    <Modal heading={heading} onClose={onClose}>
      <Browser
        browsing={browsing}
        shown={shown}
        empty={t(kind === 'image' ? 'pages.noImages' : 'pages.noFiles')}
        onPick={(file) => {
          onPick(file);
          onClose();
        }}
      />
      {browsing.error && <p className="text-sm text-danger">{errorMessage(browsing.error, t)}</p>}
      <div className="flex justify-end gap-2">
        {actions}
        <Cancel />
      </div>
    </Modal>
  );
}

export function ConfirmDialog({
  heading,
  confirmLabel,
  onConfirm,
  onClose,
  children,
}: {
  heading: string;
  confirmLabel: string;
  onConfirm: () => void;
  onClose: () => void;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const returnFocus = useReturnFocus();
  return (
    <AlertDialog.Root open onOpenChange={(open) => open || onClose()}>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className={overlay} />
        <AlertDialog.Content className={panel} onCloseAutoFocus={returnFocus}>
          <AlertDialog.Title className="text-lg font-semibold">{heading}</AlertDialog.Title>
          <AlertDialog.Description className="text-sm">{children}</AlertDialog.Description>
          <div className="flex justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <button type="button" className={button}>
                {t('tree.cancel')}
              </button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button type="button" onClick={onConfirm} className={dangerButton}>
                {confirmLabel}
              </button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
