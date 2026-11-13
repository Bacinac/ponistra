import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FolderOpen, Plus, Send } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { ApiError, deleteJson, getJson, postJson, putJson } from './api';
import { Cancel, ConfirmDialog, Labelled, Modal } from './dialogs';
import { useAi } from './editor/runs';
import { Loading } from './frame';
import { useI18n } from './i18n';
import { accountName, useAccounts, type Person } from './mailData';
import { useMessageAction } from './mailTriage';
import { Recipients } from './recipients';
import { button, field, primaryButton } from './styles';
import { codeText, errorMessage, nodeHref } from './tree';
import { day } from './when';

interface Placed {
  id: string;
  title: string;
}

interface CollectionMonth {
  id: number;
  month: string;
  folder: Placed | null;
  table: Placed | null;
  past: boolean;
  asked_at: string | null;
  delivered_at: string | null;
  failed: string;
  kept: number;
  waiting: number;
  passed: number;
  missed: number;
  due_at: string;
}

export interface Collection {
  id: number;
  name: string;
  accounts: number[];
  senders: string[];
  words: string[];
  attached: boolean;
  recognise: boolean;
  since: string;
  folder: Placed | null;
  to: Person[];
  account: number | null;
  day: number;
  hour: number;
  sends: 'draft' | 'send';
  text: string;
  active: boolean;
  error: string;
  months: CollectionMonth[];
}

type Written = Omit<Collection, 'id' | 'folder' | 'error' | 'months'>;

const COLLECTIONS = ['mail', 'collections'];
const DAYS = Array.from({ length: 28 }, (_, at) => at + 1);
const HOURS = Array.from({ length: 24 }, (_, at) => at);

function useCollections() {
  return useQuery({
    queryKey: COLLECTIONS,
    queryFn: () => getJson<{ collections: Collection[] }>('/api/collections'),
  });
}

function listed(text: string): string[] {
  return text
    .split(/[,;\n]/)
    .map((each) => each.trim())
    .filter(Boolean);
}

function fresh(): Written {
  const today = new Date();
  return {
    name: '',
    accounts: [],
    senders: [],
    words: [],
    attached: true,
    recognise: false,
    since: day(new Date(today.getFullYear(), today.getMonth(), 1)),
    to: [],
    account: null,
    day: 1,
    hour: 9,
    sends: 'draft',
    text: '',
    active: true,
  };
}

function consentAsked(error: Error | null): boolean {
  return error instanceof ApiError && error.code === 'consent_needed';
}

