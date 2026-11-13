import * as Dialog from '@radix-ui/react-dialog';
import type { EditorView } from 'prosemirror-view';
import { useState } from 'react';
import { postJson } from '../api';
import { useSession } from '../auth';
import { useReturnFocus } from '../dialogs';
import { Loading } from '../frame';
import { useI18n } from '../i18n';
import { EditPanel, useUndoKeys } from '../image/EditPanel';
import { edited, type Edits, type Ratio, type Tool } from '../image/edits';
import { ImageView, useBitmap } from '../image/ImageView';
import { sentOf, useKept, useOwnImageRoom } from '../image/room';
import type { Pen } from '../pen';
import { errorMessage } from '../tree';
import { placed, selectedImage, type ImageHost } from './images';
import { imageUrl, schema } from './schema';

/** The image the document shows, edited as an image file is and drawn into an image of its own,
 * which the document then shows; the one it showed stays with the document's versions. */
export function ImageEditDialog({
  view,
  host,
  onClose,
}: {
  view: EditorView;
  host: ImageHost;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [picked] = useState(() => selectedImage(view.state)?.node ?? null);
  const blob: string | null = picked?.attrs.blob ?? null;
  const room = useOwnImageRoom();
  const kept = useKept(room);
  const [cropping, setCropping] = useState<Ratio | undefined>();
  const [toning, setToning] = useState<Partial<Edits>>({});
  const [tool, setTool] = useState<Tool | null>(null);
  const [pen, setPen] = useState<Pen>({ color: 'red', width: 2 });
  const [applying, setApplying] = useState(false);
  const [failure, setFailure] = useState<Error | null>(null);
  const me = useSession().data?.user?.id ?? null;
  const returnFocus = useReturnFocus();
  const bitmap = useBitmap(blob && imageUrl(blob));
  const upright = bitmap instanceof ImageBitmap ? bitmap : null;
  const edits = { ...kept.edits, ...toning };
  const altered = edited(kept.edits) || kept.marks.length > 0;
  useUndoKeys(room);

  function apply() {
    if (applying || !picked) return;
    setApplying(true);
    setFailure(null);
    postJson<{ blob: string }>(`/api/nodes/${host.document}/images`, { blob, ...sentOf(kept) })
      .then((drawn) => {
        const now = placed(view.state, schema.nodes.image, picked.attrs.id);
        if (now?.node.attrs.blob === blob) {
          view.dispatch(view.state.tr.setNodeAttribute(now.pos, 'blob', drawn.blob));
        }
        onClose();
      })
      .catch((error: Error) => {
        setFailure(error);
        setApplying(false);
      });
  }

  return (
    <Dialog.Root open onOpenChange={(open) => open || onClose()}>
      <Dialog.Portal>
        <Dialog.Content
          aria-describedby={undefined}
          onCloseAutoFocus={returnFocus}
          onEscapeKeyDown={(event) => {
            // Escape first lets go of what the image has in hand, and never throws edits away.
            if (altered || tool || cropping) event.preventDefault();
          }}
          className="fixed inset-0 z-50 flex bg-panel text-ink md:p-2"
        >
          <Dialog.Title className="sr-only">{t('image.editing')}</Dialog.Title>
          <div className="relative min-w-0 flex-1 overflow-hidden bg-surface md:rounded-2xl md:shadow-sm">
            {bitmap === 'failed' || bitmap === 'unsupported' ? (
              <p className="flex h-full items-center justify-center p-6 text-center text-muted">
                {t(bitmap === 'failed' ? 'image.unreadable' : 'image.unsupported')}
              </p>
            ) : upright ? (
              <ImageView
                bitmap={upright}
                title={picked?.attrs.alt || t('command.image')}
                edits={edits}
                marks={kept.marks}
                cropping={cropping}
                onCrop={(crop) => room?.change({ crop })}
                marking={room && { tool, pen, me, onMark: room.mark, onTool: setTool }}
              />
            ) : (
              <Loading />
            )}
          </div>
          <EditPanel
            room={room}
            kept={kept}
            altered={altered && !applying}
            edits={edits}
            upright={upright}
            cropping={cropping}
            onCropping={setCropping}
            onToning={setToning}
            tool={tool}
            onTool={setTool}
            pen={pen}
            onPen={setPen}
            save={t('image.apply')}
            failure={failure && errorMessage(failure, t)}
            onSave={apply}
            onClose={onClose}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
