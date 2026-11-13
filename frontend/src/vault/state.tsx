import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getJson, patchJson, postJson, putJson } from '../api';
import type { Role } from '../tree';
import {
  bytesText,
  fromBase64,
  fromCode,
  fromPassword,
  fromPrf,
  newCode,
  newKdf,
  newPair,
  open,
  openSealed,
  random,
  seal,
  sealTo,
  spelledCode,
  textBytes,
  toBase64,
  toBase64Url,
  type Bytes,
  type Kdf,
  type Pair,
} from './crypto';
import type { Folder } from './folders';
import { openItem, openJson, type Opened, type Person, type SealedItem } from './secret';

export interface VaultData {
  public_key: string;
  private_key: string;
  kdf: Kdf;
  by_password: string;
  by_code: string;
  code: string;
  /** The vault key wrapped with a one-time code an administrator prepared. */
  handed: string | null;
  unlocks: { passkey: number; name: string; credential: string; salt: string; wrapped: string }[];
  recovery: { public_key: string } | null;
  escrowed: boolean;
  recovered: { by: Person | null; at: string } | null;
}

export interface Collection {
  id: string;
  kind: 'personal' | 'shared' | 'company';
  name: string;
  role: Role;
  /** The collection's key sealed to the user; null until an owner confirms them. */
  key: string | null;
  items: number;
  /** Whether nobody holds a key to it yet, as a company collection before its first owner. */
  keyless?: boolean;
  /** How many members wait for an owner to confirm them, for its owners. */
  waiting?: number;
}

export interface Unlocked {
  /** Which unlocking this is, so that what one opened is never served to the next. */
  epoch: number;
  vaultKey: Bytes;
  pair: Pair;
  keys: Map<string, Promise<Bytes>>;
}

/** What the browser opened lives under this key only while the vault is unlocked. */
export const OPENED = ['vault', 'opened'];
export const MINE = ['vault', 'mine'];
export const COLLECTIONS = ['vault', 'collections'];

/** The password, code or passkey was not the one the vault was sealed for. */
export class Wrong extends Error {}

/** The browser or the passkey gave no PRF result, so the passkey cannot unlock a vault. */
export class NoPrf extends Error {}

const IDLE = 'ponistra.vault.idle';
export const IDLE_MINUTES = [5, 15, 60] as const;
export type Idle = (typeof IDLE_MINUTES)[number];

export function idleMinutes(): Idle {
  try {
    const kept = Number(localStorage.getItem(IDLE));
    return IDLE_MINUTES.find((minutes) => minutes === kept) ?? 15;
  } catch {
    return 15;
  }
}

export function keepIdle(minutes: Idle): void {
  try {
    localStorage.setItem(IDLE, String(minutes));
  } catch {
    // The choice holds for this tab only.
  }
}

let epochs = 0;

function unlockedWith(vaultKey: Bytes, pair: Pair): Unlocked {
  return { epoch: ++epochs, vaultKey, pair, keys: new Map() };
}

async function opening(vault: VaultData, key: Bytes, wrapped: string): Promise<Unlocked> {
  let vaultKey: Bytes;
  try {
    vaultKey = await open(key, fromBase64(wrapped));
  } catch {
    throw new Wrong();
  }
  const privateKey = await open(vaultKey, fromBase64(vault.private_key));
  return unlockedWith(vaultKey, { publicKey: fromBase64(vault.public_key), privateKey });
}

export async function withPassword(vault: VaultData, password: string): Promise<Unlocked> {
  return opening(vault, await fromPassword(password, vault.kdf), vault.by_password);
}

/** The vault opened with the user's recovery code, or the one an administrator handed them. */
export async function withCode(vault: VaultData, typed: string): Promise<Unlocked> {
  const spelled = spelledCode(typed);
  if (!spelled) throw new Wrong();
  const key = await fromCode(spelled);
  for (const wrapped of [vault.by_code, vault.handed]) {
    if (!wrapped) continue;
    try {
      return await opening(vault, key, wrapped);
    } catch (error) {
      if (!(error instanceof Wrong)) throw error;
    }
  }
  throw new Wrong();
}