function CollectionForm({
  collection,
  onDone,
}: {
  collection: Collection | null;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const accounts = useAccounts().data?.accounts ?? [];
  const ai = useAi().data === true;
  const [given, setGiven] = useState<Written>(collection ?? fresh());
  const [senders, setSenders] = useState(given.senders.join(', '));
  const [words, setWords] = useState(given.words.join(', '));
  const [removing, setRemoving] = useState(false);
  const change = (values: Partial<Written>) => setGiven((before) => ({ ...before, ...values }));
  const save = useMutation({
    mutationFn: (consent: boolean) => {
      const sent = {
        ...given,
        senders: listed(senders),
        words: listed(words),
        ...(consent && { consent: 'once' }),
      };
      return collection
        ? putJson<Collection>(`/api/collections/${collection.id}`, sent)
        : postJson<Collection>('/api/collections', sent);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: COLLECTIONS });
      onDone();
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteJson(`/api/collections/${collection?.id}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: COLLECTIONS });
      onDone();
    },
  });
  const failure = consentAsked(save.error) ? remove.error : (save.error ?? remove.error);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(false);
  };
  const chosen = new Set(given.accounts);
  const ready =
    given.name.trim() !== '' &&
    given.since !== '' &&
    (given.sends === 'draft' || given.to.length > 0);
  return (
    <form onSubmit={submit} className="flex max-w-xl flex-col gap-3">
      <Labelled label={t('collections.name')}>
        {(id) => (
          <input
            id={id}
            value={given.name}
            maxLength={150}
            required
            onChange={(event) => change({ name: event.target.value })}
            className={field}
          />
        )}
      </Labelled>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 text-sm font-semibold">{t('collections.takes')}</legend>
        {accounts.length > 1 && (
          <div role="group" aria-label={t('collections.accounts')} className="flex flex-col gap-1">
            <span className="text-sm text-muted">{t('collections.accounts')}</span>
            {accounts.map((account) => (
              <label key={account.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={chosen.has(account.id)}
                  onChange={(event) =>
                    change({
                      accounts: event.target.checked
                        ? [...given.accounts, account.id]
                        : given.accounts.filter((each) => each !== account.id),
                    })
                  }
                  className="size-4"
                />
                {accountName(account)}
              </label>
            ))}
          </div>
        )}
        <Labelled label={t('collections.senders')}>
          {(id) => (
            <input
              id={id}
              value={senders}
              placeholder="anthropic.com, racuni@example.com"
              onChange={(event) => setSenders(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <Labelled label={t('collections.words')}>
          {(id) => (
            <input
              id={id}
              value={words}
              placeholder={t('collections.wordsExample')}
              onChange={(event) => setWords(event.target.value)}
              className={field}
            />
          )}
        </Labelled>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={given.attached}
            onChange={(event) => change({ attached: event.target.checked })}
            className="size-4"
          />
          {t('collections.attached')}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={given.recognise}
            disabled={!ai && !given.recognise}
            onChange={(event) => change({ recognise: event.target.checked })}
            className="size-4"
          />
          {t('collections.recognise')}
        </label>
        <Labelled label={t('collections.since')}>
          {(id) => (
            <input
              id={id}
              type="date"
              value={given.since}
              max={day(new Date())}
              required
              onChange={(event) => change({ since: event.target.value })}
              className={field}
            />
          )}
        </Labelled>
      </fieldset>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 text-sm font-semibold">{t('collections.goes')}</legend>
        <Labelled label={t('collections.to')}>
          {(id) => <Recipients id={id} people={given.to} onChange={(to) => change({ to })} />}
        </Labelled>
        {accounts.length > 1 && (
          <Labelled label={t('collections.from')}>
            {(id) => (
              <select
                id={id}
                value={given.account ?? ''}
                onChange={(event) =>
                  change({ account: event.target.value ? Number(event.target.value) : null })
                }
                className={field}
              >
                <option value="">{t('collections.fromDefault')}</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {accountName(account)}
                  </option>
                ))}
              </select>
            )}
          </Labelled>
        )}
        <div className="flex flex-wrap gap-3">
          <Labelled label={t('collections.day')}>
            {(id) => (
              <select
                id={id}
                value={given.day}
                onChange={(event) => change({ day: Number(event.target.value) })}
                className={field}
              >
                {DAYS.map((each) => (
                  <option key={each} value={each}>
                    {each}.
                  </option>
                ))}
              </select>
            )}
          </Labelled>
          <Labelled label={t('collections.hour')}>
            {(id) => (
              <select
                id={id}
                value={given.hour}
                onChange={(event) => change({ hour: Number(event.target.value) })}
                className={field}
              >
                {HOURS.map((each) => (
                  <option key={each} value={each}>
                    {`${String(each).padStart(2, '0')}:00`}
                  </option>
                ))}
              </select>
            )}
          </Labelled>
        </div>
        <div role="radiogroup" aria-label={t('collections.sends')} className="flex flex-col gap-1">
          {(['draft', 'send'] as const).map((each) => (
            <label key={each} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="collection-sends"
                checked={given.sends === each}
                onChange={() => change({ sends: each })}
                className="size-4"
              />
              {t(each === 'draft' ? 'collections.draft' : 'collections.send')}
            </label>
          ))}
        </div>
        <Labelled label={t('collections.text')}>
          {(id) => (
            <textarea
              id={id}
              rows={4}
              value={given.text}
              onChange={(event) => change({ text: event.target.value })}
              className={field}
            />
          )}
        </Labelled>
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={given.active}
          onChange={(event) => change({ active: event.target.checked })}
          className="size-4"
        />
        {t('collections.active')}
      </label>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={!ready || save.isPending} className={primaryButton}>
          {t('tree.save')}
        </button>
        <button type="button" onClick={onDone} className={button}>
          {t('tree.cancel')}
        </button>
        {collection && (
          <button type="button" onClick={() => setRemoving(true)} className={`${button} ml-auto`}>
            {t('collections.remove')}
          </button>
        )}
      </div>
      {consentAsked(save.error) && (
        <Modal heading={t('ai.consent.heading')} onClose={() => save.reset()}>
          <p className="text-sm">{t('collections.consent')}</p>
          <div className="flex flex-wrap justify-end gap-2">
            <Cancel />
            <button type="button" className={primaryButton} onClick={() => save.mutate(true)}>
              {t('collections.consentGive')}
            </button>
          </div>
        </Modal>
      )}
      {removing && (
        <ConfirmDialog
          heading={t('collections.remove')}
          confirmLabel={t('collections.remove')}
          onConfirm={() => remove.mutate()}
          onClose={() => setRemoving(false)}
        >
          {t('collections.removeKeeps')}
        </ConfirmDialog>
      )}
    </form>
  );
}

function MonthRow({ collection, month }: { collection: Collection; month: CollectionMonth }) {
  const { t, formatDate, formatMonth, formatNumber } = useI18n();
  const queryClient = useQueryClient();
  const [again, setAgain] = useState(false);
  const send = useMutation({
    mutationFn: () => postJson(`/api/collections/${collection.id}/months/${month.id}/send`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: COLLECTIONS }),
  });
  const state = month.failed
    ? codeText(month.failed, t)
    : month.asked_at
      ? t('collections.sending')
      : month.delivered_at
        ? t(collection.sends === 'send' ? 'collections.sentAt' : 'collections.draftedAt').replace(
            '{when}',
            formatDate(month.delivered_at),
          )
        : month.past
          ? t('collections.notSent')
          : t('collections.dueAt').replace('{when}', formatDate(month.due_at));
  const counted = (
    [
      ['collections.kept', month.kept],
      ['collections.waiting', month.waiting],
      ['collections.passed', month.passed],
      ['collections.missed', month.missed],
    ] as const
  ).filter(([, count]) => count > 0);
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line py-2 text-sm">
      <span className="w-32 font-medium">{formatMonth(month.month)}</span>
      <span className="text-muted">
        {counted.map(([label, count]) => `${t(label)}: ${formatNumber(count)}`).join(' · ')}
      </span>
      <span className={month.failed ? 'text-danger' : 'text-muted'}>{state}</span>
      <span className="ml-auto flex gap-1">
        {month.folder && (
          <Link
            to={nodeHref({ ...month.folder, kind: 'folder' })}
            className={button}
            aria-label={`${t('collections.openFolder')} ${formatMonth(month.month)}`}
          >
            <FolderOpen className="size-4" />
          </Link>
        )}
        {!month.asked_at && (
          <button
            type="button"
            disabled={send.isPending}
            onClick={() => (month.delivered_at ? setAgain(true) : send.mutate())}
            className={button}
          >
            <Send className="size-4" />
            {t(month.delivered_at ? 'collections.sendAgain' : 'collections.sendNow')}
          </button>
        )}
      </span>
      {send.isError && <p className="w-full text-danger">{errorMessage(send.error, t)}</p>}
      {again && (
        <ConfirmDialog
          heading={t('collections.sendAgain')}
          confirmLabel={t('collections.sendAgain')}
          onConfirm={() => send.mutate()}
          onClose={() => setAgain(false)}
        >
          {formatMonth(month.month)}
        </ConfirmDialog>
      )}
    </li>
  );
}

function CollectionView({ collection, onEdit }: { collection: Collection; onEdit: () => void }) {
  const { t } = useI18n();
  const named = [...collection.senders, ...collection.words].join(', ');
  return (
    <section className="flex flex-col gap-2 rounded border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{collection.name}</h3>
        {!collection.active && (
          <span className="text-sm text-muted">{t('collections.paused')}</span>
        )}
        <span className="ml-auto flex gap-1">
          {collection.folder && (
            <Link to={nodeHref({ ...collection.folder, kind: 'folder' })} className={button}>
              <FolderOpen className="size-4" />
              {t('collections.openFolder')}
            </Link>
          )}
          <button type="button" onClick={onEdit} className={button}>
            {t('collections.edit')}
          </button>
        </span>
      </div>
      {named && <p className="truncate text-sm text-muted">{named}</p>}
      {collection.error && <p className="text-sm text-danger">{codeText(collection.error, t)}</p>}
      {collection.months.length > 0 && (
        <ul className="flex flex-col">
          {collection.months.map((month) => (
            <MonthRow key={month.id} collection={collection} month={month} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function Collections() {
  const { t } = useI18n();
  const found = useCollections();
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  if (!found.data)
    return found.isError ? (
      <p className="text-sm text-danger">{errorMessage(found.error, t)}</p>
    ) : (
      <Loading />
    );
  const done = () => setEditing(null);
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      {editing === 'new' ? (
        <CollectionForm collection={null} onDone={done} />
      ) : (
        <button
          type="button"
          onClick={() => setEditing('new')}
          className={`${primaryButton} self-start`}
        >
          <Plus className="size-4" />
          {t('collections.new')}
        </button>
      )}
      {found.data.collections.map((each) =>
        editing === each.id ? (
          <CollectionForm key={each.id} collection={each} onDone={done} />
        ) : (
          <CollectionView key={each.id} collection={each} onEdit={() => setEditing(each.id)} />
        ),
      )}
    </div>
  );
}

/** Takes the messages chosen into one of the user's collections. */
export function GatherDialog({
  messages,
  onDone,
  onClose,
}: {
  messages: number[];
  onDone: () => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const found = useCollections();
  const gather = useMessageAction();
  const [into, setInto] = useState<number | null>(null);
  const collections = found.data?.collections ?? [];
  const chosen = into ?? collections[0]?.id ?? null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (chosen === null) return;
    gather.mutate(
      { action: 'mail.gather', messages, parameters: { collection: chosen } },
      { onSuccess: onDone },
    );
  };
  return (
    <Modal heading={t('collections.addTitle')} onClose={onClose}>
      {!found.data ? (
        <Loading />
      ) : collections.length === 0 ? (
        <div className="flex flex-col gap-3 text-sm">
          <p>{t('collections.none')}</p>
          <div className="flex justify-end gap-2">
            <Cancel />
            <Link to="/settings/collections" className={primaryButton}>
              {t('collections.new')}
            </Link>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Labelled label={t('collections.into')}>
            {(id) => (
              <select
                id={id}
                value={chosen ?? ''}
                onChange={(event) => setInto(Number(event.target.value))}
                className={field}
              >
                {collections.map((each) => (
                  <option key={each.id} value={each.id}>
                    {each.name}
                  </option>
                ))}
              </select>
            )}
          </Labelled>
          {gather.isError && <p className="text-sm text-danger">{errorMessage(gather.error, t)}</p>}
          <div className="flex justify-end gap-2">
            <Cancel />
            <button type="submit" disabled={gather.isPending} className={primaryButton}>
              {t('collections.addConfirm')}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
