import { postJson, upload } from '../api';
import { FilePickDialog, WORD_FILES } from '../dialogs';
import { IMPORTED } from '../importable';
import { useI18n } from '../i18n';
import { button } from '../styles';
import { useNode, type TreeNode } from '../tree';
import { named } from '../upload';

const ACCEPT = [...WORD_FILES].flatMap((type) => [type, IMPORTED[type]]).join(',');

function pickWord(): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = ACCEPT;
    input.addEventListener('change', () => resolve(input.files?.[0] ?? null));
    input.click();
  });
}

/** The file from the computer kept as it came, beside the document. */
async function keptBeside(file: File, near: TreeNode): Promise<TreeNode> {
  const stored = await upload(file);
  return postJson<TreeNode>('/api/nodes', {
    kind: 'file',
    parent: near.parent,
    blob: stored.sha256,
    ...named(file.name),
    modified: new Date(file.lastModified).toISOString(),
  });
}

/** What the tab is compared with: a text document or a word processor's file of the folders,
 * starting beside the document, or one from the computer. */
export function CompareFileDialog({
  documentId,
  onCompare,
  onFail,
  onClose,
}: {
  documentId: string;
  onCompare: (file: string) => void;
  onFail: (error: unknown) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const near = useNode(documentId).data?.node;
  if (!near) return null;
  return (
    <FilePickDialog
      heading={t('action.fileCompare')}
      near={near}
      kind="text"
      onPick={(file) => onCompare(file.id)}
      onClose={onClose}
      actions={
        <button
          type="button"
          className={button}
          onClick={() => {
            onClose();
            pickWord()
              .then((file) => file && keptBeside(file, near))
              .then((kept) => kept && onCompare(kept.id), onFail);
          }}
        >
          {t('file.fromComputer')}
        </button>
      }
    />
  );
}
