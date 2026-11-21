import { ChevronDown, Download, FileInput, RefreshCw, X } from 'lucide-react';
import { useState } from 'react';
import { deleteJson, upload } from './api';
import { Close, Modal } from './dialogs';
import { Panel } from './frame';
import { isMessageKey, useI18n } from './i18n';
import { runJob } from './jobs';
import { button } from './styles';
import {
  errorMessage,
  useTreeChange,
  type ImportReport as Report,
  type Tab,
  type TreeNode,
} from './tree';
import { named } from './upload';

export function sourceHref(node: TreeNode): string {
  return `/api/nodes/${node.id}/source?download=1`;
}

function isComplete(report: Report): boolean {
  return (
    Object.keys(report.lost).length === 0 &&
    report.fonts.length === 0 &&
    !report.accepted &&
    !report.functions?.length
  );
}

export interface ImportedInto {
  tab: Tab;
  report: Report;
}

/** A file's tabs put after the document's own. */
export function useImportInto(documentId: string) {
  return useTreeChange(async (file: File) => {
    const stored = await upload(file);
    return runJob<ImportedInto>(
      'into',
      { document: documentId, blob: stored.sha256, title: named(file.name).title },
      file.name,
    );
  });
}

/** The document read from its file once more, as the import reads it now. */
export function useReimport() {
  return useTreeChange((node: TreeNode) =>
    runJob<TreeNode>('reimport', { document: node.id }, node.title),
  );
}

/** What a file imported into the document could not carry, told to whoever imported it. */
export function ImportedDialog({ report, onClose }: { report: Report; onClose: () => void }) {
  const { t } = useI18n();
  const complete = isComplete(report);
  return (
    <Modal heading={t('import.report')} onClose={onClose}>
      <p>{t(complete ? 'import.intoComplete' : 'import.intoPartial')}</p>
      {!complete && <ReportDetails report={report} />}
      <div className="flex justify-end">
        <Close />
      </div>
    </Modal>
  );
}

/** Whether the import of a document left anything behind to tell its editors. */
export function leftBehind(node: TreeNode): boolean {
  return Boolean(node.imported) && !isComplete(node.imported!);
}

/** The header's mark that the import of the document left something behind, opening its report. */
export function ImportButton({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      aria-label={t('import.report')}
      title={t('import.report')}
      aria-pressed={open}
      onClick={onToggle}
      className={`${button} relative aria-pressed:bg-selected`}
    >
      <FileInput size={16} aria-hidden />
      <span aria-hidden className="absolute top-1 right-1 size-2 rounded-full bg-accent" />
    </button>
  );
}

/** What the import of an editor's document left behind, until one of them puts it away. */
export function ImportPanel({
  node,
  confined,
  reimporting,
  onReimport,
  onClose,
}: {
  node: TreeNode;
  /** Whether a folder on the way keeps the document in the browser. */
  confined: boolean;
  reimporting: boolean;
  onReimport: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const dismiss = useTreeChange(() => deleteJson(`/api/nodes/${node.id}/report`));
  const report = node.imported;
  if (!report) return null;
  return (
    <Panel title={t('import.report')} onClose={onClose}>
      <p className="text-sm">{t('import.partial')}</p>
      <div className="text-sm">
        <ReportDetails report={report} />
      </div>
      <div className="flex flex-wrap gap-2">
        {confined ? (
          <button type="button" disabled title={t('confined.hint')} className={button}>
            <Download size={16} aria-hidden />
            {t('import.original')}
          </button>
        ) : (
          <a href={sourceHref(node)} className={button}>
            <Download size={16} aria-hidden />
            {t('import.original')}
          </a>
        )}
        <button type="button" disabled={reimporting} onClick={onReimport} className={button}>
          <RefreshCw size={16} aria-hidden />
          {t('import.again')}
        </button>
        <button
          type="button"
          disabled={dismiss.isPending}
          onClick={() => dismiss.mutate(undefined, { onSuccess: onClose })}
          className={button}
        >
          <X size={16} aria-hidden />
          {t('import.dismiss')}
        </button>
      </div>
      {dismiss.error && <p className="text-sm text-danger">{errorMessage(dismiss.error, t)}</p>}
    </Panel>
  );
}

function ReportDetails({ report }: { report: Report }) {
  const { t, formatNumber } = useI18n();
  const lost = Object.entries(report.lost);
  const named = (key: string) => {
    const message = `import.lost.${key}`;
    return isMessageKey(message) ? t(message) : key;
  };
  return (
    <div className="flex flex-col gap-2">
      {lost.length > 0 && (
        <div>
          <h3 className="font-semibold">{t('import.lost')}</h3>
          <ul className="list-disc pl-5">
            {lost.map(([key, count]) => (
              <li key={key}>
                {named(key)}
                {count > 1 && <span className="text-muted"> ({formatNumber(count)})</span>}
                {key === 'values' && report.cells?.length ? (
                  <span>
                    : {report.cells.join(', ')}
                    {count > report.cells.length && ' …'}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}
      {report.fonts.length > 0 && (
        <div>
          <h3 className="font-semibold">{t('import.fonts')}</h3>
          <ul className="list-disc pl-5">
            {report.fonts.map(({ from, to }) => (
              <li key={from}>
                {from} → {to ?? t('import.fontDefault')}
              </li>
            ))}
          </ul>
        </div>
      )}
      {report.functions?.length ? (
        <div>
          <h3 className="font-semibold">{t('import.functions')}</h3>
          <p>{report.functions.join(', ')}</p>
        </div>
      ) : null}
      {report.macros?.length ? (
        <div>
          <h3 className="font-semibold">{t('import.macros')}</h3>
          <ul className="flex flex-col gap-1 pt-1">
            {report.macros.map((macro) => (
              <Macro key={macro.name} {...macro} />
            ))}
          </ul>
        </div>
      ) : null}
      {report.accepted > 0 && (
        <p>
          {t('import.accepted')}: {formatNumber(report.accepted)}
        </p>
      )}
    </div>
  );
}

function Macro({ name, code }: { name: string; code: string }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="flex flex-col gap-1">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className={`${button} self-start`}
      >
        <ChevronDown
          size={16}
          aria-hidden
          className={open ? 'rotate-180 transition-transform' : 'transition-transform'}
        />
        {name}
      </button>
      {open && (
        <pre className="max-h-80 overflow-auto rounded-md border border-line bg-surface p-2 font-mono text-xs">
          {code}
        </pre>
      )}
    </li>
  );
}