async function prf(
  allow: Bytes[],
  salts: Record<string, { first: Bytes }> | Bytes,
): Promise<{ credential: Bytes; output: Bytes }> {
  const answer = (await navigator.credentials.get({
    publicKey: {
      challenge: random(32),
      rpId: location.hostname,
      userVerification: 'required',
      allowCredentials: allow.map((id) => ({ type: 'public-key', id })),
      extensions: {
        prf: salts instanceof Uint8Array ? { eval: { first: salts } } : { evalByCredential: salts },
      },
    },
  })) as PublicKeyCredential;
  const first = answer.getClientExtensionResults().prf?.results?.first;
  if (!first) throw new NoPrf();
  return {
    credential: new Uint8Array(answer.rawId),
    output: new Uint8Array(first instanceof ArrayBuffer ? first : (first as Bytes)),
  };
}

export async function withPasskey(vault: VaultData): Promise<Unlocked> {
  const salts = Object.fromEntries(
    vault.unlocks.map((unlock) => [
      toBase64Url(fromBase64(unlock.credential)),
      { first: fromBase64(unlock.salt) },
    ]),
  );
  const { credential, output } = await prf(
    vault.unlocks.map((unlock) => fromBase64(unlock.credential)),
    salts,
  );
  const used = vault.unlocks.find((unlock) => unlock.credential === toBase64(credential));
  if (!used) throw new Wrong();
  return opening(vault, await fromPrf(output), used.wrapped);
}

/** One of the user's passkeys, chosen in the browser's own dialog, made to unlock the vault. */
export async function addPasskey(unlocked: Unlocked): Promise<VaultData> {
  const salt = random(32);
  const { credential, output } = await prf([], salt);
  return postJson<VaultData>('/api/vault/unlocks', {
    credential: toBase64(credential),
    salt: toBase64(salt),
    wrapped: toBase64(await seal(await fromPrf(output), unlocked.vaultKey)),
  });
}

async function byPassword(vaultKey: Bytes, password: string) {
  const kdf = newKdf();
  return { kdf, by_password: toBase64(await seal(await fromPassword(password, kdf), vaultKey)) };
}

async function byCode(vaultKey: Bytes) {
  const code = newCode();
  return {
    code,
    fields: {
      by_code: toBase64(await seal(await fromCode(spelledCode(code)!), vaultKey)),
      code: toBase64(await seal(vaultKey, textBytes(code))),
    },
  };
}

/** A new vault: a key pair, a vault key the password and a new recovery code wrap, and the
    user's own collection with a key of its own. */
export async function makeVault(
  password: string,
): Promise<{ unlocked: Unlocked; code: string; vault: VaultData }> {
  const pair = await newPair();
  const vaultKey = random(32);
  const { code, fields } = await byCode(vaultKey);
  const vault = await postJson<VaultData>('/api/vault', {
    public_key: toBase64(pair.publicKey),
    private_key: toBase64(await seal(vaultKey, pair.privateKey)),
    ...(await byPassword(vaultKey, password)),
    ...fields,
    personal: toBase64(await sealTo(pair.publicKey, random(32))),
  });
  return { unlocked: unlockedWith(vaultKey, pair), code, vault };
}

export async function setPassword(unlocked: Unlocked, password: string): Promise<VaultData> {
  return patchJson<VaultData>('/api/vault', await byPassword(unlocked.vaultKey, password));
}

export async function renewCode(unlocked: Unlocked): Promise<{ vault: VaultData; code: string }> {
  const { code, fields } = await byCode(unlocked.vaultKey);
  return { vault: await patchJson<VaultData>('/api/vault', fields), code };
}

export async function shownCode(unlocked: Unlocked, vault: VaultData): Promise<string> {
  return bytesText(await open(unlocked.vaultKey, fromBase64(vault.code)));
}

/** The vault key sealed to the company's recovery key, where the policy holds the vault to it
    and it is not yet. */
export async function enrolled(unlocked: Unlocked, vault: VaultData): Promise<VaultData | null> {
  if (!vault.recovery || vault.escrowed) return null;
  const sealed = await sealTo(fromBase64(vault.recovery.public_key), unlocked.vaultKey);
  return putJson<VaultData>('/api/vault/escrow', {
    public_key: vault.recovery.public_key,
    sealed: toBase64(sealed),
  });
}

