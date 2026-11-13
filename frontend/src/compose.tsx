import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Clock,
  Download,
  FolderTree,
  HardDriveUpload,
  Hourglass,
  Languages,
  Link2,
  Paperclip,
  ScanLine,
  Send,
  Trash2,
  X,
} from 'lucide-react';
import type { Node } from 'prosemirror-model';
import type { EditorView } from 'prosemirror-view';
import { Suspense, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { ApiError, deleteJson, getJson, postJson, putJson, upload } from './api';
import { Close, ConfirmDialog, FilePickDialog, Labelled, Modal } from './dialogs';
import { formatSize } from './explorer';
import { languageName, useI18n } from './i18n';
import { type Attachment, type Opened } from './mail';
import { HtmlBody } from './mailBody';
import { PlainBody } from './plain';
import { button, field, iconButton, primaryButton } from './styles';
import { MailEditor } from './MailEditor';
import { mailDoc, mailHtml, opening, resign } from './mailText';
import { ZONE } from './calendarData';
import { Recipients } from './recipients';
import { useReplyTranslation } from './translation';
import { Menu, MenuItem } from './menu';
import { errorMessage, type TreeNode } from './tree';
import { named, useFilePicker } from './upload';
import { WhenDialog } from './when';
import { lazily } from './lazily';
import { dequeue, queue } from './kept';
import { reachable, useReachable } from './live';
import { type Account, accountColor, draftPath, type Person, person } from './mailData';
import { hold, queueing } from './offline';

export type Way = 'reply' | 'all' | 'forward';

/** What the user starts writing from: an account, with what another app shared (D26-4), or a
 * message to answer or forward. The account follows the first recipient to the one the user
 * writes to them from, unless the user chose it. */
export type Start =
  | {
      account: number;
      chosen?: boolean;
      to?: Person[];
      cc?: Person[];
      bcc?: Person[];
      subject?: string;
      text?: string;
      files?: File[];
    }
  | { way: Way; original: Opened; written?: string }
  | { unsent: Unsent };

/** A message the user began and has not sent, as they left the composer. */
export interface Unsent {
  id: number;
  account: number | null;
  updated_at: string;
  send_at: string | null;
  sending: boolean;
  failed: string;
  to: Person[];
  cc: Person[];
  bcc: Person[];
  subject: string;
  html: string;
  files: Added[];
  shared?: Shared[];
  as?: Way;
  original?: number;
  carried?: string[];
  heading?: string[];
  awaited?: string;
  /** The key a device that keeps it without the network names it by (D45). */
  queued?: string;
}

export const UNSENT = ['mail', 'unsent'];

export function useUnsent() {
  return useQuery({
    queryKey: UNSENT,
    queryFn: () => getJson<{ unsent: Unsent[] }>('/api/mail/unsent'),
    select: (data) => data.unsent,
  });
}

interface Draft {
  account: number;
  to: Person[];
  cc: Person[];
  /** Recipients the server names only as Domino does, the address of whom the user must write. */
  unnamed: Person[];
  /** Asked by a mailto link; a reply's draft has none. */
  bcc?: Person[];
  subject: string;
  attachments: Attachment[];
}

interface Added {
  sha256: string;
  name: string;
  size: number;
}

/** A node of the user's the message carries as a link instead of a file: a colleague is given it
    inside, and anyone else opens it by a code to their address (D39). */
interface Shared {
  node: string;
  title: string;
  role: 'read' | 'edit';
  download: boolean;
}

const SHARED_ROLES = ['read', 'edit'] as const;

const ScanDialog = lazily(() => import('./scan'), 'ScanDialog');

function signatureOf(accounts: Account[], id: number): string {
  return accounts.find((account) => account.id === id)?.signature ?? '';
}

export function fullPerson(given: Partial<Person>): string {
  return given.name && given.address ? `${given.name} <${given.address}>` : person(given);
}

/** The message as the user writes it, in a dialog: from an account, to whom, with what. A reply
    or forward starts from the server's draft of it, under the lines saying what it answers. */
export function Compose({
  accounts,
  start,
  onClose,
}: {
  accounts: Account[];
  start: Start;
  /** Told whether the message went. */
  onClose: (sent?: boolean) => void;
}) {
  if ('way' in start) return <Answer accounts={accounts} answering={start} onClose={onClose} />;
  if ('unsent' in start)
    return <Resume accounts={accounts} unsent={start.unsent} onClose={onClose} />;
  const empty = {
    account: start.account,
    to: start.to ?? [],
    cc: start.cc ?? [],
    bcc: start.bcc ?? [],
    unnamed: [],
    subject: start.subject ?? '',
    attachments: [],
  };
  const body = opening(start.text ?? '', signatureOf(accounts, start.account));
  return (
    <ComposeForm
      accounts={accounts}
      draft={empty}
      body={body}
      files={start.files}
      follows={!start.chosen}
      prefilled={Boolean(
        start.to?.length ||
        start.cc?.length ||
        start.bcc?.length ||
        start.subject ||
        start.text ||
        start.files?.length,
      )}
      onClose={onClose}
    />
  );
}

function Answer({
  accounts,
  answering,
  onClose,
}: {
  accounts: Account[];
  answering: { way: Way; original: Opened; written?: string };
  onClose: (sent?: boolean) => void;
}) {
  const { t, formatDate } = useI18n();
  const { original, way } = answering;
  const draft = useQuery({
    queryKey: ['mail', 'draft', original.id, way],
    queryFn: () => getJson<Draft>(draftPath(original.id, way)),
    staleTime: Infinity,
    gcTime: 0,
  });
  // A dialog shown meanwhile would hand focus back to the page as it went, after the composer
  // took it.
  if (draft.isError) {
    return (
      <Modal heading={t('mail.compose')} wide onClose={onClose}>
        <p className="text-danger">{errorMessage(draft.error, t)}</p>
      </Modal>
    );
  }
  if (!draft.data) return null;
  const lines =
    way === 'forward'
      ? [
          `---------- ${t('mail.forwarded')} ----------`,
          `${t('mail.from')}: ${fullPerson(original.sender)}`,
          `${t('mail.date')}: ${formatDate(original.date)}`,
          `${t('mail.subject')}: ${original.subject}`,
          `${t('mail.to')}: ${original.to.map(fullPerson).join(', ')}`,
        ]
      : [`${formatDate(original.date)}, ${fullPerson(original.sender)} ${t('mail.wrote')}`];
  const body = opening(answering.written ?? '', signatureOf(accounts, draft.data.account));
  return (
    <ComposeForm
      accounts={accounts}
      draft={draft.data}
      body={body}
      answering={answering}
      heading={lines}
      onClose={onClose}
    />
  );
}

/** The composer as the user left it, over the message it answers where it answers one. */
function Resume({
  accounts,
  unsent,
  onClose,
}: {
  accounts: Account[];
  unsent: Unsent;
  onClose: (sent?: boolean) => void;
}) {
  const { t } = useI18n();
  const original = useQuery({
    queryKey: ['mail', 'message', unsent.original],
    queryFn: () => getJson<Opened>(`/api/mail/messages/${unsent.original}?zone=${ZONE}`),
    enabled: unsent.original !== undefined,
  });
  const [body] = useState(() => mailDoc(unsent.html));
  if (original.isError) {
    return (
      <Modal heading={t('mail.compose')} wide onClose={onClose}>
        <p className="text-danger">{errorMessage(original.error, t)}</p>
      </Modal>
    );
  }
  if (unsent.original !== undefined && !original.data) return null;
  const carried = unsent.carried ?? [];
  return (
    <ComposeForm
      accounts={accounts}
      draft={{
        account: unsent.account ?? (accounts.find((each) => each.default) ?? accounts[0]).id,
        to: unsent.to,
        cc: unsent.cc,
        unnamed: [],
        subject: unsent.subject,
        attachments: (original.data?.attachments ?? []).filter((each) =>
          carried.includes(each.part),
        ),
      }}
      body={body}
      answering={original.data && unsent.as && { way: unsent.as, original: original.data }}
      heading={unsent.heading}
      saved={unsent}
      onClose={onClose}
    />
  );
}

function ComposeForm({
  accounts,
  draft,
  files: given,
  body,
  answering,
  heading = [],
  follows = false,
  prefilled = false,
  saved,
  onClose,
}: {
  accounts: Account[];
  draft: Draft;
  /** Whether the account follows the first recipient until the user chooses one. */
  follows?: boolean;
  /** Whether the composer opens with something written, which is kept unsent from the start. */
  prefilled?: boolean;
  /** The message as the user left it, which what they write now replaces. */
  saved?: Unsent;
  /** What the user starts writing from. */
  body: Node;
  /** Attached as the form opens. */
  files?: File[];
  answering?: { way: Way; original: Opened };
  /** The lines saying what the message answers or forwards, above that message. */
  heading?: string[];
  onClose: (sent?: boolean) => void;
}) {
  const { t, formatDate, formatNumber, language } = useI18n();
  const queryClient = useQueryClient();
  const [from, setFrom] = useState(draft.account);
  const [to, setTo] = useState(draft.to);
  const [cc, setCc] = useState(draft.cc);
  const [bcc, setBcc] = useState<Person[]>(saved?.bcc ?? draft.bcc ?? []);
  const [copies, setCopies] = useState(draft.cc.length > 0 || bcc.length > 0);
  const [subject, setSubject] = useState(draft.subject);
  const [initial] = useState(() => mailHtml(body));
  const [html, setHtml] = useState(initial);
  const editor = useRef<EditorView | null>(null);
  const [quoted, setQuoted] = useState(false);
  const [askingWhen, setAskingWhen] = useState(false);
  const [askingAwaited, setAskingAwaited] = useState(false);
  const [awaited, setAwaited] = useState<Date | null>(() =>
    saved?.awaited ? new Date(saved.awaited) : null,
  );
  const [carried, setCarried] = useState(draft.attachments);
  const [added, setAdded] = useState<Added[]>(saved?.files ?? []);
  const [shared, setShared] = useState<Shared[]>(saved?.shared ?? []);
  const [pickingNode, setPickingNode] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [scanning, setScanning] = useState(false);
  const sender = accounts.find((account) => account.id === from);
  const offline = queueing(useReachable());
  const [key] = useState(() => saved?.queued ?? crypto.randomUUID());
  useEffect(() => hold(key), [key]);
  const [following, setFollowing] = useState(follows);
  const first = to[0]?.address.toLowerCase();
  const preferred = useQuery({
    queryKey: ['mail', 'sender', first],
    queryFn: () =>
      getJson<{ account: number | null }>(
        `/api/mail/sender?${new URLSearchParams({ to: first ?? '' })}`,
      ),
    enabled: following && Boolean(first),
  });
  const wanted = following && first ? preferred.data?.account : undefined;
  useEffect(() => {
    const account = accounts.find((each) => each.id === wanted);
    if (!account || account.id === from) return;
    const view = editor.current;
    if (view) view.dispatch(resign(view.state, account.signature));
    setFrom(account.id);
  }, [accounts, wanted, from]);
  const unnamed = draft.unnamed.filter((each) =>
    [...to, ...cc].some((person) => person.address === each.address),
  );
  const attach = useMutation({
    mutationFn: (files: File[]) =>
      Promise.all(
        files.map(async (file) => ({ ...(await upload(file)), name: file.name, size: file.size })),
      ),
    onSuccess: (stored) => setAdded((kept) => [...kept, ...stored]),
  });
  const picker = useFilePicker((files) => attach.mutate(files), { accept: '' });
  const attachFiles = attach.mutate;
  const unattached = useRef(given);
  useEffect(() => {
    if (!unattached.current?.length) return;
    attachFiles(unattached.current);
    unattached.current = undefined;
  }, [attachFiles]);
  const written = useMemo(
    () => ({
      account: from,
      to,
      cc,
      bcc,
      subject,
      html,
      ...(answering && {
        as: answering.way,
        original: answering.original.id,
        heading,
        carried: carried.map((each) => each.part),
      }),
      files: added,
      ...(shared.length > 0 && { shared }),
      ...(awaited && { awaited: awaited.toISOString() }),
      queued: key,
    }),
    [from, to, cc, bcc, subject, html, answering, heading, carried, added, shared, awaited, key],
  );
  const translation = useReplyTranslation(
    answering && answering.way !== 'forward' ? answering.original : undefined,
  );
  const reply = translation.reply;
  const unsentId = useRef(saved?.id);
  const keeping = useRef<Promise<unknown>>(Promise.resolve());
  const keptAs = useRef(prefilled && !saved ? '' : JSON.stringify(written));
  const [kept, setKept] = useState<'kept' | Error | null>(null);
  const sending = useRef(false);

  /** Keeps what the user wrote as an unsent message, after whatever keeping went before it. */
  function keep(): Promise<unknown> {
    const now = JSON.stringify(written);
    keeping.current = keeping.current.then(async () => {
      if (sending.current || now === keptAs.current) return;
      try {
        const id = unsentId.current;
        if (queueing(reachable())) {
          await queue({ key, message: written, unsent: id, send: false, written: Date.now() });
          keptAs.current = now;
          setKept('kept');
          return;
        }
        const answer = id
          ? await putJson<Unsent>(`/api/mail/unsent/${id}`, written)
          : await postJson<Unsent>('/api/mail/unsent', written);
        unsentId.current = answer.id;
        keptAs.current = now;
        setKept('kept');
        await dequeue(key);
        void queryClient.invalidateQueries({ queryKey: UNSENT });
      } catch (error) {
        setKept(error as Error);
        throw error;
      }
    });
    return keeping.current;
  }

  useEffect(() => {
    if (JSON.stringify(written) === keptAs.current) return;
    const timer = setTimeout(() => void keep().catch(() => undefined), 1500);
    return () => clearTimeout(timer);
  });

  const send = useMutation({
    mutationFn: async (at?: Date) => {
      await keeping.current.catch(() => undefined);
      sending.current = true;
      const message = {
        ...written,
        ...(reply && {
          subject: reply.subject,
          html: reply.html,
          heading: reply.heading,
          source: reply.source,
        }),
        files: added.map(({ sha256, name }) => ({ sha256, name })),
      };
      try {
        if (queueing(reachable())) {
          await queue({
            key,
            message,
            unsent: unsentId.current,
            send: true,
            at: at?.toISOString(),
            written: Date.now(),
          });
          return { refused: [], kept: true };
        }
        const handed = { ...message, unsent: unsentId.current };
        await dequeue(key);
        if (at) {
          await postJson('/api/mail/later', { ...handed, at: at.toISOString() });
          return { refused: [], kept: true };
        }
        return await postJson<{ refused: string[]; kept: boolean }>('/api/mail/send', handed);
      } catch (error) {
        sending.current = false;
        throw error;
      }
    },
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ['mail', 'messages'] });
      void queryClient.invalidateQueries({ queryKey: ['mail', 'drafts'] });
      void queryClient.invalidateQueries({ queryKey: UNSENT });
      void queryClient.invalidateQueries({ queryKey: ['mail', 'later'] });
      void queryClient.invalidateQueries({ queryKey: ['mail', 'accounts'] });
      if (result.refused.length === 0 && result.kept) onClose(true);
    },
  });
  const linked = useMutation({
    mutationFn: () =>
      Promise.all(
        added.map(async (each) => {
          const node = await postJson<TreeNode>('/api/nodes', {
            kind: 'file',
            parent: null,
            blob: each.sha256,
            ...named(each.name),
          });
          return { node: node.id, title: node.title, role: 'read' as const, download: true };
        }),
      ),
    onSuccess: (made) => {
      setAdded([]);
      setShared((kept) => [...kept, ...made]);
      send.reset();
    },
  });
  const tooLarge =
    send.error instanceof ApiError && send.error.code === 'mail_too_large' && added.length > 0;
  const share = (node: TreeNode) =>
    setShared((kept) =>
      kept.some((each) => each.node === node.id)
        ? kept
        : [...kept, { node: node.id, title: node.title, role: 'read', download: true }],
    );
  const reshare = (node: string, change: Partial<Shared>) =>
    setShared((kept) => kept.map((each) => (each.node === node ? { ...each, ...change } : each)));
  const failure = attach.error ?? linked.error ?? send.error ?? translation.failure;

  function choose(account: number) {
    const view = editor.current;
    if (view) view.dispatch(resign(view.state, signatureOf(accounts, account)));
    setFrom(account);
  }

  const changed =
    to !== draft.to ||
    cc !== draft.cc ||
    bcc.length > 0 ||
    subject !== draft.subject ||
    html !== initial ||
    added.length > 0 ||
    shared.length > 0;

  function close() {
    if (send.isSuccess) return onClose();
    keep().then(
      () => onClose(),
      () => undefined,
    );
  }

  async function discard() {
    sending.current = true;
    await keeping.current.catch(() => undefined);
    await dequeue(key);
    if (unsentId.current) await deleteJson(`/api/mail/unsent/${unsentId.current}`);
    void queryClient.invalidateQueries({ queryKey: UNSENT });
    onClose();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send.mutate();
  }

  if (send.data) {
    return (
      <Modal heading={t('mail.compose')} onClose={() => onClose(true)}>
        {send.data.refused.length > 0 && (
          <p className="text-danger">
            {t('mail.sentRefused')} {send.data.refused.join(', ')}
          </p>
        )}
        {!send.data.kept && <p className="text-danger">{t('mail.sentUnkept')}</p>}
        <div className="flex justify-end">
          <Close />
        </div>
      </Modal>
    );
  }

  const files = [
    ...carried.map((each) => ({
      key: `part-${each.part}`,
      name: each.name,
      size: each.size,
      remove: () => setCarried((kept) => kept.filter((other) => other !== each)),
    })),
    ...added.map((each, at) => ({
      key: `added-${at}`,
      name: each.name,
      size: each.size,
      remove: () => setAdded((kept) => kept.filter((other) => other !== each)),
    })),
  ];
  return (
    <Modal heading={t('mail.compose')} wide onClose={close}>
      <form onSubmit={submit} className="flex min-h-0 flex-col gap-3">
        <Labelled label={t('mail.sender')}>
          {(id) => (
            <div className="flex items-center gap-2">
              {sender && (
                <span
                  aria-hidden
                  className={`size-3 shrink-0 rounded-full ${accountColor(sender)}`}
                />
              )}
              <select
                id={id}
                value={from}
                disabled={reply !== null}
                onChange={(event) => {
                  setFollowing(false);
                  choose(Number(event.target.value));
                }}
                className={`${field} min-w-0 flex-1`}
              >
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name ? `${account.name} <${account.address}>` : account.address}
                  </option>
                ))}
              </select>
            </div>
          )}
        </Labelled>
        <Labelled label={t('mail.to')}>
          {(id) => (
            <Recipients
              id={id}
              people={to}
              onChange={setTo}
              autoFocus={!answering || answering.way === 'forward'}
            />
          )}
        </Labelled>
        {copies ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Labelled label={t('mail.cc')}>
              {(id) => <Recipients id={id} people={cc} onChange={setCc} />}
            </Labelled>
            <Labelled label={t('mail.bcc')}>
              {(id) => <Recipients id={id} people={bcc} onChange={setBcc} />}
            </Labelled>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setCopies(true)}
            className="-mt-1 self-start text-sm text-link hover:underline"
          >
            {t('mail.copies')}
          </button>
        )}
        {unnamed.length > 0 && (
          <p className="-mt-1 text-sm text-danger">
            {t('mail.unnamed')}: {unnamed.map((each) => each.name).join(', ')}
          </p>
        )}
        <Labelled label={t('mail.subject')}>
          {(id) => (
            <input
              id={id}
              maxLength={998}
              value={reply ? reply.subject : subject}
              onChange={(event) =>
                reply
                  ? translation.change({ subject: event.target.value })
                  : setSubject(event.target.value)
              }
              className={field}
            />
          )}
        </Labelled>
        <div className={reply ? 'hidden' : 'flex min-h-0 flex-col'}>
          <MailEditor
            label={t('mail.text')}
            initial={body}
            onChange={setHtml}
            viewRef={editor}
            autoFocus={answering !== undefined && answering.way !== 'forward'}
          />
        </div>
        {reply && (
          <div className="grid gap-3 md:grid-cols-2">
            <section className="flex min-w-0 flex-col gap-1">
              <h3 className="text-sm text-muted">
                {languageName(reply.source.language, language)}
              </h3>
              <HtmlBody title={subject} html={html} />
            </section>
            <section className="flex min-w-0 flex-col gap-1">
              <h3 className="text-sm text-muted">{languageName(reply.language, language)}</h3>
              <MailEditor
                label={languageName(reply.language, language)}
                initial={mailDoc(reply.html)}
                onChange={(changed) => translation.change({ html: changed })}
                autoFocus
              />
            </section>
          </div>
        )}
        {answering &&
          (quoted ? (
            <div className="flex flex-col gap-2 border-l-2 border-line pl-3">
              <p className="text-sm whitespace-pre-line text-muted">{heading.join('\n')}</p>
              {answering.original.html !== null ? (
                <HtmlBody title={answering.original.subject} html={answering.original.html} />
              ) : (
                <PlainBody text={answering.original.text ?? ''} />
              )}
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setQuoted(true)}
              className="-mt-1 self-start text-sm text-link hover:underline"
            >
              {t(answering.way === 'forward' ? 'mail.showForwarded' : 'mail.showQuoted')}
            </button>
          ))}
        {files.length > 0 && (
          <ul aria-label={t('mail.files')} className="flex flex-wrap gap-2">
            {files.map((each) => (
              <li
                key={each.key}
                className="flex min-w-0 max-w-full items-center gap-2 rounded-lg border border-line py-1 pr-1 pl-2 text-sm"
              >
                <Paperclip size={14} aria-hidden className="shrink-0 text-muted" />
                <span className="min-w-0 truncate">{each.name}</span>
                <span className="shrink-0 text-xs text-muted">
                  {formatSize(each.size, formatNumber)}
                </span>
                <button
                  type="button"
                  aria-label={`${t('mail.removeFile')}: ${each.name}`}
                  title={t('mail.removeFile')}
                  onClick={each.remove}
                  className={iconButton}
                >
                  <X size={14} aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {shared.length > 0 && (
          <ul aria-label={t('mail.shared')} className="flex flex-wrap gap-2">
            {shared.map((each) => (
              <li
                key={each.node}
                className="flex min-w-0 max-w-full items-center gap-2 rounded-lg border border-line py-1 pr-1 pl-2 text-sm"
              >
                <Link2 size={14} aria-hidden className="shrink-0 text-muted" />
                <span className="min-w-0 truncate">{each.title}</span>
                <select
                  value={each.role}
                  aria-label={`${t('access.role')}: ${each.title}`}
                  onChange={(event) =>
                    reshare(each.node, { role: event.target.value as Shared['role'] })
                  }
                  className="rounded border border-line bg-surface px-1 py-0.5 text-xs"
                >
                  {SHARED_ROLES.map((option) => (
                    <option key={option} value={option}>
                      {t(`access.role.${option}`)}
                    </option>
                  ))}
                </select>
                <label title={t('outside.download')} className="flex items-center gap-1 text-muted">
                  <input
                    type="checkbox"
                    checked={each.download}
                    onChange={(event) => reshare(each.node, { download: event.target.checked })}
                  />
                  <span className="sr-only">{`${t('outside.download')}: ${each.title}`}</span>
                  <Download size={14} aria-hidden />
                </label>
                <button
                  type="button"
                  aria-label={`${t('mail.removeFile')}: ${each.title}`}
                  title={t('mail.removeFile')}
                  onClick={() =>
                    setShared((kept) => kept.filter((other) => other.node !== each.node))
                  }
                  className={iconButton}
                >
                  <X size={14} aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        {tooLarge && (
          <button
            type="button"
            disabled={linked.isPending || offline}
            onClick={() => linked.mutate()}
            className={`${button} self-start`}
          >
            <Link2 size={16} aria-hidden />
            {t('mail.filesAsLinks')}
          </button>
        )}
        <div className="flex flex-wrap items-center gap-2">
          {picker.element}
          <Menu
            align="start"
            trigger={
              <button type="button" disabled={attach.isPending} className={button}>
                <Paperclip size={16} aria-hidden />
                {t('mail.attach')}
              </button>
            }
          >
            <MenuItem
              icon={HardDriveUpload}
              label={t('chat.fromComputer')}
              disabled={offline}
              onSelect={() => picker.open()}
            />
            <MenuItem
              icon={FolderTree}
              label={t('chat.fromDocuments')}
              onSelect={() => setPickingNode(true)}
            />
          </Menu>
          <button
            type="button"
            disabled={offline}
            onClick={() => setScanning(true)}
            className={button}
          >
            <ScanLine size={16} aria-hidden />
            {t('mail.scan')}
          </button>
          <button
            type="button"
            disabled={offline && unsentId.current !== undefined}
            onClick={() => (changed || unsentId.current ? setDiscarding(true) : onClose())}
            className={button}
          >
            <Trash2 size={16} aria-hidden />
            {t('mail.discard')}
          </button>
          <span className="flex-1" />
          {kept === 'kept' && (
            <span className="text-sm text-muted">
              {t(offline ? 'mail.keptOnDevice' : 'mail.unsentKept')}
            </span>
          )}
          {reply ? (
            <button type="button" onClick={translation.back} className={button}>
              {t('translation.edit')}
            </button>
          ) : (
            translation.offered && (
              <button
                type="button"
                disabled={translation.pending || offline}
                onClick={() => translation.translate({ subject, html, heading })}
                className={button}
              >
                <Languages size={16} aria-hidden />
                {t(translation.pending ? 'translation.translating' : 'translation.reply')}
              </button>
            )
          )}
          {kept instanceof Error && (
            <span className="text-sm text-danger">{errorMessage(kept, t)}</span>
          )}
          <Close />
          {awaited ? (
            <span className="inline-flex items-center gap-1 text-sm text-muted">
              <Hourglass size={14} aria-hidden />
              {t('mail.awaitingUntil').replace('{when}', formatDate(awaited.toISOString()))}
              <button
                type="button"
                aria-label={t('mail.unawait')}
                title={t('mail.unawait')}
                onClick={() => setAwaited(null)}
                className={iconButton}
              >
                <X size={14} aria-hidden />
              </button>
            </span>
          ) : (
            <button
              type="button"
              aria-label={t('mail.await')}
              title={t('mail.await')}
              onClick={() => setAskingAwaited(true)}
              className={iconButton}
            >
              <Hourglass size={18} aria-hidden />
            </button>
          )}
          <button
            type="button"
            disabled={send.isPending || attach.isPending || linked.isPending || translation.pending}
            onClick={() => setAskingWhen(true)}
            className={button}
          >
            <Clock size={16} aria-hidden />
            {t('mail.later')}
          </button>
          <button
            type="submit"
            disabled={send.isPending || attach.isPending || linked.isPending || translation.pending}
            className={primaryButton}
          >
            <Send size={16} aria-hidden />
            {t(send.isPending ? 'mail.sending' : 'mail.send')}
          </button>
        </div>
      </form>
      {translation.dialog}
      {askingAwaited && (
        <WhenDialog
          heading={t('mail.awaitAsk')}
          confirmLabel={t('mail.await')}
          pending={false}
          error={null}
          onChoose={(at) => {
            setAwaited(at);
            setAskingAwaited(false);
          }}
          onClose={() => setAskingAwaited(false)}
        />
      )}
      {askingWhen && (
        <WhenDialog
          heading={t('mail.laterTitleAsk')}
          confirmLabel={t('mail.later')}
          pending={send.isPending}
          error={send.error}
          onChoose={(at) => send.mutate(at, { onSuccess: () => setAskingWhen(false) })}
          onClose={() => setAskingWhen(false)}
        />
      )}
      {pickingNode && (
        <FilePickDialog
          heading={t('chat.fromDocuments')}
          kind="shareable"
          onPick={share}
          onClose={() => setPickingNode(false)}
        />
      )}
      {scanning && (
        <Suspense fallback={null}>
          <ScanDialog
            attached
            onDone={({ sha256, name, size }) => {
              setAdded((kept) => [...kept, { sha256, name, size }]);
              setScanning(false);
            }}
            onClose={() => setScanning(false)}
          />
        </Suspense>
      )}
      {discarding && (
        <ConfirmDialog
          heading={t('mail.discardTitle')}
          confirmLabel={t('mail.discard')}
          onConfirm={() => void discard()}
          onClose={() => setDiscarding(false)}
        >
          {t('mail.discardWarning')}
        </ConfirmDialog>
      )}
    </Modal>
  );
}
