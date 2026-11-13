import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate, useParams } from 'react-router';
import { getJson, postJson, uploadThrough } from './api';
import { SESSION_KEY } from './auth';
import { rememberDoor } from './door';
import { Loading, Lobby } from './frame';
import { useI18n } from './i18n';
import { field, primaryButton } from './styles';
import { useTitle } from './title';
import { errorMessage, nodeHref, type TreeNode } from './tree';
import { named } from './upload';

/** What someone holding a link sees of it before they are in (D39). */
interface Door {
  kind: 'open' | 'people' | 'upload';
  title: string | null;
  password: boolean;
  /** The node, where whoever is signed in reads it already. */
  node: TreeNode | null;
}

/** Signs the browser in as the one the link lets in, then opens the node it gives. */
function useEntering(path: string) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return useMutation({
    mutationFn: (given: object) => postJson<{ node: TreeNode }>(path, given),
    onSuccess: async ({ node }) => {
      rememberDoor(pathname);
      await queryClient.invalidateQueries({ queryKey: SESSION_KEY });
      void navigate(nodeHref(node), { replace: true });
    },
  });
}

/** A document or folder as someone outside the installation reaches it, through a link of its
    owner's: open to whoever holds it, for the recipients of a mail by a code to their address,
    or a folder that asks them for files (D39). */
export function OutsidePage() {
  const { t } = useI18n();
  const token = useParams().token ?? '';
  const door = useQuery({
    queryKey: ['outside', token],
    queryFn: () => getJson<Door>(`/api/outside/${token}`),
    retry: false,
  });
  useTitle(door.data?.title ?? undefined);

  if (door.isPending) return <Loading />;
  if (door.isError) {
    return (
      <Lobby>
        <p className="text-sm text-danger">{errorMessage(door.error, t)}</p>
      </Lobby>
    );
  }
  const { kind, node, title, password } = door.data;
  if (node) return <Navigate to={nodeHref(node)} replace />;
  return (
    <Lobby>
      <div className="flex w-full max-w-sm flex-col gap-3">
        {title && <h2 className="text-center text-lg font-semibold">{title}</h2>}
        {kind === 'upload' ? (
          <AskedFiles token={token} />
        ) : kind === 'people' ? (
          <ByCode token={token} />
        ) : password ? (
          <ByPassword token={token} />
        ) : (
          <Entering path={`/api/outside/${token}/enter`} />
        )}
      </div>
    </Lobby>
  );
}

/** The personal link of someone a document was shared with by address. */
export function VisitPage() {
  const key = useParams().key ?? '';
  return (
    <Lobby>
      <Entering path={`/api/visit/${key}`} />
    </Lobby>
  );
}

function Entering({ path }: { path: string }) {
  const { t } = useI18n();
  const enter = useEntering(path);
  const asked = useRef(false);
  useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    enter.mutate({});
  }, [enter]);
  if (enter.isError) return <p className="text-sm text-danger">{errorMessage(enter.error, t)}</p>;
  return <Loading />;
}

function ByPassword({ token }: { token: string }) {
  const { t } = useI18n();
  const enter = useEntering(`/api/outside/${token}/enter`);
  const [password, setPassword] = useState('');
  const send = (event: FormEvent) => {
    event.preventDefault();
    enter.mutate({ password });
  };
  return (
    <form onSubmit={send} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        {t('outside.asked')}
        <input
          type="password"
          autoFocus
          autoComplete="off"
          required
          aria-label={t('outside.password')}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={field}
        />
      </label>
      {enter.isError && <p className="text-sm text-danger">{errorMessage(enter.error, t)}</p>}
      <button type="submit" disabled={enter.isPending} className={primaryButton}>
        {t('outside.open')}
      </button>
    </form>
  );
}