/** The collection's key, opened once per unlocking. */
export function collectionKey(unlocked: Unlocked, sealed: string): Promise<Bytes> {
  let found = unlocked.keys.get(sealed);
  if (!found) {
    found = openSealed(unlocked.pair, fromBase64(sealed));
    unlocked.keys.set(sealed, found);
  }
  return found;
}

export function useVaultData() {
  return useQuery({
    queryKey: MINE,
    queryFn: () => getJson<VaultData | null>('/api/vault'),
  });
}

export function useCollections(enabled = true) {
  return useQuery({
    queryKey: COLLECTIONS,
    queryFn: async () =>
      (await getJson<{ collections: Collection[] }>('/api/vault/collections')).collections,
    enabled,
  });
}

/** The collection's items, opened in the browser. */
export async function openedItems(unlocked: Unlocked, collection: Collection): Promise<Opened[]> {
  const key = await collectionKey(unlocked, collection.key!);
  const { items } = await getJson<{ items: SealedItem[] }>(
    `/api/vault/collections/${collection.id}/items`,
  );
  return Promise.all(items.map((item) => openItem(key, item)));
}

/** The collection's folders, their names opened in the browser. */
export async function openedFolders(unlocked: Unlocked, collection: Collection): Promise<Folder[]> {
  const key = await collectionKey(unlocked, collection.key!);
  const { folders } = await getJson<{ folders: Folder[] }>(
    `/api/vault/collections/${collection.id}/folders`,
  );
  return Promise.all(
    folders.map(async (folder) => ({ ...folder, name: await openJson<string>(key, folder.name) })),
  );
}

export function useOpenedFolders(unlocked: Unlocked, collection: Collection | undefined) {
  return useQuery({
    queryKey: [...OPENED, unlocked.epoch, collection?.id, 'folders'],
    queryFn: () => openedFolders(unlocked, collection!),
    enabled: Boolean(collection?.key),
  });
}

export function useOpenedItems(unlocked: Unlocked, collection: Collection | undefined) {
  return useQuery({
    queryKey: [...OPENED, unlocked.epoch, collection?.id],
    queryFn: () => openedItems(unlocked, collection!),
    enabled: Boolean(collection?.key),
  });
}

/** The items in the trash, opened with the keys of the collections they came from. */
export function useOpenedTrash(unlocked: Unlocked, collections: Collection[]) {
  return useQuery({
    queryKey: [...OPENED, unlocked.epoch, 'trash'],
    queryFn: async (): Promise<Opened[]> => {
      const { items } = await getJson<{ items: SealedItem[] }>('/api/vault/trash');
      const sealed = new Map(collections.map((collection) => [collection.id, collection.key]));
      return Promise.all(
        items.flatMap((item) => {
          const key = sealed.get(item.collection);
          return key ? [collectionKey(unlocked, key).then((raw) => openItem(raw, item))] : [];
        }),
      );
    },
  });
}

interface Lock {
  unlocked: Unlocked | null;
  unlock: (unlocked: Unlocked) => void;
  lock: () => void;
}

const VaultContext = createContext<Lock | null>(null);

/** Holds the opened vault while the user works in the app; it locks after the minutes they
    chose without a key or a click. Signing out unmounts it, and the keys go with it. */
export function VaultProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [unlocked, setUnlocked] = useState<Unlocked | null>(null);
  const lock = useCallback(() => {
    setUnlocked(null);
    queryClient.removeQueries({ queryKey: OPENED });
  }, [queryClient]);
  const unlock = useCallback(
    (next: Unlocked) => {
      queryClient.removeQueries({ queryKey: OPENED });
      setUnlocked(next);
    },
    [queryClient],
  );

  useEffect(() => {
    if (!unlocked) return;
    let timer = setTimeout(lock, idleMinutes() * 60_000);
    const touched = () => {
      clearTimeout(timer);
      timer = setTimeout(lock, idleMinutes() * 60_000);
    };
    window.addEventListener('pointerdown', touched, true);
    window.addEventListener('keydown', touched, true);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('pointerdown', touched, true);
      window.removeEventListener('keydown', touched, true);
    };
  }, [unlocked, lock]);

  const value = useMemo(() => ({ unlocked, unlock, lock }), [unlocked, unlock, lock]);
  return <VaultContext value={value}>{children}</VaultContext>;
}

export function useVault(): Lock {
  return use(VaultContext)!;
}
