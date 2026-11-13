import {
  Download,
  ExternalLink,
  FileText,
  FolderInput,
  FolderTree,
  HardDriveUpload,
  Lock,
  Paperclip,
  Play,
  X,
} from 'lucide-react';
import { useState, type DragEvent } from 'react';
import { Link } from 'react-router';
import { upload, type StoredFile } from './api';
import { FilePickDialog, FolderPickDialog, Modal } from './dialogs';
import { dropped } from './drag';
import { formatSize } from './explorer';
import { useI18n } from './i18n';
import { Menu, MenuItem } from './menu';
import { Shown } from './preview';
import { useHeldRelease } from './release';
import { button, iconButton, primaryButton } from './styles';
import {
  errorMessage,
  kindOf,
  NodeIcon,
  nodeHref,
  useTreeChange,
  type ListedNode,
  type TreeNode,
} from './tree';
import { isHidden, placed, useFilePicker } from './upload';

/** A file a message carries: bytes that belong to the conversation (`href`), or a file of the
 * tree (`node`), which is absent for someone without a right to it. */
export interface Carried {
  id: number | string;
  name: string;
  blob: string | null;
  size: number | null;
  media_type: string | null;
  href: string | null;
  picture: boolean;
  node: ListedNode | null;
}

interface Attaching {
  key: number;
  name: string;
  size: number;
  sent: number;
  stored?: StoredFile;
  node?: TreeNode;
  failure?: Error;
}

let keys = 0;

/** The files of a message being written: each uploads the moment it is added. */
export function useAttachments() {
  const [items, setItems] = useState<Attaching[]>([]);
  const change = (key: number, part: Partial<Attaching>) =>
    setItems((all) => all.map((each) => (each.key === key ? { ...each, ...part } : each)));
  const addFiles = (files: File[]) => {
    const made = files.map((file) => ({
      file,
      item: { key: ++keys, name: file.name, size: file.size, sent: 0 },
    }));
    setItems((all) => [...all, ...made.map((each) => each.item)]);
    for (const { file, item } of made)
      upload(file, (sent) => change(item.key, { sent })).then(
        (stored) => change(item.key, { stored }),
        (failure: Error) => change(item.key, { failure }),
      );
  };
  useHeldRelease(items.some((each) => !each.stored && !each.node && !each.failure));
  return {
    items,
    addFiles,
    addNode: (node: TreeNode) =>
      setItems((all) => [...all, { key: ++keys, name: node.title, size: 0, sent: 0, node }]),
    remove: (key: number) => setItems((all) => all.filter((each) => each.key !== key)),
    clear: () => setItems([]),
    ready: items.every((each) => each.stored || each.node),
    given: () =>
      items.map((each) =>
        each.node ? { node: each.node.id } : { blob: each.stored!.sha256, name: each.name },
      ),
  };
}

export type Attachments = ReturnType<typeof useAttachments>;

/** Lets files dragged from the computer fall anywhere on a conversation's column. */
export function dropTarget(attachments: Attachments) {
  const carriesFiles = (event: DragEvent) => event.dataTransfer.types.includes('Files');
  return {
    onDragOver: (event: DragEvent) => {
      if (carriesFiles(event)) event.preventDefault();
    },
    onDrop: (event: DragEvent) => {
      if (!carriesFiles(event)) return;
      event.preventDefault();
      void dropped(event.dataTransfer).then((picked) =>
        attachments.addFiles(picked.filter((each) => !isHidden(each)).map((each) => each.file)),
      );
    },
  };
}

export function AttachButton({ attachments }: { attachments: Attachments }) {
  const { t } = useI18n();
  const [picking, setPicking] = useState(false);
  const picker = useFilePicker(attachments.addFiles);
  return (
    <>
      {picker.element}
      <Menu
        trigger={
          <button
            type="button"
            aria-label={t('chat.attach')}
            title={t('chat.attach')}
            className={iconButton}
          >
            <Paperclip size={18} aria-hidden />
          </button>
        }
      >
        <MenuItem
          icon={HardDriveUpload}
          label={t('chat.fromComputer')}
          onSelect={() => picker.open()}
        />
        <MenuItem
          icon={FolderTree}
          label={t('chat.fromDocuments')}
          onSelect={() => setPicking(true)}
        />
      </Menu>
      {picking && (
        <FilePickDialog
          heading={t('chat.fromDocuments')}
          kind="shareable"
          onPick={attachments.addNode}
          onClose={() => setPicking(false)}
        />
      )}
    </>
  );
}

