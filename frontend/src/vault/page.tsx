import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  FileKey2,
  FileUp,
  FolderClosed,
  FolderInput,
  FolderPlus,
  FolderTree,
  KeyRound,
  Lock,
  Paperclip,
  Pencil,
  Plus,
  RotateCcw,
  ScrollText,
  Settings,
  Share2,
  StickyNote,
  Trash2,
  Upload,
} from 'lucide-react';
import { Fragment, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { ApiError, deleteJson, patchJson, postJson } from '../api';
import { useSession } from '../auth';
import {
  ActionButtons,
  ActionItems,
  ChoiceBar,
  ChoiceBox,
  useChoice,
  type RowAction,
} from '../choice';
import { Cancel, ConfirmDialog, Modal, NameDialog } from '../dialogs';
import { Frame, Loading, PrimaryAction } from '../frame';
import { useI18n } from '../i18n';
import { ContextMenuArea, MenuItem, MenuSeparator } from '../menu';
import { useMenuPress } from '../press';
import { Splitter, useWidth, type Column } from '../split';
import { button, field, iconButton, primaryButton, sideRow } from '../styles';
import { covers, errorMessage } from '../tree';
import { useFilePicker } from '../upload';
import { random, seal, sealTo, toBase64 } from './crypto';
import { counted, laidOut, pathOf, planned, sealedFolders, type Folder } from './folders';
import { LogDialog, MembersPanel } from './members';
import { Detail } from './detail';
import { ItemDialog } from './itemDialog';
import { UnlockForm } from './unlock';
import { CodeShown, KIND_ICONS, NewPassword, saved } from './parts';
import { hostIn, hostOf, sealJson, sealSecret, type Kind, type Opened } from './secret';
import { SettingsDialog } from './settings';
import {
  collectionKey,
  COLLECTIONS,
  enrolled,
  makeVault,
  MINE,
  openedFolders,
  openedItems,
  OPENED,
  setPassword,
  useCollections,
  useOpenedFolders,
  useOpenedItems,
  useOpenedTrash,
  useVault,
  useVaultData,
  type Collection,
  type Unlocked,
  type VaultData,
} from './state';
import { exported, imported, Unreadable, type Filed, type Imported } from './transfer';
import { useAi } from '../editor/runs';

const BATCH = 1000;
const ITEMS: Column = { name: 'items', initial: 448, min: 288, max: 768 };

function Plain({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  return (
    <Frame title={t('vault.title')} folders={false} side={<></>}>
      <div className="flex w-full max-w-md flex-col gap-4">{children}</div>
    </Frame>
  );
}

export function VaultPage() {
  const { t } = useI18n();
  const vault = useVaultData();
  const { unlocked } = useVault();
  const [fresh, setFresh] = useState<string | null>(null);
  if (vault.isPending) {
    return (
      <Plain>
        <Loading />
      </Plain>
    );
  }
  if (vault.isError) {
    return (
      <Plain>
        <p className="text-danger">{errorMessage(vault.error, t)}</p>
      </Plain>
    );
  }
  if (!vault.data) return <Setup onMade={setFresh} />;
  if (!unlocked) return <Locked vault={vault.data} />;
  return (
    <VaultOpen
      vault={vault.data}
      unlocked={unlocked}
      fresh={fresh}
      onFreshSeen={() => setFresh(null)}
    />
  );
}

function Setup({ onMade }: { onMade: (code: string) => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { unlock } = useVault();
  const make = useMutation({
    mutationFn: makeVault,
    onSuccess: ({ unlocked, code, vault }) => {
      onMade(code);
      queryClient.setQueryData(MINE, vault);
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
      unlock(unlocked);
    },
  });
  return (
    <Plain>
      <h2 className="text-lg font-semibold">{t('vault.setup')}</h2>
      <p className="text-sm">{t('vault.setupNote')}</p>
      <NewPassword
        submitLabel={t('vault.make')}
        pending={make.isPending}
        error={make.isError && <p className="text-sm text-danger">{errorMessage(make.error, t)}</p>}
        onSubmit={(password) => make.mutate(password)}
      />
    </Plain>
  );
}

function Locked({ vault }: { vault: VaultData }) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const { unlock } = useVault();
  const [mode, setMode] = useState<'password' | 'code'>(vault.handed ? 'code' : 'password');
  const [renewing, setRenewing] = useState<Unlocked | null>(null);
  const [restart, setRestart] = useState(false);
  const renew = useMutation({
    mutationFn: (password: string) => setPassword(renewing!, password),
    onSuccess: (changed) => {
      queryClient.setQueryData(MINE, changed);
      unlock(renewing!);
    },
  });
  const restarting = useMutation({
    mutationFn: () => deleteJson('/api/vault'),
    onSuccess: () => {
      queryClient.setQueryData(MINE, null);
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
    },
  });

  if (renewing) {
    return (
      <Plain>
        <h2 className="text-lg font-semibold">{t('vault.password.set')}</h2>
        <p className="text-sm">{t('vault.password.afterCode')}</p>
        <NewPassword
          submitLabel={t('vault.password.set')}
          pending={renew.isPending}
          error={
            renew.isError && <p className="text-sm text-danger">{errorMessage(renew.error, t)}</p>
          }
          onSubmit={(password) => renew.mutate(password)}
        />
      </Plain>
    );
  }

  return (
    <Plain>
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <Lock size={18} aria-hidden />
        {t('vault.locked')}
      </h2>
      {vault.handed && <p className="rounded bg-panel p-3 text-sm">{t('vault.handed')}</p>}
      <UnlockForm
        key={mode}
        vault={vault}
        mode={mode}
        onOpened={(unlocked, how) => (how === 'code' ? setRenewing(unlocked) : unlock(unlocked))}
      />
      <button
        type="button"
        onClick={() => {
          setMode(mode === 'code' ? 'password' : 'code');
        }}
        className="self-start text-sm text-accent hover:underline"
      >
        {t(mode === 'code' ? 'vault.withPassword' : 'vault.forgot')}
      </button>
      {vault.recovered && (
        <p className="text-sm text-muted">
          {t('vault.recoveredBy')}: {vault.recovered.by?.name ?? t('log.formerUser')},{' '}
          {formatDate(vault.recovered.at)}
        </p>
      )}
      <p className="text-sm text-muted">
        {t(vault.recovery ? 'vault.recoverable' : 'vault.unrecoverable')}
      </p>
      {mode === 'code' && (
        <button
          type="button"
          onClick={() => setRestart(true)}
          className="self-start text-sm text-danger hover:underline"
        >
          {t('vault.restart')}
        </button>
      )}
      {restarting.isError && (
        <p className="text-sm text-danger">{errorMessage(restarting.error, t)}</p>
      )}
      {restart && (
        <ConfirmDialog
          heading={t('vault.restartTitle')}
          confirmLabel={t('vault.restart')}
          onConfirm={() => restarting.mutate()}
          onClose={() => setRestart(false)}
        >
          {t('vault.restartWarning')}
        </ConfirmDialog>
      )}
    </Plain>
  );
}

type Dialog =
  | { type: 'item'; item?: Opened; kind: Kind; into: Collection }
  | { type: 'move'; items: Opened[] }
  | { type: 'purge'; items: Opened[] }
  | { type: 'import' | 'export' | 'log' | 'rename' | 'delete' }
  | { type: 'newCollection' | 'settings' | 'newFolder' | 'renameFolder' | 'deleteFolder' | 'sort' };

function VaultOpen({
  vault,
  unlocked,
  fresh,
  onFreshSeen,
}: {
  vault: VaultData;
  unlocked: Unlocked;
  fresh: string | null;
  onFreshSeen: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const params = useParams();
  const { lock } = useVault();
  const [search] = useSearchParams();
  const collections = useCollections();
  const current = collections.data?.find((each) => each.id === params.collection);
  const folders = useOpenedFolders(unlocked, current);
  const opened = useOpenedItems(unlocked, current);
  const ai = useAi();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [members, setMembers] = useState(false);
  const close = () => setDialog(null);
  const enrol = useMutation({
    mutationFn: () => enrolled(unlocked, vault),
    onSuccess: (changed) => changed && queryClient.setQueryData(MINE, changed),
    onError: () => void queryClient.invalidateQueries({ queryKey: MINE }),
  });
  const due = Boolean(vault.recovery && !vault.escrowed);
  const recoveryKey = vault.recovery?.public_key;
  useEffect(() => {
    if (due) enrol.mutate();
  }, [due, recoveryKey]);
  const removal = useMutation({
    mutationFn: (collection: Collection) => deleteJson(`/api/vault/collections/${collection.id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
      navigate('/vault');
    },
  });
  const folderRemoval = useMutation({
    mutationFn: (gone: Folder) => deleteJson(`/api/vault/folders/${gone.id}`),
    onSuccess: (_, gone) => {
      void queryClient.invalidateQueries({ queryKey: OPENED });
      navigate(`/vault/${params.collection}${gone.parent ? `?folder=${gone.parent}` : ''}`);
    },
  });

  if (collections.isPending || collections.isError) {
    return (
      <Plain>
        {collections.isError ? (
          <p className="text-danger">{errorMessage(collections.error, t)}</p>
        ) : (
          <Loading />
        )}
      </Plain>
    );
  }
  const all = collections.data;
  const personal = all.find((each) => each.kind === 'personal')!;
  if (!params.collection) return <Navigate to={`/vault/${personal.id}`} replace />;
  const trash = params.collection === 'trash';
  const collection = all.find((each) => each.id === params.collection);
  if (!trash && !collection) return <Navigate to="/vault" replace />;
  const into = collection?.key && covers(collection.role, 'edit') ? collection : personal;
  const shared = collection && collection.kind !== 'personal';
  const own = collection?.role === 'own';
  const editable = Boolean(collection?.key && covers(collection.role, 'edit'));
  const listed = folders.data ?? [];
  const folderId = search.get('folder');
  const folder = folderId ? listed.find((each) => each.id === folderId) : undefined;
  if (folderId && folders.isSuccess && !folder)
    return <Navigate to={`/vault/${params.collection}`} replace />;
  const unfiled = opened.data?.filter((item) => item.folder === null) ?? [];

  const more = collection && (
    <>
      {shared && (
        <MenuItem icon={Share2} label={t('vault.members')} onSelect={() => setMembers(true)} />
      )}
      {shared && own && (
        <MenuItem
          icon={ScrollText}
          label={t('log.title')}
          onSelect={() => setDialog({ type: 'log' })}
        />
      )}
      <MenuItem
        icon={StickyNote}
        label={t('vault.newNote')}
        disabled={!editable}
        onSelect={() => setDialog({ type: 'item', kind: 'note', into: collection })}
      />
      <MenuItem
        icon={FileKey2}
        label={t('vault.newMailKey')}
        disabled={!editable}
        onSelect={() => setDialog({ type: 'item', kind: 'mailkey', into: collection })}
      />
      <MenuItem
        icon={FolderPlus}
        label={t('create.folder')}
        disabled={!editable}
        onSelect={() => setDialog({ type: 'newFolder' })}
      />
      {folder && (
        <>
          <MenuItem
            icon={Pencil}
            label={t('vault.renameFolder')}
            disabled={!editable}
            onSelect={() => setDialog({ type: 'renameFolder' })}
          />
          <MenuItem
            icon={Trash2}
            label={t('vault.deleteFolder')}
            disabled={!editable}
            onSelect={() => setDialog({ type: 'deleteFolder' })}
          />
        </>
      )}
      <MenuSeparator />
      <MenuItem
        icon={FolderTree}
        label={t('vault.sort')}
        disabled={!editable || !ai.data || unfiled.length === 0}
        hint={
          ai.data === false
            ? t('ai.off')
            : opened.isSuccess && unfiled.length === 0
              ? t('vault.sortNothing')
              : undefined
        }
        onSelect={() => setDialog({ type: 'sort' })}
      />
      <MenuItem
        icon={Upload}
        label={t('vault.import')}
        disabled={!editable}
        onSelect={() => setDialog({ type: 'import' })}
      />
      <MenuItem
        icon={Download}
        label={t('vault.export')}
        disabled={!collection.key || !own}
        onSelect={() => setDialog({ type: 'export' })}
      />
      {collection.kind === 'shared' && own && (
        <>
          <MenuSeparator />
          <MenuItem
            icon={Pencil}
            label={t('tree.rename')}
            onSelect={() => setDialog({ type: 'rename' })}
          />
          <MenuItem
            icon={Trash2}
            label={t('vault.deleteCollection')}
            onSelect={() => setDialog({ type: 'delete' })}
          />
        </>
      )}
    </>
  );
  return (
    <Frame
      title={
        trash
          ? t('trash.title')
          : [
              collection!.kind === 'personal' ? t('vault.mine') : collection!.name,
              ...pathOf(folder?.id ?? null, listed),
            ].join(' / ')
      }
      folders={false}
      side={
        <Side
          collections={all}
          here={params.collection}
          folders={collection?.key ? listed : undefined}
          folder={folder?.id}
          items={opened.data}
          onNewCollection={() => setDialog({ type: 'newCollection' })}
          onLock={lock}
          onSettings={() => setDialog({ type: 'settings' })}
          menu={more}
        />
      }
      primary={
        <PrimaryAction
          icon={Plus}
          label={t('vault.newItem')}
          onClick={() => setDialog({ type: 'item', kind: 'login', into })}
        />
      }
      more={more}
      panel={
        members &&
        shared && (
          <MembersPanel
            collection={collection}
            unlocked={unlocked}
            onClose={() => setMembers(false)}
          />
        )
      }
    >
      {enrol.isError && (
        <p className="mb-2 text-sm text-danger">
          {t('vault.enrolFailed')}: {errorMessage(enrol.error, t)}
        </p>
      )}
      {removal.isError && (
        <p className="mb-2 text-sm text-danger">{errorMessage(removal.error, t)}</p>
      )}
      {folderRemoval.isError && (
        <p className="mb-2 text-sm text-danger">{errorMessage(folderRemoval.error, t)}</p>
      )}
      {trash ? (
        <Trash
          collections={all}
          unlocked={unlocked}
          onPurge={(items) => setDialog({ type: 'purge', items })}
        />
      ) : collection!.key ? (
        <Items
          key={`${collection!.id} ${folder?.id}`}
          collection={collection!}
          collections={all}
          unlocked={unlocked}
          here={params.item}
          folder={folder?.id}
          folders={listed}
          onEdit={(item) =>
            setDialog({ type: 'item', item, kind: item.secret.kind, into: collection! })
          }
          onMove={(items) => setDialog({ type: 'move', items })}
        />
      ) : (
        <Pending collection={collection!} unlocked={unlocked} />
      )}
      {fresh && (
        <Modal heading={t('vault.code')} onClose={onFreshSeen}>
          <CodeShown code={fresh} note={t('vault.codeNote')} />
          <div className="flex justify-end">
            <button type="button" onClick={onFreshSeen} className={primaryButton}>
              {t('vault.codeKept')}
            </button>
          </div>
        </Modal>
      )}
      {dialog?.type === 'item' && (
        <ItemDialog
          collection={dialog.into}
          unlocked={unlocked}
          item={dialog.item}
          kind={dialog.kind}
          folder={dialog.into.id === collection?.id ? folder?.id : undefined}
          onDone={(id) => {
            close();
            const kept = dialog.into.id === collection?.id && folder;
            navigate(`/vault/${dialog.into.id}/${id}${kept ? `?folder=${folder.id}` : ''}`);
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'move' && (
        <MoveDialog
          items={dialog.items}
          collections={all}
          unlocked={unlocked}
          onDone={(target, into) => {
            close();
            if (dialog.items.length === 1)
              navigate(`/vault/${target}/${dialog.items[0].id}${into ? `?folder=${into}` : ''}`);
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'purge' && <PurgeDialog items={dialog.items} onClose={close} />}
      {dialog?.type === 'import' && collection && (
        <ImportDialog collection={collection} unlocked={unlocked} onClose={close} />
      )}
      {dialog?.type === 'export' && collection && (
        <ExportDialog collection={collection} unlocked={unlocked} onClose={close} />
      )}
      {dialog?.type === 'log' && collection && (
        <LogDialog collection={collection} unlocked={unlocked} onClose={close} />
      )}
      {dialog?.type === 'rename' && collection && (
        <NameDialog
          heading={t('tree.rename')}
          submitLabel={t('tree.save')}
          initial={collection.name}
          onSubmit={(name) => patchJson(`/api/vault/collections/${collection.id}`, { name })}
          onDone={() => {
            void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
            close();
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'delete' && collection && (
        <ConfirmDialog
          heading={t('vault.deleteCollectionTitle')}
          confirmLabel={t('vault.deleteCollection')}
          onConfirm={() => removal.mutate(collection)}
          onClose={close}
        >
          <strong>{collection.name}</strong> {t('vault.deleteCollectionWarning')}
        </ConfirmDialog>
      )}
      {dialog?.type === 'newCollection' && (
        <NameDialog<Collection>
          heading={t('vault.newCollection')}
          submitLabel={t('tree.create')}
          note={t('vault.newCollectionNote')}
          onSubmit={async (name) =>
            postJson<Collection>('/api/vault/collections', {
              name,
              key: toBase64(await sealTo(unlocked.pair.publicKey, random(32))),
            })
          }
          onDone={(made) => {
            void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
            close();
            navigate(`/vault/${made.id}`);
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'settings' && (
        <SettingsDialog vault={vault} unlocked={unlocked} onClose={close} />
      )}
      {dialog?.type === 'newFolder' && collection && (
        <NameDialog<string>
          heading={t('create.folder')}
          submitLabel={t('tree.create')}
          onSubmit={async (name) => {
            const key = await collectionKey(unlocked, collection.key!);
            const made = { id: crypto.randomUUID(), parent: folder?.id ?? null, name };
            await postJson(`/api/vault/collections/${collection.id}/folders`, {
              folders: await sealedFolders(key, [made]),
            });
            await queryClient.invalidateQueries({
              queryKey: [...OPENED, unlocked.epoch, collection.id, 'folders'],
            });
            return made.id;
          }}
          onDone={(id) => {
            close();
            navigate(`/vault/${collection.id}?folder=${id}`);
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'renameFolder' && collection && folder && (
        <NameDialog
          heading={t('vault.renameFolder')}
          submitLabel={t('tree.save')}
          initial={folder.name}
          onSubmit={async (name) => {
            const key = await collectionKey(unlocked, collection.key!);
            return patchJson(`/api/vault/folders/${folder.id}`, {
              name: await sealJson(key, name),
            });
          }}
          onDone={() => {
            void queryClient.invalidateQueries({ queryKey: OPENED });
            close();
          }}
          onClose={close}
        />
      )}
      {dialog?.type === 'deleteFolder' && folder && (
        <ConfirmDialog
          heading={t('vault.deleteFolderTitle')}
          confirmLabel={t('vault.deleteFolder')}
          onConfirm={() => folderRemoval.mutate(folder)}
          onClose={close}
        >
          <strong>{folder.name}</strong> {t('vault.deleteFolderWarning')}
        </ConfirmDialog>
      )}
      {dialog?.type === 'sort' && collection && (
        <SortDialog
          collection={collection}
          unlocked={unlocked}
          items={unfiled}
          folders={listed}
          onDone={() => {
            close();
            navigate(`/vault/${collection.id}`);
          }}
          onClose={close}
        />
      )}
    </Frame>
  );
}

function CollectionLink({
  collection,
  here,
  ...press
}: { collection: Collection; here?: string } & ReturnType<typeof useMenuPress>) {
  const { t, formatNumber } = useI18n();
  return (
    <Link
      {...press}
      to={`/vault/${collection.id}`}
      aria-current={collection.id === here ? 'page' : undefined}
      className={sideRow}
    >
      <span className="min-w-0 flex-1 truncate">
        {collection.kind === 'personal' ? t('vault.mine') : collection.name}
      </span>
      {!collection.key && (
        <Clock size={14} role="img" aria-label={t('vault.pending')} className="shrink-0" />
      )}
      {!!collection.waiting && (
        <span
          title={t('vault.waiting')}
          className="rounded-full bg-accent px-1.5 text-xs font-semibold text-on-accent tabular-nums"
        >
          {formatNumber(collection.waiting)}
        </span>
      )}
      {collection.key && (
        <span className="text-xs font-normal text-muted tabular-nums">
          {formatNumber(collection.items)}
        </span>
      )}
    </Link>
  );
}

function Side({
  collections,
  here,
  folders,
  folder,
  items,
  onNewCollection,
  onLock,
  onSettings,
  menu,
}: {
  collections: Collection[];
  here?: string;
  /** The open collection's folders, which the side lists under it. */
  folders?: Folder[];
  folder?: string;
  items?: Opened[];
  onNewCollection: () => void;
  onLock: () => void;
  onSettings: () => void;
  /** What the open collection and folder offer, for the row a menu was asked of once it is open. */
  menu: ReactNode;
}) {
  const { t, language, formatNumber } = useI18n();
  const press = useMenuPress();
  const navigate = useNavigate();
  const collator = useMemo(() => new Intl.Collator(language), [language]);
  const of = (kind: Collection['kind']) => collections.filter((each) => each.kind === kind);
  const heading = 'px-2 text-xs font-semibold text-muted uppercase';
  const counts = counted(folders ?? [], items?.map((item) => item.folder) ?? []);
  const linked = (collection: Collection) => (
    <Fragment key={collection.id}>
      <ContextMenuArea items={menu} onOpen={() => navigate(`/vault/${collection.id}`)}>
        <CollectionLink {...press} collection={collection} here={folder ? undefined : here} />
      </ContextMenuArea>
      {collection.id === here &&
        laidOut(folders ?? [], collator.compare).map(({ folder: each, depth }) => (
          <ContextMenuArea
            key={each.id}
            items={menu}
            onOpen={() => navigate(`/vault/${collection.id}?folder=${each.id}`)}
          >
            <Link
              {...press}
              to={`/vault/${collection.id}?folder=${each.id}`}
              aria-current={each.id === folder ? 'page' : undefined}
              style={{ paddingLeft: `${1.25 + depth}rem` }}
              className={sideRow}
            >
              <FolderClosed size={16} aria-hidden className="shrink-0" />
              <span className="min-w-0 flex-1 truncate">{each.name}</span>
              {items && (
                <span className="text-xs font-normal text-muted tabular-nums">
                  {formatNumber(counts.get(each.id) ?? 0)}
                </span>
              )}
            </Link>
          </ContextMenuArea>
        ))}
    </Fragment>
  );
  return (
    <nav aria-label={t('vault.title')} className="flex h-full flex-col gap-3">
      <div className="flex flex-col gap-0.5">{of('personal').map(linked)}</div>
      <section aria-label={t('vault.shared')} className="flex flex-col gap-0.5">
        <div className="flex items-center gap-1">
          <h2 className={`${heading} flex-1`}>{t('vault.shared')}</h2>
          <button
            type="button"
            aria-label={t('vault.newCollection')}
            title={t('vault.newCollection')}
            onClick={onNewCollection}
            className={iconButton}
          >
            <Plus size={14} aria-hidden />
          </button>
        </div>
        {of('shared').map(linked)}
      </section>
      {of('company').length > 0 && (
        <section aria-label={t('tree.company')} className="flex flex-col gap-0.5">
          <h2 className={heading}>{t('tree.company')}</h2>
          {of('company').map(linked)}
        </section>
      )}
      <div className="flex flex-col gap-0.5">
        <Link
          to="/vault/trash"
          aria-current={here === 'trash' ? 'page' : undefined}
          className={sideRow}
        >
          <Trash2 size={16} aria-hidden />
          {t('trash.title')}
        </Link>
      </div>
      <div className="mt-auto flex flex-col gap-0.5 border-t border-line pt-2">
        <button type="button" onClick={onSettings} className={sideRow}>
          <Settings size={16} aria-hidden />
          {t('vault.settings')}
        </button>
        <button type="button" onClick={onLock} className={sideRow}>
          <Lock size={16} aria-hidden />
          {t('vault.lock')}
        </button>
      </div>
    </nav>
  );
}

/** A collection whose key the user does not hold yet: they wait for an owner to confirm them,
    or, as the first owner of a company collection, make its key. */
function Pending({ collection, unlocked }: { collection: Collection; unlocked: Unlocked }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const me = useSession().data?.user;
  const first = useMutation({
    mutationFn: async () =>
      postJson(`/api/vault/collections/${collection.id}/keys`, {
        keys: [
          {
            user: me!.id,
            sealed: toBase64(await sealTo(unlocked.pair.publicKey, random(32))),
          },
        ],
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: COLLECTIONS }),
  });
  if (collection.keyless && collection.role === 'own') {
    return (
      <div className="flex max-w-md flex-col gap-3">
        <p className="text-sm">{t('vault.keyless')}</p>
        {first.isError && <p className="text-sm text-danger">{errorMessage(first.error, t)}</p>}
        <button
          type="button"
          disabled={first.isPending}
          onClick={() => first.mutate()}
          className={`${primaryButton} self-start`}
        >
          <KeyRound size={16} aria-hidden />
          {t('vault.firstKey')}
        </button>
      </div>
    );
  }
  return (
    <p className="flex max-w-md items-center gap-2 text-sm text-muted">
      <Clock size={16} aria-hidden />
      {t('vault.pendingNote')}
    </p>
  );
}

function matches(item: Opened, query: string): boolean {
  const { name, username, urls, notes } = item.secret;
  return [name, username, ...urls, notes].some((text) => text.toLocaleLowerCase().includes(query));
}

function Items({
  collection,
  collections,
  unlocked,
  here,
  folder,
  folders,
  onEdit,
  onMove,
}: {
  collection: Collection;
  collections: Collection[];
  unlocked: Unlocked;
  here?: string;
  folder?: string;
  folders: Folder[];
  onEdit: (item: Opened) => void;
  onMove: (items: Opened[]) => void;
}) {
  const { t, language, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const { search } = useLocation();
  const opened = useOpenedItems(unlocked, collection);
  const [query, setQuery] = useState('');
  const [list, setList, listStyle] = useWidth(ITEMS);
  const collator = useMemo(() => new Intl.Collator(language), [language]);
  const wanted = query.trim().toLocaleLowerCase();
  const at = folder ?? null;
  const shown = (opened.data ?? [])
    .filter((item) => (wanted ? matches(item, wanted) : item.folder === at))
    .sort((a, b) => collator.compare(a.secret.name, b.secret.name));
  const choice = useChoice(shown.map((each) => each.id));
  const toTrash = useMutation({
    mutationFn: (chosen: Opened[]) =>
      Promise.all(chosen.map((item) => deleteJson(`/api/vault/items/${item.id}`))),
    onSettled: () => {
      choice.choose([]);
      void queryClient.invalidateQueries({ queryKey: OPENED });
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
    },
  });
  if (opened.isPending) return <Loading />;
  if (opened.isError) return <p className="text-danger">{errorMessage(opened.error, t)}</p>;
  const inside = wanted
    ? []
    : folders.filter((each) => each.parent === at).sort((a, b) => collator.compare(a.name, b.name));
  const counts = counted(
    folders,
    opened.data.map((item) => item.folder),
  );
  const item = here ? opened.data.find((each) => each.id === here) : undefined;
  if (here && !item && !opened.isFetching)
    return <Navigate to={`/vault/${collection.id}${search}`} replace />;
  const editable = covers(collection.role, 'edit');
  const movable =
    editable &&
    (folders.length > 0 ||
      collections.some(
        (each) => each.id !== collection.id && each.key && covers(each.role, 'edit'),
      ));
  const chosen = shown.filter((each) => choice.has(each.id));
  const many = chosen.length;
  const actionsOf = (on: Opened[]): RowAction[] => [
    {
      icon: FolderInput,
      label: t('tree.move'),
      disabled: !movable,
      onSelect: () => onMove(on),
    },
    {
      icon: Trash2,
      label: t('tree.toTrash'),
      disabled: !editable || toTrash.isPending,
      onSelect: () => toTrash.mutate(on),
    },
  ];
  const row =
    'flex min-w-0 items-center gap-3 rounded px-2 py-2 hover:bg-hover aria-[current=page]:bg-selected';

  return (
    <div style={listStyle} className="flex h-full min-h-0">
      <div
        className={`flex min-w-0 flex-1 flex-col gap-2 lg:w-(--items) lg:max-w-[calc(100%-20rem)] lg:flex-none ${item ? 'hidden lg:flex' : ''}`}
        onKeyDown={(event) =>
          choice.onKeyDown(event, () => {
            if (editable) toTrash.mutate(chosen);
          })
        }
      >
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('vault.search')}
          aria-label={t('vault.search')}
          className={field}
        />
        {many > 0 && (
          <ChoiceBar all={choice.all}>
            {editable && <ActionButtons actions={actionsOf(chosen)} />}
          </ChoiceBar>
        )}
        {toTrash.isError && <p className="text-sm text-danger">{errorMessage(toTrash.error, t)}</p>}
        {opened.data.length === 0 && folders.length === 0 ? (
          <p className="text-sm text-muted">{t('vault.empty')}</p>
        ) : shown.length === 0 && inside.length === 0 ? (
          <p className="text-sm text-muted">{t(wanted ? 'vault.noMatch' : 'vault.folderEmpty')}</p>
        ) : (
          <ul className="flex min-h-0 flex-col gap-0.5 overflow-y-auto">
            {inside.map((each) => (
              <li key={each.id}>
                <Link to={`/vault/${collection.id}?folder=${each.id}`} className={row}>
                  <FolderClosed size={18} aria-hidden className="shrink-0 text-muted" />
                  <span className="min-w-0 flex-1 truncate text-sm">{each.name}</span>
                  <span className="text-xs text-muted tabular-nums">
                    {formatNumber(counts.get(each.id) ?? 0)}
                  </span>
                </Link>
              </li>
            ))}
            {shown.map((each) => {
              const Icon = KIND_ICONS[each.secret.kind];
              const kept = choice.has(each.id);
              return (
                <ContextMenuArea
                  key={each.id}
                  items={<ActionItems actions={actionsOf(kept ? chosen : [each])} />}
                >
                  <li
                    className={`flex min-w-0 items-center rounded select-none [-webkit-touch-callout:none] ${kept ? 'bg-selected' : ''}`}
                  >
                    {many > 0 && (
                      <ChoiceBox
                        checked={kept}
                        onToggle={(range) => choice.toggle(each.id, range)}
                        className="ml-2"
                      />
                    )}
                    <Link
                      {...choice.opener(each.id)}
                      to={`/vault/${collection.id}/${each.id}${search}`}
                      aria-current={each.id === here ? 'page' : undefined}
                      className={`${row} flex-1`}
                    >
                      <Icon size={18} aria-hidden className="shrink-0 text-muted" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm">{each.secret.name}</span>
                        <span className="block truncate text-xs text-muted">
                          {[
                            each.secret.kind === 'note'
                              ? t('vault.kind.note')
                              : each.secret.username || hostOf(each.secret.urls[0] ?? ''),
                            wanted && pathOf(each.folder, folders).join(' / '),
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                      </span>
                      {each.attachments.length > 0 && (
                        <Paperclip size={14} aria-hidden className="shrink-0 text-muted" />
                      )}
                    </Link>
                  </li>
                </ContextMenuArea>
              );
            })}
          </ul>
        )}
      </div>
      <Splitter column={ITEMS} width={list} onWidth={setList} className="hidden w-6 lg:flex" />
      {item && (
        <Detail
          key={item.id}
          item={item}
          collection={collection}
          movable={movable}
          onEdit={() => onEdit(item)}
          onMove={() => onMove([item])}
        />
      )}
    </div>
  );
}

function MoveDialog({
  items,
  collections,
  unlocked,
  onDone,
  onClose,
}: {
  items: Opened[];
  collections: Collection[];
  unlocked: Unlocked;
  onDone: (collection: string, folder: string | null) => void;
  onClose: () => void;
}) {
  const { t, language, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const collator = useMemo(() => new Intl.Collator(language), [language]);
  const targets = collections.filter((each) => each.key && covers(each.role, 'edit'));
  const places = useQuery({
    queryKey: [...OPENED, unlocked.epoch, 'places'],
    queryFn: () =>
      Promise.all(
        targets.map(async (collection) => ({
          collection,
          folders: await openedFolders(unlocked, collection),
        })),
      ),
  });
  const [first] = items;
  const options = (places.data ?? [])
    .flatMap(({ collection, folders }) => {
      const name = collection.kind === 'personal' ? t('vault.mine') : collection.name;
      return [
        { value: `${collection.id}/`, label: name },
        ...laidOut(folders, collator.compare).map(({ folder }) => ({
          value: `${collection.id}/${folder.id}`,
          label: [name, ...pathOf(folder.id, folders)].join(' / '),
        })),
      ];
    })
    .filter(
      ({ value }) => items.length > 1 || value !== `${first.collection}/${first.folder ?? ''}`,
    );
  const [target, setTarget] = useState<string | null>(null);
  const chosen = target ?? options[0]?.value ?? '';
  const [to, into = ''] = chosen.split('/');
  const leaving = items.filter((each) => each.collection !== to);
  const move = useMutation({
    mutationFn: async () => {
      const folder = into || null;
      const staying = items.filter((each) => each.collection === to);
      if (staying.length)
        await patchJson(`/api/vault/collections/${to}/items`, {
          folders: Object.fromEntries(staying.map((each) => [each.id, folder])),
        });
      if (leaving.length) {
        const key = await collectionKey(unlocked, targets.find((each) => each.id === to)!.key!);
        await Promise.all(
          leaving.map(async (each) =>
            patchJson(`/api/vault/items/${each.id}`, {
              collection: to,
              key: toBase64(await seal(key, each.key)),
              folder,
            }),
          ),
        );
      }
      return folder;
    },
    onSuccess: (folder) => {
      void queryClient.invalidateQueries({ queryKey: OPENED });
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
      onDone(to, folder);
    },
  });
  const failure = places.error ?? move.error;

  function submit(event: FormEvent) {
    event.preventDefault();
    move.mutate();
  }

  return (
    <Modal
      heading={`${t('tree.move')}: ${items.length === 1 ? first.secret.name : formatNumber(items.length)}`}
      onClose={onClose}
    >
      {places.isPending ? (
        <Loading />
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('vault.moveTo')}
            <select
              value={chosen}
              onChange={(event) => setTarget(event.target.value)}
              className={field}
            >
              {options.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {leaving.length > 0 && <p className="text-sm text-muted">{t('vault.moveNote')}</p>}
          {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
          <div className="flex justify-end gap-2">
            <Cancel />
            <button type="submit" disabled={move.isPending || !chosen} className={primaryButton}>
              {t('tree.moveHere')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

function Trash({
  collections,
  unlocked,
  onPurge,
}: {
  collections: Collection[];
  unlocked: Unlocked;
  onPurge: (items: Opened[]) => void;
}) {
  const { t, formatDate } = useI18n();
  const queryClient = useQueryClient();
  const trashed = useOpenedTrash(unlocked, collections);
  const items = trashed.data ?? [];
  const choice = useChoice(items.map((item) => item.id));
  const restore = useMutation({
    mutationFn: (chosen: Opened[]) =>
      postJson('/api/vault/trash/restore', { items: chosen.map((item) => item.id) }),
    onSuccess: () => {
      choice.choose([]);
      void queryClient.invalidateQueries({ queryKey: OPENED });
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
    },
  });
  if (trashed.isPending) return <Loading />;
  if (trashed.isError) return <p className="text-danger">{errorMessage(trashed.error, t)}</p>;
  if (items.length === 0) return <p className="text-muted">{t('trash.empty')}</p>;
  const named = new Map(collections.map((each) => [each.id, each]));
  const owned = (chosen: Opened[]) =>
    chosen.every((item) => named.get(item.collection)?.role === 'own');
  const actionsOf = (chosen: Opened[]): RowAction[] => [
    {
      icon: RotateCcw,
      label: t('trash.restore'),
      disabled: restore.isPending,
      onSelect: () => restore.mutate(chosen),
    },
    {
      icon: Trash2,
      label: t('trash.purge'),
      disabled: !owned(chosen),
      onSelect: () => onPurge(chosen),
    },
  ];
  const chosen = items.filter((item) => choice.has(item.id));
  return (
    <div
      className="flex w-full max-w-3xl flex-col gap-2"
      onKeyDown={(event) =>
        choice.onKeyDown(event, () => {
          if (owned(chosen)) onPurge(chosen);
        })
      }
    >
      {restore.isError && <p className="text-sm text-danger">{errorMessage(restore.error, t)}</p>}
      <div className="flex flex-col">
        {choice.many > 0 && (
          <ChoiceBar all={choice.all}>
            <ActionButtons actions={actionsOf(chosen)} />
          </ChoiceBar>
        )}
        <ul aria-label={t('trash.title')} className="flex flex-col">
          {items.map((item) => {
            const from = named.get(item.collection);
            const Icon = KIND_ICONS[item.secret.kind];
            const picked = choice.has(item.id);
            return (
              <ContextMenuArea
                key={item.id}
                items={<ActionItems actions={actionsOf(picked ? chosen : [item])} />}
              >
                <li
                  className={`flex items-center gap-3 border-b border-line px-3 py-1.5 select-none [-webkit-touch-callout:none] ${picked ? 'bg-selected' : 'hover:bg-hover'}`}
                >
                  {choice.many > 0 && (
                    <ChoiceBox
                      checked={picked}
                      onToggle={(range) => choice.toggle(item.id, range)}
                    />
                  )}
                  <button
                    type="button"
                    {...choice.opener(item.id)}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                  >
                    <Icon size={18} aria-hidden className="shrink-0 text-muted" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm">{item.secret.name}</span>
                      <span className="block truncate text-xs text-muted">
                        {from?.kind === 'personal' ? t('vault.mine') : from?.name} ·{' '}
                        {formatDate(item.trashed_at!)}
                      </span>
                    </span>
                  </button>
                  {choice.many === 0 && <ActionButtons actions={actionsOf([item])} />}
                </li>
              </ContextMenuArea>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

function PurgeDialog({ items, onClose }: { items: Opened[]; onClose: () => void }) {
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const purge = useMutation({
    mutationFn: () => postJson('/api/vault/trash/purge', { items: items.map((item) => item.id) }),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: OPENED }),
  });
  return (
    <ConfirmDialog
      heading={t('trash.purgeTitle')}
      confirmLabel={t('trash.purge')}
      onConfirm={() => purge.mutate()}
      onClose={onClose}
    >
      {items.length === 1 ? (
        <>
          <strong>{items[0].secret.name}</strong> {t('vault.purgeWarning')}
        </>
      ) : (
        `${t('explorer.selected')}: ${formatNumber(items.length)}. ${t('vault.purgeChosen')}`
      )}
    </ConfirmDialog>
  );
}

function ImportDialog({
  collection,
  unlocked,
  onClose,
}: {
  collection: Collection;
  unlocked: Unlocked;
  onClose: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const [read, setRead] = useState<Imported | null>(null);
  const [unreadable, setUnreadable] = useState<Unreadable['reason'] | null>(null);
  const [chosen, setChosen] = useState('');
  const load = async (file: File | undefined) => {
    setRead(null);
    setUnreadable(null);
    if (!file) return;
    setChosen(file.name);
    try {
      setRead(imported(await file.text()));
    } catch (error) {
      if (!(error instanceof Unreadable)) throw error;
      setUnreadable(error.reason);
    }
  };
  const save = useMutation({
    mutationFn: async (items: Filed[]) => {
      const key = await collectionKey(unlocked, collection.key!);
      const { made, ends } = planned(
        items.map(({ folder }) => folder),
        await openedFolders(unlocked, collection),
      );
      for (let at = 0; at < made.length; at += BATCH)
        await postJson(`/api/vault/collections/${collection.id}/folders`, {
          folders: await sealedFolders(key, made.slice(at, at + BATCH)),
        });
      for (let at = 0; at < items.length; at += BATCH) {
        const sealed = await Promise.all(
          items.slice(at, at + BATCH).map(async ({ secret }, index) => ({
            ...(await sealSecret(key, secret)),
            folder: ends[at + index],
          })),
        );
        await postJson(`/api/vault/collections/${collection.id}/items`, { items: sealed });
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: OPENED });
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
    },
    onSuccess: onClose,
  });
  const picker = useFilePicker((files) => void load(files[0]), {
    accept: '.csv,.json,text/csv,application/json',
    multiple: false,
  });

  return (
    <Modal heading={t('vault.import')} onClose={onClose}>
      <p className="text-sm">{t('vault.importNote')}</p>
      <div className="flex min-w-0 items-center gap-2">
        {picker.element}
        <button type="button" onClick={picker.open} className={`${button} shrink-0`}>
          <FileUp size={16} aria-hidden />
          {t('vault.importChoose')}
        </button>
        {chosen && <span className="truncate text-sm text-muted">{chosen}</span>}
      </div>
      {unreadable && <p className="text-sm text-danger">{t(`vault.unreadable.${unreadable}`)}</p>}
      {read && (
        <p className="text-sm">
          {t(`vault.format.${read.format}`)} · {t('vault.importItems')}:{' '}
          {formatNumber(read.items.length)}
          {read.skipped > 0 && ` · ${t('vault.importSkipped')}: ${formatNumber(read.skipped)}`}
        </p>
      )}
      {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
      <div className="flex justify-end gap-2">
        <Cancel />
        <button
          type="button"
          disabled={!read?.items.length || save.isPending}
          onClick={() => read && save.mutate(read.items)}
          className={primaryButton}
        >
          <Upload size={16} aria-hidden />
          {t('vault.importDo')}
        </button>
      </div>
    </Modal>
  );
}

function ExportDialog({
  collection,
  unlocked,
  onClose,
}: {
  collection: Collection;
  unlocked: Unlocked;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const name = collection.kind === 'personal' ? t('vault.mine') : collection.name;
  const run = useMutation({
    mutationFn: async () => {
      const [items, folders] = await Promise.all([
        openedItems(unlocked, collection),
        openedFolders(unlocked, collection),
      ]);
      await postJson(`/api/vault/collections/${collection.id}/exported`);
      const text = exported(
        items.map((item) => ({ secret: item.secret, folder: pathOf(item.folder, folders) })),
      );
      saved(new Blob([text], { type: 'application/json' }), `${name}.json`);
    },
    onSuccess: onClose,
  });
  return (
    <Modal heading={`${t('vault.export')}: ${name}`} onClose={onClose}>
      <p className="text-sm">{t('vault.exportWarning')}</p>
      {run.isError && <p className="text-sm text-danger">{errorMessage(run.error, t)}</p>}
      <div className="flex justify-end gap-2">
        <Cancel />
        <button
          type="button"
          disabled={run.isPending}
          onClick={() => run.mutate()}
          className={primaryButton}
        >
          <Download size={16} aria-hidden />
          {t('vault.exportDo')}
        </button>
      </div>
    </Modal>
  );
}

interface Proposed {
  name: string;
  items: Opened[];
  /** The items left outside folders, which keep no name. */
  none?: boolean;
}

/** Folders a model proposes for the items outside folders, from only their names and the hosts
    of their sites, which the user lets out each time and reviews before they are applied. */
function SortDialog({
  collection,
  unlocked,
  items,
  folders,
  onDone,
  onClose,
}: {
  collection: Collection;
  unlocked: Unlocked;
  items: Opened[];
  folders: Folder[];
  onDone: () => void;
  onClose: () => void;
}) {
  const { t, language, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const [proposal, setProposal] = useState<Proposed[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const ask = useMutation({
    mutationFn: () =>
      postJson<{ folders: { name: string; entries: number[] }[] }>(
        `/api/vault/collections/${collection.id}/sorting`,
        {
          entries: items.map(({ secret }) => ({
            name: secret.name.slice(0, 200),
            host: hostIn(secret.urls[0] ?? ''),
          })),
          existing: folders.filter((each) => each.parent === null).map((each) => each.name),
          language,
          consent: 'once',
        },
      ),
    onSuccess: ({ folders: given }) => {
      const placed = new Set(given.flatMap((each) => each.entries));
      setProposal([
        ...given.map((each) => ({ name: each.name, items: each.entries.map((at) => items[at]) })),
        { name: '', items: items.filter((_, at) => !placed.has(at)), none: true },
      ]);
    },
  });
  const apply = useMutation({
    mutationFn: async () => {
      const groups = proposal!.filter((group) => !group.none && group.name.trim());
      const { made, ends } = planned(
        groups.map((group) => [group.name]),
        folders,
      );
      const key = await collectionKey(unlocked, collection.key!);
      if (made.length)
        await postJson(`/api/vault/collections/${collection.id}/folders`, {
          folders: await sealedFolders(key, made),
        });
      const filed = groups.flatMap((group, at) => group.items.map((item) => [item.id, ends[at]]));
      if (filed.length)
        await patchJson(`/api/vault/collections/${collection.id}/items`, {
          folders: Object.fromEntries(filed),
        });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: OPENED });
      onDone();
    },
  });
  const renamed = (at: number, name: string) =>
    setProposal(proposal!.map((group, index) => (index === at ? { ...group, name } : group)));
  const moved = (item: Opened, from: number, to: number) =>
    setProposal(
      proposal!.map((group, index) =>
        index === from
          ? { ...group, items: group.items.filter((each) => each !== item) }
          : index === to
            ? { ...group, items: [...group.items, item] }
            : group,
      ),
    );
  const failed =
    ask.error instanceof ApiError && ask.error.code === 'no_answer'
      ? t('vault.sortNoAnswer')
      : ask.error && errorMessage(ask.error, t);

  if (!proposal)
    return (
      <Modal heading={t('vault.sortHeading')} onClose={onClose}>
        <p className="text-sm">{t('vault.sortBody')}</p>
        <p className="text-sm">
          {t('vault.sortCount')}: {formatNumber(items.length)}
        </p>
        <p className="text-sm text-muted">{t('vault.sortKept')}</p>
        {ask.isPending && (
          <p role="status" className="text-sm text-muted">
            {t('vault.sorting')}
          </p>
        )}
        {failed && <p className="text-sm text-danger">{failed}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="button"
            disabled={ask.isPending}
            onClick={() => ask.mutate()}
            className={primaryButton}
          >
            <FolderTree size={16} aria-hidden />
            {t('vault.sortDo')}
          </button>
        </div>
      </Modal>
    );
  return (
    <Modal heading={t('vault.sortHeading')} onClose={onClose}>
      <p className="text-sm">{t('vault.sortReview')}</p>
      <ul className="flex max-h-[55vh] flex-col gap-1 overflow-y-auto">
        {proposal.map(
          (group, at) =>
            (!group.none || group.items.length > 0) && (
              <li key={at} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-expanded={open === at}
                    aria-label={t('vault.sortItems')}
                    title={t('vault.sortItems')}
                    onClick={() => setOpen(open === at ? null : at)}
                    className={iconButton}
                  >
                    {open === at ? (
                      <ChevronDown size={16} aria-hidden />
                    ) : (
                      <ChevronRight size={16} aria-hidden />
                    )}
                  </button>
                  {group.none ? (
                    <span className="min-w-0 flex-1 px-1 text-sm text-muted">
                      {t('vault.sortNone')}
                    </span>
                  ) : (
                    <input
                      value={group.name}
                      onChange={(event) => renamed(at, event.target.value)}
                      aria-label={t('vault.sortName')}
                      className={`${field} min-w-0 flex-1`}
                    />
                  )}
                  <span className="w-10 shrink-0 text-right text-xs text-muted tabular-nums">
                    {formatNumber(group.items.length)}
                  </span>
                </div>
                {open === at && (
                  <ul className="ml-9 flex flex-col gap-0.5">
                    {group.items.map((item) => (
                      <li key={item.id} className="flex min-w-0 items-center gap-2 text-sm">
                        <span className="min-w-0 flex-1 truncate">{item.secret.name}</span>
                        <select
                          value={at}
                          onChange={(event) => moved(item, at, Number(event.target.value))}
                          aria-label={`${t('tree.move')}: ${item.secret.name}`}
                          className={`${field} w-40 shrink-0 py-0.5 text-xs`}
                        >
                          {proposal.map((other, index) => (
                            <option key={index} value={index}>
                              {other.none ? t('vault.sortNone') : other.name}
                            </option>
                          ))}
                        </select>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ),
        )}
      </ul>
      <p className="text-xs text-muted">{t('vault.sortMerge')}</p>
      {apply.isError && <p className="text-sm text-danger">{errorMessage(apply.error, t)}</p>}
      <div className="flex justify-end gap-2">
        <Cancel />
        <button
          type="button"
          disabled={apply.isPending}
          onClick={() => apply.mutate()}
          className={primaryButton}
        >
          {t('vault.sortApply')}
        </button>
      </div>
    </Modal>
  );
}
