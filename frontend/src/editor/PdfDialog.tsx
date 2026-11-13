import { useQuery } from '@tanstack/react-query';
import type { EditorView } from 'prosemirror-view';
import { useId, useState, type FormEvent } from 'react';
import { Cancel, FilePickDialog, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { button, field, primaryButton } from '../styles';
import { errorMessage, useNode } from '../tree';
import type { ImageHost } from './images';
import { fromComputer, insertPdfs, pickPdfs, selectedPdf, shownPages, sizesOf } from './pdfs';

/** A PDF put in as a copy: a file of the folders, starting beside the document, or one from the
 * computer, which goes into the document only. */
export function PdfDialog({
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
      heading={t('pdf.insert')}
      near={near}
      kind="file"
      onPick={(file) => insertPdfs(view, host, [{ body: { file: file.id }, title: file.title }])}
      onClose={onClose}
      actions={
        <button
          type="button"
          className={button}
          onClick={() => {
            onClose();
            pickPdfs().then((files) => insertPdfs(view, host, fromComputer(files)), host.fail);
          }}
        >
          {t('file.fromComputer')}
        </button>
      }
    />
  );
}

/** Which of the file's pages the selected PDF shows, from one to another. */
export function PdfPagesDialog({ view, onClose }: { view: EditorView; onClose: () => void }) {
  const { t, formatNumber } = useI18n();
  const id = useId();
  const [picked] = useState(() => selectedPdf(view.state));
  const blob = (picked?.node.attrs.blob as string | null) ?? null;
  const sizes = useQuery({
    queryKey: ['pdf', blob, 'pages'],
    queryFn: () => sizesOf(blob!),
    enabled: blob !== null,
  });
  const count = sizes.data?.length ?? 0;
  const shown = picked && count ? shownPages(picked.node, count) : null;
  const [first, setFirst] = useState<string | null>(null);
  const [last, setLast] = useState<string | null>(null);
  const from = first ?? String(shown?.first ?? '');
  const to = last ?? String(shown?.last ?? '');
  const [low, high] = [Number(from), Number(to)];
  const valid =
    Number.isInteger(low) && Number.isInteger(high) && low >= 1 && low <= high && high <= count;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!valid) return;
    const now = selectedPdf(view.state) ?? picked;
    if (now && view.state.doc.nodeAt(now.pos)?.attrs.id === picked?.node.attrs.id) {
      view.dispatch(
        view.state.tr
          .setNodeAttribute(now.pos, 'first', low === 1 ? null : low)
          .setNodeAttribute(now.pos, 'last', high === count ? null : high),
      );
    }
    onClose();
  }

  const number = (label: string, value: string, set: (value: string) => void, at: string) => (
    <label htmlFor={at} className="flex flex-1 flex-col gap-1 text-sm">
      {label}
      <input
        id={at}
        autoFocus={at.endsWith('first')}
        type="number"
        inputMode="numeric"
        min={1}
        max={count || undefined}
        step={1}
        value={value}
        onChange={(event) => set(event.target.value)}
        aria-invalid={!valid}
        className={field}
      />
    </label>
  );

  return (
    <Modal heading={t('pdf.pages')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <p className="text-sm text-muted">
          {sizes.isError
            ? errorMessage(sizes.error, t)
            : `${t('pdf.pageCount')}: ${count ? formatNumber(count) : '…'}`}
        </p>
        <div className="flex gap-3">
          {number(t('pdf.firstPage'), from, setFirst, `${id}-first`)}
          {number(t('pdf.lastPage'), to, setLast, `${id}-last`)}
        </div>
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={!valid} className={primaryButton}>
            {t('tree.save')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
