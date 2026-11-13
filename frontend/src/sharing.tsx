import { useQuery } from '@tanstack/react-query';
import { FolderInput, Mail, MessagesSquare, StickyNote, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { postJson } from './api';
import { Compose } from './compose';
import { nameOf } from './chat';
import { handOver } from './chatFiles';
import { FolderPickDialog, Modal } from './dialogs';
import { formatSize } from './explorer';
import { Frame, Loading } from './frame';
import { useI18n } from './i18n';
import { useLive } from './live';
import { useNewNote } from './notes';
import { button, primaryButton, sideRow } from './styles';
import { errorMessage, Failure, KindIcon, kindOf, useTreeChange, type TreeNode } from './tree';
import { loose, named, useUploads } from './upload';
import { useAccounts } from './mailData';

/** What another app shared, as the service worker keeps it from the share target (D26-4). */
interface Shared {
  title: string;
  text: string;
  url: string;
  files: File[];
}

async function asked<T>(type: 'shared' | 'forget'): Promise<T> {
  const { active } = await navigator.serviceWorker.ready;
  const channel = new MessageChannel();
  const answer = new Promise<T>((resolve, reject) => {
    channel.port1.onmessage = ({ data }: MessageEvent<{ value: T; error?: string }>) =>
      data.error ? reject(new Error(data.error)) : resolve(data.value);
  });
  active!.postMessage({ type }, [channel.port2]);
  return answer;
}

/** The page shared: its link, or else the last address in its text, as most Android apps
 * share a page. */
function pageOf({ url, text }: Shared): string {
  return url || (text.match(/https?:\/\/\S+/gi)?.at(-1) ?? '');
}

function Thumbnail({ file }: { file: File }) {
  const [address, setAddress] = useState<string | null>(null);
  useEffect(() => {
    const made = URL.createObjectURL(file);
    setAddress(made);
    return () => URL.revokeObjectURL(made);
  }, [file]);
  return address ? (
    <img src={address} alt="" className="size-10 shrink-0 rounded object-cover" />
  ) : null;
}

function ConversationPick({
  onPick,
  onClose,
}: {
  onPick: (conversation: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { conversations } = useLive();
  return (
    <Modal heading={t('share.toConversation')} onClose={onClose}>
      <ul className="flex max-h-96 flex-col gap-0.5 overflow-y-auto">
        {conversations.map((each) => (
          <li key={each.id}>
            <button type="button" onClick={() => onPick(each.id)} className={sideRow}>
              <span className="min-w-0 flex-1 truncate text-left">{nameOf(each, t)}</span>
            </button>
          </li>
        ))}
      </ul>
    </Modal>
  );
}

export function SharingPage() {
  const { t, formatNumber } = useI18n();
  const navigate = useNavigate();
  const shared = useQuery({
    queryKey: ['shared'],
    queryFn: () => asked<Shared | null>('shared'),
    staleTime: Infinity,
    gcTime: 0,
  });
  const accounts = useAccounts();
  const uploads = useUploads();
  const note = useNewNote();
  const keep = useTreeChange((given: { parent: string | null; href: string; title: string }) =>
    postJson<TreeNode>('/api/nodes', {
      kind: 'link',
      parent: given.parent,
      href: given.href,
      ...(given.title ? { title: given.title } : {}),
    }),
  );
  const [dialog, setDialog] = useState<'folder' | 'mail' | 'conversation' | null>(null);
  const mine = accounts.data?.accounts ?? [];
  const sender = mine.find((account) => account.default) ?? mine[0];

  function done(to: string) {
    void asked('forget');
    void navigate(to, { replace: true });
  }

  if (shared.isPending)
    return (
      <Frame title={t('share.title')}>
        <Loading />
      </Frame>
    );
  if (shared.isError)
    return (
      <Frame title={t('share.title')}>
        <Failure error={shared.error} />
      </Frame>
    );
  const { data } = shared;
  if (!data)
    return (
      <Frame title={t('share.title')}>
        <p className="text-muted">{t('share.nothing')}</p>
      </Frame>
    );
  const words = [data.text, data.url].filter(Boolean).join('\n');
  const page = pageOf(data);
  const failed = note.error ?? keep.error;
  return (
    <Frame title={t('share.title')}>
      <section className="flex w-full max-w-2xl flex-col gap-4">
        {data.title && <h2 className="font-semibold break-words">{data.title}</h2>}
        {words && <p className="whitespace-pre-wrap break-words">{words}</p>}
        {data.files.length > 0 && (
          <ul
            aria-label={t('share.files')}
            className="divide-y divide-line rounded border border-line"
          >
            {data.files.map((file, index) => (
              <li key={index} className="flex items-center gap-3 px-3 py-2">
                {file.type.startsWith('image/') ? (
                  <Thumbnail file={file} />
                ) : (
                  <KindIcon
                    kind={kindOf({ kind: 'file', media_type: file.type, holds: null })}
                    extension={named(file.name).extension}
                  />
                )}
                <span className="min-w-0 flex-1 truncate">{file.name}</span>
                <span className="shrink-0 text-sm text-muted">
                  {formatSize(file.size, formatNumber)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={data.files.length === 0 && !page}
            onClick={() => setDialog('folder')}
            className={primaryButton}
          >
            <FolderInput size={16} aria-hidden />
            {t('share.toFolder')}
          </button>
          <button
            type="button"
            disabled={!words || note.isPending}
            onClick={() =>
              note.mutate(
                { text: [data.title, data.text].filter(Boolean).join('\n'), link: data.url },
                { onSuccess: () => void asked('forget') },
              )
            }
            className={button}
          >
            <StickyNote size={16} aria-hidden />
            {t('share.toNote')}
          </button>
          <button
            type="button"
            disabled={!sender}
            onClick={() => setDialog('mail')}
            className={button}
          >
            <Mail size={16} aria-hidden />
            {t('share.toMail')}
          </button>
          <button type="button" onClick={() => setDialog('conversation')} className={button}>
            <MessagesSquare size={16} aria-hidden />
            {t('share.toConversation')}
          </button>
          <button type="button" onClick={() => done('/')} className={button}>
            <X size={16} aria-hidden />
            {t('share.discard')}
          </button>
        </div>
        {failed && <p className="text-sm text-danger">{errorMessage(failed, t)}</p>}
      </section>
      {dialog === 'folder' && (
        <FolderPickDialog
          heading={t('share.toFolder')}
          confirmLabel={t('share.saveHere')}
          onPick={(folder) => {
            const to = folder ? `/f/${folder}` : '/documents';
            if (data.files.length > 0) uploads.start(loose(data.files), folder);
            if (!page) return done(to);
            setDialog(null);
            keep.mutate(
              { parent: folder, href: page, title: data.title },
              { onSuccess: () => done(to) },
            );
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'conversation' && (
        <ConversationPick
          onPick={(conversation) => {
            const link = data.url && !data.text.includes(data.url) ? data.url : '';
            const text = [data.text, link].filter(Boolean).join('\n') || data.title;
            handOver(`/api/conversations/${conversation}`, text, data.files);
            done(`/chat/${conversation}`);
          }}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === 'mail' && sender && (
        <Compose
          accounts={mine}
          start={{ account: sender.id, subject: data.title, text: words, files: data.files }}
          onClose={(sent) => (sent ? done('/mail') : setDialog(null))}
        />
      )}
    </Frame>
  );
}
