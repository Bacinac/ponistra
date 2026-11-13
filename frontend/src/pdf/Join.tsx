import { useQueries } from '@tanstack/react-query';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Cancel, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import { runJob } from '../jobs';
import { field, iconButton, primaryButton } from '../styles';
import { errorMessage, KindIcon, useTreeChange, type TreeNode } from '../tree';
import { failure, sealedOf } from './load';

const fileUrl = (id: string) => `/api/nodes/${id}/file`;

/** The files, in the order the user sets, joined into one new file beside the first. */
export default function JoinDialog({
  files,
  onDone,
  onClose,
}: {
  files: TreeNode[];
  onDone: (joined: TreeNode) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [order, setOrder] = useState(files);
  const [title, setTitle] = useState(`${t('join.of')} ${files[0].title}`.slice(0, 200));
  const checks = useQueries({
    queries: files.map((file) => ({
      queryKey: ['sealed', file.id],
      queryFn: () => sealedOf(fileUrl(file.id)),
      staleTime: Infinity,
      retry: false,
    })),
  });
  const checked = new Map(files.map((file, index) => [file.id, checks[index]]));
  const ready = checks.every((check) => check.isSuccess && check.data === null);
  const join = useTreeChange((name: string) =>
    runJob<TreeNode>(
      'compose',
      { title: name, beside: order[0].id, pages: order.map((file) => ({ file: file.id })) },
      name,
    ),
  );

  function swap(index: number, by: -1 | 1) {
    const next = [...order];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    setOrder(next);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    join.mutate(title, { onSuccess: onDone });
  }

  return (
    <Modal heading={t('join.heading')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm">
          {t('tree.name')}
          <input
            required
            maxLength={200}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onFocus={(event) => event.currentTarget.select()}
            className={field}
          />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{t('join.order')}</span>
          <ol className="max-h-64 divide-y divide-line overflow-y-auto rounded border border-line">
            {order.map((file, index) => {
              const check = checked.get(file.id)!;
              const problem = check.isError
                ? failure(check.error, fileUrl(file.id), t)
                : check.data
                  ? t(`pages.sealed.${check.data}`)
                  : null;
              return (
                <li key={file.id} className="flex items-center gap-2 py-1 pr-1 pl-3">
                  <KindIcon kind="file" decorative />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate">{file.title}</span>
                    {problem && <span className="text-xs text-danger">{problem}</span>}
                    {check.isPending && (
                      <span className="text-xs text-muted">{t('join.checking')}</span>
                    )}
                  </span>
                  <button
                    type="button"
                    aria-label={`${t('join.earlier')}: ${file.title}`}
                    title={t('join.earlier')}
                    disabled={index === 0}
                    onClick={() => swap(index, -1)}
                    className={`${iconButton} disabled:opacity-40`}
                  >
                    <ArrowUp size={16} aria-hidden />
                  </button>
                  <button
                    type="button"
                    aria-label={`${t('join.later')}: ${file.title}`}
                    title={t('join.later')}
                    disabled={index === order.length - 1}
                    onClick={() => swap(index, 1)}
                    className={`${iconButton} disabled:opacity-40`}
                  >
                    <ArrowDown size={16} aria-hidden />
                  </button>
                </li>
              );
            })}
          </ol>
        </div>
        {join.isError && <p className="text-sm text-danger">{errorMessage(join.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={!ready || join.isPending} className={primaryButton}>
            {t('join.submit')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