/** A recipient of a mail shows who they are by a code sent to their address. */
function ByCode({ token }: { token: string }) {
  const { t, language } = useI18n();
  const enter = useEntering(`/api/outside/${token}/enter`);
  const [address, setAddress] = useState('');
  const [code, setCode] = useState('');
  const asked = useMutation({
    mutationFn: () => postJson(`/api/outside/${token}/code`, { address, language }),
  });
  const ask = (event: FormEvent) => {
    event.preventDefault();
    asked.mutate();
  };
  const send = (event: FormEvent) => {
    event.preventDefault();
    enter.mutate({ address, code: code.trim() });
  };
  if (!asked.isSuccess) {
    return (
      <form onSubmit={ask} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('outside.address')}
          <input
            type="email"
            autoFocus
            autoComplete="email"
            required
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            className={field}
          />
        </label>
        {asked.isError && <p className="text-sm text-danger">{errorMessage(asked.error, t)}</p>}
        <button type="submit" disabled={asked.isPending} className={primaryButton}>
          {t('outside.sendCode')}
        </button>
      </form>
    );
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-3">
      <p className="text-sm text-muted">{t('outside.codeSent').replace('{address}', address)}</p>
      <label className="flex flex-col gap-1 text-sm">
        {t('outside.code')}
        <input
          autoFocus
          autoComplete="one-time-code"
          inputMode="numeric"
          required
          value={code}
          onChange={(event) => setCode(event.target.value)}
          className={field}
        />
      </label>
      {enter.isError && <p className="text-sm text-danger">{errorMessage(enter.error, t)}</p>}
      <button type="submit" disabled={enter.isPending} className={primaryButton}>
        {t('outside.open')}
      </button>
      <button
        type="button"
        onClick={() => asked.reset()}
        className="text-sm text-muted hover:text-ink"
      >
        {t('outside.otherAddress')}
      </button>
    </form>
  );
}

/** A folder's link that asks whoever holds it for files, without an account. */
function AskedFiles({ token }: { token: string }) {
  const { t, formatNumber } = useI18n();
  const [sender, setSender] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [delivered, setDelivered] = useState<string[]>([]);
  const chosen = useRef<HTMLInputElement>(null);
  const send = useMutation({
    mutationFn: async () => {
      for (const [index, file] of files.entries()) {
        setProgress({ done: index, total: files.length });
        const upload = await uploadThrough(`/api/outside/${token}/uploads`, file);
        const { title } = await postJson<{ title: string }>(`/api/outside/${token}/files`, {
          upload,
          sender,
          ...named(file.name),
          modified: new Date(file.lastModified).toISOString(),
        });
        setDelivered((before) => [...before, title]);
      }
    },
    onSettled: () => {
      setProgress(null);
      setFiles([]);
      if (chosen.current) chosen.current.value = '';
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    send.mutate();
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        {t('outside.sender')}
        <input
          required
          autoComplete="name"
          value={sender}
          onChange={(event) => setSender(event.target.value)}
          className={field}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t('outside.files')}
        <input
          ref={chosen}
          type="file"
          multiple
          required
          onChange={(event) => setFiles([...(event.target.files ?? [])])}
          className={field}
        />
      </label>
      {progress && (
        <p role="status" className="text-sm text-muted">
          {t('outside.sending')
            .replace('{done}', formatNumber(progress.done + 1))
            .replace('{total}', formatNumber(progress.total))}
        </p>
      )}
      {send.isError && <p className="text-sm text-danger">{errorMessage(send.error, t)}</p>}
      <button type="submit" disabled={send.isPending} className={primaryButton}>
        {t('outside.send')}
      </button>
      {delivered.length > 0 && (
        <div role="status" className="flex flex-col gap-1 text-sm">
          <p className="font-semibold">{t('outside.delivered')}</p>
          <ul className="list-inside list-disc text-muted">
            {delivered.map((title, index) => (
              <li key={index}>{title}</li>
            ))}
          </ul>
        </div>
      )}
    </form>
  );
}
