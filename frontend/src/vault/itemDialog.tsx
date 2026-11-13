import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Dices } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { patchJson, postJson } from '../api';
import { Cancel, Modal } from '../dialogs';
import { useI18n } from '../i18n';
import type { MessageKey } from '../i18n/hr';
import { published } from '../mailKeys';
import { button, field, iconButton, primaryButton } from '../styles';
import { errorMessage } from '../tree';
import { MailKeyFields, MailKeyShown } from './mailKey';
import { KIND_ICONS, RevealButton } from './parts';
import {
  blank,
  changed,
  generated,
  RECIPE,
  sealJson,
  sealSecret,
  type Kind,
  type Opened,
  type Recipe,
  type Secret,
} from './secret';
import { collectionKey, COLLECTIONS, OPENED, type Collection, type Unlocked } from './state';
import { parseTotp } from './totp';

const NEW_KIND: Record<Kind, MessageKey> = {
  login: 'vault.newItem',
  note: 'vault.newNote',
  mailkey: 'vault.newMailKey',
};

function Generator({ onUse }: { onUse: (password: string) => void }) {
  const { t } = useI18n();
  const [recipe, setRecipe] = useState<Recipe>(RECIPE);
  const [made, setMade] = useState(() => generated(RECIPE));
  const remade = (next: Recipe) => {
    setRecipe(next);
    setMade(generated(next));
  };
  const flag = (name: 'upper' | 'digits' | 'symbols') => (
    <label className="flex items-center gap-1.5">
      <input
        type="checkbox"
        checked={recipe[name]}
        onChange={(event) => remade({ ...recipe, [name]: event.target.checked })}
      />
      {t(`vault.generator.${name}`)}
    </label>
  );
  return (
    <div className="flex flex-col gap-2 rounded border border-line bg-panel p-3 text-sm">
      <p className="font-mono break-all">{made}</p>
      <label className="flex items-center gap-2">
        {t('vault.generator.length')}
        <input
          type="range"
          min={8}
          max={64}
          value={recipe.length}
          onChange={(event) => remade({ ...recipe, length: Number(event.target.value) })}
          className="flex-1"
        />
        <span className="w-6 text-right tabular-nums">{recipe.length}</span>
      </label>
      <div className="flex flex-wrap gap-3">
        {flag('upper')}
        {flag('digits')}
        {flag('symbols')}
      </div>
      <div className="flex gap-2">
        <button type="button" onClick={() => setMade(generated(recipe))} className={button}>
          <Dices size={16} aria-hidden />
          {t('vault.generator.again')}
        </button>
        <button type="button" onClick={() => onUse(made)} className={primaryButton}>
          {t('vault.generator.use')}
        </button>
      </div>
    </div>
  );
}

