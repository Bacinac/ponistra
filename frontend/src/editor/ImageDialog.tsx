import type { EditorView } from 'prosemirror-view';
import { FilePickDialog } from '../dialogs';
import { useI18n } from '../i18n';
import { button } from '../styles';
import { useNode } from '../tree';
import { insertImageFile, insertImages, pickImages, type ImageHost } from './images';

/** A picture put in as a copy: a file of the folders, starting beside the document, or one from
 * the computer. */
export function ImageDialog({
  view,
  host,
  onClose,
}: {
  view: EditorView;
  host: ImageHost;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const near = useNode(host.document).data?.node;
  if (!near) return null;
  return (
    <FilePickDialog
      heading={t('image.insert')}
      near={near}
      kind="image"
      onPick={(file) => insertImageFile(view, host, file.id)}
      onClose={onClose}
      actions={
        <button
          type="button"
          className={button}
          onClick={() => {
            onClose();
            pickImages().then((files) => insertImages(view, host, files), host.fail);
          }}
        >
          {t('file.fromComputer')}
        </button>
      }
    />
  );
}
