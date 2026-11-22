import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Download,
  File,
  Folder,
  FolderOpen,
  KeyRound,
  Link2Off,
  Pencil,
  Plus,
  Server,
  Trash2,
  X,
} from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { deleteJson, getJson, postJson } from './api';
import { CodeEditor, type Opened, type Written } from './codeEditor';
import { Cancel, ConfirmDialog, Modal, Picker } from './dialogs';
import { formatSize } from './explorer';
import { Loading, useWide } from './frame';
import { Headed, inline } from './headed';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { useHeldRelease } from './release';
import { ActionsMenu, Menu, MenuChoices, MenuItem, MenuSeparator } from './menu';
import { button, field, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';
import { CopyButton } from './vault/parts';

type Kind = 'folder' | 'file' | 'outside' | 'broken' | 'other';

interface Entry {
  name: string;
  kind: Kind;
  size: number | null;
  modified: string | null;
}

interface Listed {
  path: string;
  entries: Entry[];
}

const UNOPENED: Partial<Record<Kind, MessageKey>> = {
  outside: 'workspace.files.outside',
  broken: 'workspace.files.broken',
  other: 'workspace.files.other',
};

/** Where files are read: a project of the workspace, or a host it reaches over SSH (PJ12). */
export type Place = { folder: string } | { host: string };

const placeOf = (place: Place, path: string) => new URLSearchParams({ ...place, path }).toString();
const placeKey = (place: Place) => ('host' in place ? `host:${place.host}` : place.folder);

const listKey = (place: Place, path: string) => ['workspace', 'files', placeKey(place), path];
const fileKey = (place: Place, path: string) => ['workspace', 'file', placeKey(place), path];

const within = (parent: string, name: string) => (parent ? `${parent}/${name}` : name);

/** One folder's entries, each folder opening its own below it. */
function Entries({
  place,
  path,
  depth,
  open,
  chosen,
  onToggle,
  onChoose,
}: {
  place: Place;
  path: string;
  depth: number;
  open: Set<string>;
  chosen: string | null;
  onToggle: (path: string) => void;
  onChoose: (path: string) => void;
}) {
  const { t } = useI18n();
  const listed = useQuery({
    queryKey: listKey(place, path),
    queryFn: () => getJson<Listed>(`/api/workspace/files?${placeOf(place, path)}`),
  });
  const indent = { paddingLeft: `${depth * 0.75 + 0.25}rem` };
  if (listed.isPending)
    return (
      <p style={indent} className="py-1 text-sm text-muted">
        {t('tree.loading')}
      </p>
    );
  if (listed.isError)
    return (
      <p style={indent} className="py-1 text-sm text-danger">
        {errorMessage(listed.error, t)}
      </p>
    );
  if (!listed.data.entries.length)
    return (
      <p style={indent} className="py-1 text-sm text-muted">
        {t('workspace.files.empty')}
      </p>
    );
  return (
    <ul role={depth ? 'group' : 'tree'} aria-label={depth ? undefined : t('workspace.view.files')}>
      {listed.data.entries.map((entry) => {
        const at = within(path, entry.name);
        const unopened = UNOPENED[entry.kind];
        const expanded = entry.kind === 'folder' && open.has(at);
        const Icon =
          entry.kind === 'folder'
            ? expanded
              ? ChevronDown
              : ChevronRight
            : unopened
              ? Link2Off
              : File;
        return (
          <li
            key={entry.name}
            role="treeitem"
            aria-expanded={entry.kind === 'folder' ? expanded : undefined}
            aria-selected={chosen === at}
          >
            <button
              type="button"
              disabled={Boolean(unopened)}
              title={unopened ? t(unopened) : entry.name}
              onClick={() => (entry.kind === 'folder' ? onToggle(at) : onChoose(at))}
              style={indent}
              className={`flex w-full min-w-0 items-center gap-1.5 rounded py-1 pr-2 text-left text-sm hover:bg-hover disabled:text-muted disabled:hover:bg-transparent ${chosen === at ? 'bg-selected' : ''}`}
            >
              <Icon size={14} aria-hidden className="shrink-0 text-muted" />
              {entry.kind === 'folder' && (
                <Folder size={14} aria-hidden className="shrink-0 text-muted" />
              )}
              <span className="truncate">{entry.name}</span>
            </button>
            {expanded && (
              <Entries
                place={place}
                path={at}
                depth={depth + 1}
                open={open}
                chosen={chosen}
                onToggle={onToggle}
                onChoose={onChoose}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** A file chosen in the tree: its text to edit, or what it is and a download. */
function FileView({
  place,
  path,
  onDirty,
}: {
  place: Place;
  path: string;
  onDirty: (dirty: boolean) => void;
}) {
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const opened = useQuery({
    queryKey: fileKey(place, path),
    queryFn: () => getJson<Opened>(`/api/workspace/file?${placeOf(place, path)}`),
  });
  if (opened.isPending) return <Loading />;
  if (opened.isError)
    return <p className="p-2 text-sm text-danger">{errorMessage(opened.error, t)}</p>;
  if (opened.data.kind === 'text')
    return (
      <CodeEditor
        source={placeKey(place)}
        path={path}
        opened={opened.data}
        read={() => getJson<Opened>(`/api/workspace/file?${placeOf(place, path)}`)}
        write={(text, hash) =>
          postJson<Written>('/api/workspace/file', { ...place, path, text, hash })
        }
        onWritten={(written, text) => {
          queryClient.setQueryData<Opened>(fileKey(place, path), (before) =>
            before ? { ...before, ...written, text } : before,
          );
          void queryClient.invalidateQueries({
            queryKey: listKey(place, path.replace(/\/?[^/]*$/, '')),
          });
        }}
        onRead={(now) => queryClient.setQueryData(fileKey(place, path), now)}
        onDirty={onDirty}
      />
    );
  return (
    <div className="flex flex-col items-start gap-3 p-4 text-sm">
      <p className="font-mono text-xs text-muted">{path}</p>
      <p>
        {t(opened.data.kind === 'large' ? 'workspace.files.large' : 'workspace.files.binary')}{' '}
        <span className="text-muted">{formatSize(opened.data.size, formatNumber)}</span>
      </p>
      <a
        href={`/api/workspace/file/raw?${placeOf(place, path)}`}
        download={path.split('/').pop()}
        className={button}
      >
        <Download size={14} aria-hidden />
        {t('workspace.files.download')}
      </a>
    </div>
  );
}

interface Host {
  name: string;
  address: string;
  port: number;
  user: string;
  path: string;
  key: string;
}

interface Key {
  name: string;
  type: string;
  comment: string;
  public: string;
}

interface Hosts {
  hosts: Host[];
  keys: Key[];
  made: string;
}

const HOSTS = ['workspace', 'hosts'];
const HOST_NAME = '[A-Za-z0-9][A-Za-z0-9._\\-]{0,62}';
const HOST_ADDRESS = '[A-Za-z0-9._:\\-]{1,253}';
const HOST_USER = '[A-Za-z0-9._][A-Za-z0-9._\\-]{0,63}';

const useHosts = () =>
  useQuery({ queryKey: HOSTS, queryFn: () => getJson<Hosts>('/api/workspace/hosts') });

/** A host's entry, new or in the place of the one it was, the key among those of the workspace. */
function HostDialog({
  host,
  keys,
  made,
  onSaved,
  onClose,
}: {
  host: Host | null;
  keys: Key[];
  made: string;
  onSaved: (name: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState(host?.name ?? '');
  const [address, setAddress] = useState(host?.address ?? '');
  const [port, setPort] = useState(String(host?.port ?? 22));
  const [user, setUser] = useState(host?.user ?? '');
  const [path, setPath] = useState(host?.path ?? '');
  const [key, setKey] = useState(
    host?.key ?? keys.find((each) => each.name === made)?.name ?? keys[0]?.name ?? '',
  );
  const save = useMutation({
    mutationFn: () => {
      const given = { name, address, port: Number(port), user, path, key };
      return postJson<Hosts>('/api/workspace/hosts', host ? { ...given, was: host.name } : given);
    },
    onSuccess: (now) => {
      queryClient.setQueryData(HOSTS, now);
      for (const kind of ['files', 'file'])
        void queryClient.invalidateQueries({ queryKey: ['workspace', kind, `host:${name}`] });
      onSaved(name);
    },
  });
  const make = useMutation({
    mutationFn: () => postJson<Hosts>('/api/workspace/hosts/key'),
    onSuccess: (now) => {
      queryClient.setQueryData(HOSTS, now);
      setKey(now.made);
    },
  });
  const failure = save.error ?? make.error;

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  const text = (
    label: string,
    value: string,
    onChange: (value: string) => void,
    pattern?: string,
    required = true,
  ) => (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <input
        type="text"
        required={required}
        pattern={pattern}
        spellCheck={false}
        autoCapitalize="off"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={`${field} font-mono`}
      />
    </label>
  );

  return (
    <Modal heading={t(host ? 'workspace.hosts.edit' : 'workspace.hosts.add')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {text(t('workspace.hosts.name'), name, setName, HOST_NAME)}
        <div className="grid grid-cols-[1fr_6rem] gap-2">
          {text(t('workspace.hosts.address'), address, setAddress, HOST_ADDRESS)}
          <label className="flex flex-col gap-1 text-sm">
            {t('workspace.hosts.port')}
            <input
              type="number"
              required
              min={1}
              max={65535}
              value={port}
              onChange={(event) => setPort(event.target.value)}
              className={field}
            />
          </label>
        </div>
        {text(t('workspace.hosts.user'), user, setUser, HOST_USER)}
        {text(t('workspace.hosts.path'), path, setPath, undefined, false)}
        {keys.length ? (
          <Picker
            label={t('workspace.hosts.key')}
            value={key}
            options={keys.map((each) => [each.name, each.name] as const)}
            onChange={setKey}
          />
        ) : (
          <div className={inline}>
            <p className="min-w-0 flex-1 text-sm">{t('workspace.hosts.key')}</p>
            <button
              type="button"
              disabled={make.isPending}
              onClick={() => make.mutate()}
              className={button}
            >
              <KeyRound size={14} aria-hidden />
              {t('workspace.hosts.makeKey')}
            </button>
          </div>
        )}
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button type="submit" disabled={save.isPending || !key} className={primaryButton}>
            {t(host ? 'tree.save' : 'workspace.hosts.add')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** The hosts whose files the workspace reaches, entries of its own ssh config, and the keys it
 * signs in with, the public half of each ready for a host's `authorized_keys`. */
function HostsView({
  onOpen,
  onMoved,
}: {
  onOpen: (host: Host) => void;
  onMoved: (was: string, now: string | null) => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const hosts = useHosts();
  const [editing, setEditing] = useState<Host | null | undefined>(undefined);
  const [removing, setRemoving] = useState<Host | null>(null);
  const remove = useMutation({
    mutationFn: (host: Host) =>
      deleteJson(`/api/workspace/hosts?${new URLSearchParams({ name: host.name })}`),
    onSuccess: (_, host) => {
      setRemoving(null);
      onMoved(host.name, null);
      void queryClient.invalidateQueries({ queryKey: HOSTS });
    },
  });
  const make = useMutation({
    mutationFn: () => postJson<Hosts>('/api/workspace/hosts/key'),
    onSuccess: (now) => queryClient.setQueryData(HOSTS, now),
  });
  const failure = hosts.error ?? remove.error ?? make.error;
  const known = hosts.data;
  return (
    <div className="flex min-h-0 max-w-2xl flex-col gap-8 overflow-y-auto p-3">
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      <Headed
        heading={t('workspace.hosts.title')}
        action={
          <button
            type="button"
            disabled={!known}
            onClick={() => setEditing(null)}
            className={button}
          >
            <Plus size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">{t('workspace.hosts.add')}</span>
          </button>
        }
      >
        {hosts.isPending && <Loading />}
        {known &&
          (known.hosts.length === 0 ? (
            <p className="text-sm text-muted">{t('workspace.hosts.none')}</p>
          ) : (
            <ul className="divide-y divide-line rounded border border-line">
              {known.hosts.map((host) => (
                <li key={host.name} className="flex items-center gap-2 px-3 py-2">
                  <button
                    type="button"
                    onClick={() => onOpen(host)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p className="truncate">{host.name}</p>
                    <p className="truncate font-mono text-xs text-muted">
                      {`${host.user}@${host.address}:${host.port}${host.path ? ` ${host.path}` : ''}`}
                    </p>
                  </button>
                  <ActionsMenu>
                    <MenuItem
                      icon={FolderOpen}
                      label={t('workspace.hosts.open')}
                      onSelect={() => onOpen(host)}
                    />
                    <MenuItem
                      icon={Pencil}
                      label={t('workspace.hosts.edit')}
                      onSelect={() => setEditing(host)}
                    />
                    <MenuSeparator />
                    <MenuItem
                      icon={Trash2}
                      label={t('workspace.hosts.remove')}
                      onSelect={() => setRemoving(host)}
                    />
                  </ActionsMenu>
                </li>
              ))}
            </ul>
          ))}
      </Headed>
      {known && (
        <Headed
          heading={t('workspace.hosts.keys')}
          action={
            !known.keys.some((each) => each.name === known.made) && (
              <button
                type="button"
                disabled={make.isPending}
                onClick={() => make.mutate()}
                className={button}
              >
                <KeyRound size={16} aria-hidden />
                {t('workspace.hosts.makeKey')}
              </button>
            )
          }
        >
          {known.keys.length > 0 && (
            <ul className="divide-y divide-line rounded border border-line">
              {known.keys.map((key) => (
                <li key={key.name} className="flex items-start gap-2 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="truncate">{key.name}</p>
                    <p
                      aria-label={`${t('workspace.hosts.public')} ${key.name}`}
                      className="font-mono text-xs break-all text-muted select-all"
                    >
                      {key.public}
                    </p>
                  </div>
                  <CopyButton text={key.public} label={t('workspace.hosts.copy')} />
                </li>
              ))}
            </ul>
          )}
        </Headed>
      )}
      {editing !== undefined && known && (
        <HostDialog
          host={editing}
          keys={known.keys}
          made={known.made}
          onSaved={(saved) => {
            if (editing && editing.name !== saved) onMoved(editing.name, saved);
            setEditing(undefined);
          }}
          onClose={() => setEditing(undefined)}
        />
      )}
      {removing && (
        <ConfirmDialog
          heading={t('workspace.hosts.removeTitle')}
          confirmLabel={t('workspace.hosts.remove')}
          onConfirm={() => remove.mutate(removing)}
          onClose={() => setRemoving(null)}
        >
          <strong>{removing.name}</strong> {t('workspace.hosts.removeBody')}
        </ConfirmDialog>
      )}
    </div>
  );
}

/** The files of a project of the workspace (PJ6) or of a host it reaches (PJ12): the tree beside
 * the file chosen in it, or one after the other on a narrow screen; the hosts are set up here. */
export function FilesPanel({
  folder,
  name,
  onDirty,
  onClose,
}: {
  folder: string;
  name: string;
  onDirty: (dirty: boolean) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const wide = useWide();
  const queryClient = useQueryClient();
  const [project] = useState<Place>(() => ({ folder }));
  const [place, setPlace] = useState<Place>(project);
  const [setting, setSetting] = useState(false);
  const hosts = useHosts();
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [chosen, setChosen] = useState<string | null>(null);
  const [dirty, setDirtyHere] = useState(false);
  const setDirty = (now: boolean) => {
    setDirtyHere(now);
    onDirty(now);
  };
  const [leaving, setLeaving] = useState<(() => void) | null>(null);
  useHeldRelease(dirty);
  const unsaved = (then: () => void) => (dirty ? setLeaving(() => then) : then());
  const toggle = (path: string) =>
    setOpen((now) => {
      const next = new Set(now);
      if (!next.delete(path)) next.add(path);
      return next;
    });
  const choose = (path: string) => {
    if (path !== chosen) unsaved(() => setChosen(path));
  };
  const go = (to: Place) =>
    unsaved(() => {
      setSetting(false);
      if (placeKey(to) === placeKey(place)) return;
      setPlace(to);
      setOpen(new Set());
      setChosen(null);
      if ('host' in to)
        void queryClient.invalidateQueries({ queryKey: ['workspace', 'files', placeKey(to)] });
    });
  const placeName = 'host' in place ? place.host : name;
  const known = hosts.data?.hosts ?? [];
  const tree = (
    <div className="min-h-0 overflow-y-auto">
      <Entries
        key={placeKey(place)}
        place={place}
        path=""
        depth={0}
        open={open}
        chosen={chosen}
        onToggle={toggle}
        onChoose={choose}
      />
    </div>
  );
  const file = chosen ? (
    <FileView
      key={`${placeKey(place)}\n${chosen}`}
      place={place}
      path={chosen}
      onDirty={setDirty}
    />
  ) : (
    <p className="p-4 text-sm text-muted">{t('workspace.files.none')}</p>
  );
  return (
    <section
      aria-label={t('workspace.view.files')}
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      <div className="mb-2 flex items-center gap-2">
        {!wide && chosen && !setting && (
          <button
            type="button"
            aria-label={t('workspace.files.back')}
            title={t('workspace.files.back')}
            onClick={() => unsaved(() => setChosen(null))}
            className={iconButton}
          >
            <ArrowLeft size={16} aria-hidden />
          </button>
        )}
        <div className="flex min-w-0 flex-1">
          <Menu
            align="start"
            trigger={
              <button
                type="button"
                aria-label={`${t('workspace.files.place')}: ${setting ? t('workspace.hosts.title') : placeName}`}
                className="flex min-w-0 items-center gap-1 rounded px-1 text-sm font-semibold hover:bg-hover"
              >
                {'host' in place && !setting && (
                  <Server size={14} aria-hidden className="shrink-0 text-muted" />
                )}
                <span className="truncate">{setting ? t('workspace.hosts.title') : placeName}</span>
                <ChevronDown size={12} aria-hidden className="shrink-0" />
              </button>
            }
          >
            <MenuChoices
              value={setting ? '' : placeKey(place)}
              choices={[
                { value: placeKey(project), label: name },
                ...known.map((host) => ({ value: `host:${host.name}`, label: host.name })),
              ]}
              onChange={(value) =>
                go(value.startsWith('host:') ? { host: value.slice(5) } : project)
              }
            />
            <MenuSeparator />
            <MenuItem
              icon={Server}
              label={t('workspace.hosts.title')}
              onSelect={() => unsaved(() => setSetting(true))}
            />
          </Menu>
        </div>
        <button
          type="button"
          aria-label={t('workspace.files.close')}
          title={t('workspace.files.close')}
          onClick={() => unsaved(onClose)}
          className={iconButton}
        >
          <X size={16} aria-hidden />
        </button>
      </div>
      {setting ? (
        <div className="flex min-h-[60dvh] flex-1 flex-col overflow-hidden rounded border border-line">
          <HostsView
            onOpen={(host) => go({ host: host.name })}
            onMoved={(was, now) => {
              if (!('host' in place) || place.host !== was) return;
              setPlace(now === null ? project : { host: now });
              setOpen(new Set());
              setChosen(null);
            }}
          />
        </div>
      ) : wide ? (
        <div className="grid min-h-[60dvh] flex-1 grid-cols-[minmax(12rem,18rem)_1fr] overflow-hidden rounded border border-line">
          <div className="flex min-h-0 flex-col border-r border-line p-1">{tree}</div>
          <div className="flex min-h-0 min-w-0 flex-col">{file}</div>
        </div>
      ) : (
        <div className="flex min-h-[60dvh] flex-1 flex-col overflow-hidden rounded border border-line">
          {chosen ? file : <div className="p-1">{tree}</div>}
        </div>
      )}
      {leaving && (
        <ConfirmDialog
          heading={t('workspace.files.discard')}
          confirmLabel={t('workspace.files.discardConfirm')}
          onConfirm={() => {
            setDirty(false);
            leaving();
            setLeaving(null);
          }}
          onClose={() => setLeaving(null)}
        >
          {t('workspace.files.discardBody')}
        </ConfirmDialog>
      )}
    </section>
  );
}