export function ItemDialog({
  collection,
  unlocked,
  item,
  kind,
  folder,
  onDone,
  onClose,
}: {
  collection: Collection;
  unlocked: Unlocked;
  item?: Opened;
  kind: Kind;
  /** The folder a new item goes into, none for the top of the collection. */
  folder?: string;
  onDone: (id: string) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [secret, setSecret] = useState<Secret>(() => item?.secret ?? blank(kind));
  const [urls, setUrls] = useState(() => secret.urls.join('\n'));
  const [shown, setShown] = useState(false);
  const [generating, setGenerating] = useState(false);
  const passwordId = useId();
  const set = (change: Partial<Secret>) => setSecret({ ...secret, ...change });
  const badTotp = Boolean(secret.totp.trim()) && !parseTotp(secret.totp);
  const save = useMutation({
    mutationFn: async () => {
      const next = changed(item?.secret, {
        ...secret,
        mailkey: secret.kind === 'mailkey' ? secret.mailkey : undefined,
        totp: secret.totp.trim(),
        urls: urls
          .split('\n')
          .map((url) => url.trim())
          .filter(Boolean),
      });
      if (item) {
        await patchJson(`/api/vault/items/${item.id}`, { data: await sealJson(item.key, next) });
        return item.id;
      }
      if (next.mailkey) await published(next.mailkey);
      const key = await collectionKey(unlocked, collection.key!);
      const { items } = await postJson<{ items: { id: string }[] }>(
        `/api/vault/collections/${collection.id}/items`,
        { items: [{ ...(await sealSecret(key, next)), folder: folder ?? null }] },
      );
      return items[0].id;
    },
    onSuccess: (id) => {
      void queryClient.invalidateQueries({ queryKey: OPENED });
      void queryClient.invalidateQueries({ queryKey: COLLECTIONS });
      onDone(id);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!badTotp && (secret.kind !== 'mailkey' || secret.mailkey)) save.mutate();
  }

  const heading = item
    ? t('vault.edit')
    : `${t(NEW_KIND[secret.kind])} · ${
        collection.kind === 'personal' ? t('vault.mine') : collection.name
      }`;
  return (
    <Modal heading={heading} wide onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {!item && (
          <div role="radiogroup" aria-label={t('vault.kind')} className="flex gap-2">
            {(['login', 'note', 'mailkey'] as const).map((each) => {
              const Icon = KIND_ICONS[each];
              return (
                <button
                  key={each}
                  type="button"
                  role="radio"
                  aria-checked={secret.kind === each}
                  onClick={() => set({ kind: each })}
                  className={`${button} aria-checked:bg-selected aria-checked:font-semibold`}
                >
                  <Icon size={16} aria-hidden />
                  {t(`vault.kind.${each}`)}
                </button>
              );
            })}
          </div>
        )}
        <label className="flex flex-col gap-1 text-sm">
          {t('tree.name')}
          <input
            required
            autoFocus
            maxLength={200}
            value={secret.name}
            onChange={(event) => set({ name: event.target.value })}
            className={field}
          />
        </label>
        {secret.kind === 'mailkey' &&
          (secret.mailkey ? (
            <MailKeyShown mailkey={secret.mailkey} />
          ) : (
            <MailKeyFields
              onKey={(mailkey) =>
                set({ mailkey, name: secret.name || mailkey.addresses[0] || mailkey.fingerprint })
              }
            />
          ))}
        {secret.kind === 'login' && (
          <>
            <label className="flex flex-col gap-1 text-sm">
              {t('vault.username')}
              <input
                autoComplete="off"
                spellCheck={false}
                value={secret.username}
                onChange={(event) => set({ username: event.target.value })}
                className={field}
              />
            </label>
            <div className="flex flex-col gap-1 text-sm">
              <label htmlFor={passwordId}>{t('vault.password')}</label>
              <div className="flex items-center gap-1">
                <input
                  id={passwordId}
                  type={shown ? 'text' : 'password'}
                  autoComplete="new-password"
                  spellCheck={false}
                  value={secret.password}
                  onChange={(event) => set({ password: event.target.value })}
                  className={`${field} min-w-0 flex-1 font-mono`}
                />
                <RevealButton shown={shown} onToggle={() => setShown(!shown)} />
                <button
                  type="button"
                  aria-label={t('vault.generate')}
                  title={t('vault.generate')}
                  aria-expanded={generating}
                  onClick={() => setGenerating(!generating)}
                  className={iconButton}
                >
                  <Dices size={16} aria-hidden />
                </button>
              </div>
              {generating && (
                <Generator
                  onUse={(password) => {
                    set({ password });
                    setShown(true);
                    setGenerating(false);
                  }}
                />
              )}
            </div>
            <label className="flex flex-col gap-1 text-sm">
              {t('vault.totp')}
              <input
                autoComplete="off"
                spellCheck={false}
                value={secret.totp}
                placeholder="otpauth://totp/…"
                onChange={(event) => set({ totp: event.target.value })}
                aria-invalid={badTotp}
                className={`${field} font-mono`}
              />
              <span className={`text-xs ${badTotp ? 'text-danger' : 'text-muted'}`}>
                {t(badTotp ? 'vault.totpInvalid' : 'vault.totpNote')}
              </span>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              {t('vault.urls')}
              <textarea
                rows={2}
                spellCheck={false}
                value={urls}
                onChange={(event) => setUrls(event.target.value)}
                className={field}
              />
            </label>
          </>
        )}
        <label className="flex flex-col gap-1 text-sm">
          {t('vault.notes')}
          <textarea
            rows={secret.kind === 'note' ? 8 : 3}
            value={secret.notes}
            onChange={(event) => set({ notes: event.target.value })}
            className={field}
          />
        </label>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="submit"
            disabled={save.isPending || badTotp || (secret.kind === 'mailkey' && !secret.mailkey)}
            className={primaryButton}
          >
            {t(item ? 'tree.save' : 'tree.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}