export function AttachedChips({ attachments }: { attachments: Attachments }) {
  const { t, formatNumber } = useI18n();
  if (attachments.items.length === 0) return null;
  return (
    <ul aria-label={t('chat.attached')} className="flex flex-wrap gap-1">
      {attachments.items.map((each) => {
        const going = !each.stored && !each.node && !each.failure;
        const part = each.size ? Math.round((each.sent * 100) / each.size) : 0;
        return (
          <li
            key={each.key}
            className="flex max-w-full items-center gap-2 rounded border border-line px-2 py-1 text-xs"
          >
            <span className="min-w-0 truncate">{each.name}</span>
            {going ? (
              <span
                role="progressbar"
                aria-valuenow={part}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={each.name}
                className="h-1 w-16 shrink-0 rounded bg-line"
              >
                <span className="block h-1 rounded bg-accent" style={{ width: `${part}%` }} />
              </span>
            ) : each.failure ? (
              <span className="text-danger">{errorMessage(each.failure, t)}</span>
            ) : (
              !each.node && (
                <span className="shrink-0 text-muted">{formatSize(each.size, formatNumber)}</span>
              )
            )}
            <button
              type="button"
              aria-label={t('chat.removeFile')}
              title={t('chat.removeFile')}
              onClick={() => attachments.remove(each.key)}
              className="shrink-0 text-muted hover:text-ink"
            >
              <X size={12} aria-hidden />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

const fileOfNode = (node: ListedNode) => `/api/nodes/${node.id}/file`;

function isVideo({ node, media_type }: Carried): boolean {
  return node ? kindOf(node) === 'video' : !!media_type?.startsWith('video/');
}

function isPicture({ node, media_type, picture }: Carried): boolean {
  return node ? kindOf(node) === 'image' : picture && !!media_type?.startsWith('image/');
}

function previewOf({ node, href }: Carried): string {
  return node ? `/api/nodes/${node.id}/picture` : `${href}/picture`;
}

const FACE = 'max-h-48 w-full rounded object-contain';

/** The first page or beginning a card opens with, if the file has one. */
function Beginning({ file }: { file: Carried }) {
  const [missing, setMissing] = useState(false);
  const { node, name, picture } = file;
  if (missing) return null;
  if (node && ['document', 'table', 'slides'].includes(kindOf(node)))
    return (
      <div className="pointer-events-none max-h-40 overflow-hidden">
        <Shown node={node} />
      </div>
    );
  if (node ? kindOf(node) === 'file' : picture)
    return (
      <img
        src={previewOf(file)}
        alt={name}
        loading="lazy"
        onError={() => setMissing(true)}
        className="max-h-40 w-full object-contain"
      />
    );
  return null;
}

function Card({ file, onOpen }: { file: Carried; onOpen: () => void }) {
  const { t, formatNumber } = useI18n();
  const { node, href, name, size } = file;
  if (!node && !href)
    return (
      <p className="flex items-center gap-2 rounded border border-line px-2 py-1.5 text-xs text-muted">
        <Lock size={14} aria-hidden className="shrink-0" />
        <span className="min-w-0 truncate">{name}</span>
        <span className="shrink-0">{t('chat.fileClosed')}</span>
      </p>
    );
  const source = node ? fileOfNode(node) : href!;
  if (isPicture(file) || isVideo(file))
    return (
      <button
        type="button"
        aria-label={name}
        title={name}
        onClick={onOpen}
        className="relative block w-64 max-w-full overflow-hidden rounded"
      >
        {isVideo(file) ? (
          <>
            <video src={source} preload="metadata" muted playsInline className={FACE} />
            <Play
              size={32}
              aria-hidden
              className="absolute inset-0 m-auto rounded-full bg-raised p-1.5 text-ink"
            />
          </>
        ) : (
          <img src={previewOf(file)} alt={name} loading="lazy" className={FACE} />
        )}
      </button>
    );
  const shownSize = node?.size ?? size;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-64 max-w-full flex-col gap-1 overflow-hidden rounded border border-line bg-surface p-1.5 text-left hover:bg-hover"
    >
      <Beginning file={file} />
      <span className="flex items-center gap-2 text-xs">
        {node ? (
          <NodeIcon node={node} size={14} decorative />
        ) : (
          <FileText size={14} aria-hidden className="shrink-0" />
        )}
        <span className="min-w-0 flex-1 truncate font-medium">{name}</span>
        {shownSize ? (
          <span className="shrink-0 text-muted">{formatSize(shownSize, formatNumber)}</span>
        ) : null}
      </span>
    </button>
  );
}

function asCarried(node: ListedNode): Carried {
  return {
    id: node.id,
    name: node.title,
    blob: null,
    size: null,
    media_type: null,
    href: null,
    picture: false,
    node,
  };
}

/** What a message carries, and the items its text links to, drawn the same way. */
export function CarriedFiles({
  files,
  items,
  onOpen,
}: {
  files: Carried[];
  items: ListedNode[];
  onOpen: (file: Carried) => void;
}) {
  const shown = [...files, ...items.map(asCarried)];
  if (shown.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1.5">
      {shown.map((file) => (
        <Card key={file.id} file={file} onOpen={() => onOpen(file)} />
      ))}
    </div>
  );
}

function Bytes({ file }: { file: Carried }) {
  const { href, media_type, name, picture } = file;
  const wide = 'max-h-[70vh] w-full object-contain';
  if (media_type?.startsWith('video/'))
    return <video src={href!} controls preload="metadata" className="max-h-[70vh] w-full" />;
  if (media_type?.startsWith('audio/'))
    return <audio src={href!} controls preload="metadata" className="w-full" />;
  if (media_type?.startsWith('image/')) return <img src={href!} alt={name} className={wide} />;
  return picture ? <img src={previewOf(file)} alt={name} className={wide} /> : null;
}

/** A carried file over the conversation, which stays where it was beneath it. */
export function FileView({
  file,
  canSave,
  onClose,
}: {
  file: Carried;
  canSave: boolean;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const [choosing, setChoosing] = useState(false);
  const { node, href, name, size, blob, media_type } = file;
  const save = useTreeChange((parent: string | null) =>
    placed({ sha256: blob!, media_type: media_type! }, name, parent),
  );
  return (
    <Modal wide heading={name} onClose={onClose}>
      <div className="flex max-h-[70vh] min-h-0 flex-col gap-2 overflow-y-auto">
        {node ? <Shown node={node} /> : <Bytes file={file} />}
      </div>
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
      <div className="flex flex-wrap items-center justify-end gap-2">
        {size !== null && (
          <span className="mr-auto text-sm text-muted">{formatSize(size, formatNumber)}</span>
        )}
        {save.data && (
          <Link to={nodeHref(save.data.node)} className="text-sm text-link hover:underline">
            {t('chat.savedAt')}
          </Link>
        )}
        {href && canSave && !save.data && (
          <button
            type="button"
            disabled={save.isPending}
            onClick={() => setChoosing(true)}
            className={button}
          >
            <FolderInput size={16} aria-hidden />
            {t('share.toFolder')}
          </button>
        )}
        {href && media_type === 'application/pdf' && (
          <a href={href} target="_blank" rel="noopener noreferrer" className={button}>
            <ExternalLink size={16} aria-hidden />
            {t('tree.open')}
          </a>
        )}
        {href && (
          <a href={href} download={name} className={button}>
            <Download size={16} aria-hidden />
            {t('file.download')}
          </a>
        )}
        {node && (
          <Link to={nodeHref(node)} className={primaryButton}>
            {t('tree.open')}
          </Link>
        )}
        <button type="button" onClick={onClose} className={button}>
          {t('frame.close')}
        </button>
      </div>
      {choosing && (
        <FolderPickDialog
          heading={t('share.toFolder')}
          confirmLabel={t('share.saveHere')}
          onPick={(parent) => {
            setChoosing(false);
            save.mutate(parent);
          }}
          onClose={() => setChoosing(false)}
        />
      )}
    </Modal>
  );
}

let handed: { conversation: string; text: string; files: File[] } | null = null;

/** Leaves what another app shared for the composer of the conversation about to open. */
export function handOver(conversation: string, text: string, files: File[]) {
  handed = { conversation, text, files };
}

export function takeHanded(conversation: string): { text: string; files: File[] } | null {
  if (handed?.conversation !== conversation) return null;
  const found = handed;
  handed = null;
  return found;
}
