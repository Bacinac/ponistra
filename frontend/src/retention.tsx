import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, ShieldCheck, Trash2, Unlock } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router';
import { deleteJson, getJson, patchJson, postJson } from './api';
import { useSession } from './auth';
import { Cancel, ConfirmDialog, FolderPickDialog, Modal, Picker } from './dialogs';
import { Loaded, PrimaryAction } from './frame';
import { useI18n } from './i18n';
import { AdminFrame } from './settings';
import { button, field, iconButton, primaryButton } from './styles';
import { errorMessage, useNode } from './tree';

const RETENTION = ['retention'];
const KINDS = ['documents', 'files', 'mail', 'chat'] as const;
type What = (typeof KINDS)[number];
const IN_FOLDERS: readonly What[] = ['documents', 'files'];

interface Folder {
  id: string;
  title: string;
}

interface Person {
  id: number;
  name: string;
  email: string;
}

interface Rule {
  id: number;
  what: What;
  folder: Folder | null;
  keep_days: number | null;
  remove_days: number | null;
}

interface Hold {
  id: number;
  name: string;
  person: Person | null;
  folder: Folder | null;
  created_by: Person | null;
  created_at: string;
}

interface Removal {
  at: string;
  documents: number;
  files: number;
  mail: number;
  chat: number;
}

type Dialog =
  | { type: 'rule'; rule?: Rule }
  | { type: 'dropRule'; rule: Rule }
  | { type: 'hold' }
  | { type: 'release'; hold: Hold };

function useRetentionChange<V>(mutationFn: (variables: V) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: RETENTION }),
  });
}

const days = (value: string) => (value === '' ? null : Number(value));

function FolderChoice({ folder, onPick }: { folder: string | null; onPick: (id: string) => void }) {
  const { t } = useI18n();
  const [picking, setPicking] = useState(false);
  const chosen = useNode(folder);
  return (
    <div className="flex flex-col gap-1 text-sm">
      {t('retention.folder')}
      <button type="button" className={`${button} text-left`} onClick={() => setPicking(true)}>
        {folder ? (chosen.data?.node.title ?? '…') : t('retention.chooseFolder')}
      </button>
      {picking && (
        <FolderPickDialog
          heading={t('retention.chooseFolder')}
          confirmLabel={t('retention.pick')}
          onPick={(id) => {
            if (id) onPick(id);
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      )}
    </div>
  );
}

function RuleDialog({ rule, onClose }: { rule?: Rule; onClose: () => void }) {
  const { t } = useI18n();
  const [what, setWhat] = useState<What>(rule?.what ?? 'documents');
  const [everywhere, setEverywhere] = useState(true);
  const [folder, setFolder] = useState<string | null>(null);
  const [keep, setKeep] = useState(rule?.keep_days?.toString() ?? '');
  const [remove, setRemove] = useState(rule?.remove_days?.toString() ?? '');
  const narrowed = IN_FOLDERS.includes(what) && !everywhere;
  const save = useRetentionChange(() => {
    const terms = { keep_days: days(keep), remove_days: days(remove) };
    return rule
      ? patchJson(`/api/retention/rules/${rule.id}`, terms)
      : postJson('/api/retention/rules', { what, folder: narrowed ? folder : null, ...terms });
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: onClose });
  }

  return (
    <Modal heading={t(rule ? 'retention.editRule' : 'retention.newRule')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        {rule ? (
          <p className="text-sm">
            {t(`retention.what.${rule.what}`)}
            {rule.folder && `: ${rule.folder.title}`}
          </p>
        ) : (
          <>
            <Picker
              label={t('retention.what')}
              value={what}
              options={KINDS.map((each) => [each, t(`retention.what.${each}`)] as const)}
              onChange={setWhat}
            />
            {IN_FOLDERS.includes(what) && (
              <>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={everywhere}
                    onChange={(event) => setEverywhere(event.target.checked)}
                  />
                  {t('retention.everywhere')}
                </label>
                {!everywhere && <FolderChoice folder={folder} onPick={setFolder} />}
              </>
            )}
          </>
        )}
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-1 text-sm">
            {t('retention.keepDays')}
            <input
              type="number"
              min={1}
              max={36500}
              value={keep}
              onChange={(event) => setKeep(event.target.value)}
              className={field}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t('retention.removeDays')}
            <input
              type="number"
              min={1}
              max={36500}
              value={remove}
              onChange={(event) => setRemove(event.target.value)}
              className={field}
            />
          </label>
        </div>
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="submit"
            disabled={save.isPending || (keep === '' && remove === '') || (narrowed && !folder)}
            className={primaryButton}
          >
            {t(rule ? 'tree.save' : 'tree.create')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function HoldDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState('');
  const [subject, setSubject] = useState<'person' | 'folder'>('person');
  const [person, setPerson] = useState('');
  const [folder, setFolder] = useState<string | null>(null);
  const people = useQuery({
    queryKey: ['accounts'],
    queryFn: () => getJson<{ users: Person[] }>('/api/users'),
  });
  const save = useRetentionChange(() =>
    postJson('/api/retention/holds', {
      name: name.trim(),
      ...(subject === 'person' ? { person: Number(person) } : { folder }),
    }),
  );
  const chosen = subject === 'person' ? person !== '' : folder !== null;

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: onClose });
  }

  return (
    <Modal heading={t('retention.newHold')} onClose={onClose}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t('retention.holdName')}
          <input
            type="text"
            required
            maxLength={200}
            value={name}
            onChange={(event) => setName(event.target.value)}
            className={field}
          />
        </label>
        <Picker
          label={t('retention.subject')}
          value={subject}
          options={[
            ['person', t('retention.person')],
            ['folder', t('retention.folder')],
          ]}
          onChange={setSubject}
        />
        {subject === 'person' ? (
          <label className="flex flex-col gap-1 text-sm">
            {t('retention.person')}
            <select
              className={field}
              value={person}
              onChange={(event) => setPerson(event.target.value)}
            >
              <option value="" disabled>
                {t('retention.choosePerson')}
              </option>
              {people.data?.users.map((each) => (
                <option key={each.id} value={each.id}>
                  {each.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <FolderChoice folder={folder} onPick={setFolder} />
        )}
        {save.isError && <p className="text-sm text-danger">{errorMessage(save.error, t)}</p>}
        <div className="flex justify-end gap-2">
          <Cancel />
          <button
            type="submit"
            disabled={save.isPending || !name.trim() || !chosen}
            className={primaryButton}
          >
            {t('retention.hold')}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Retention({
  rules,
  holds,
  removals,
}: {
  rules: Rule[];
  holds: Hold[] | undefined;
  removals: Removal[];
}) {
  const { t, formatDate, formatNumber } = useI18n();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const dropRule = useRetentionChange((rule: Rule) =>
    deleteJson(`/api/retention/rules/${rule.id}`),
  );
  const release = useRetentionChange((hold: Hold) => deleteJson(`/api/retention/holds/${hold.id}`));
  const close = () => setDialog(null);
  const cell = 'px-2 py-2 whitespace-nowrap';
  const head = 'px-2 py-2 font-normal';
  const count = (value: number | null) => (value === null ? '–' : formatNumber(value));
  const failure = dropRule.error ?? release.error;
  const ruleName = (rule: Rule) =>
    `${t(`retention.what.${rule.what}`)}: ${rule.folder?.title ?? t('retention.everywhere')}`;
  return (
    <AdminFrame
      title={t('retention.title')}
      primary={
        <PrimaryAction
          icon={Plus}
          label={t('retention.newRule')}
          onClick={() => setDialog({ type: 'rule' })}
        />
      }
    >
      <div className="flex w-full max-w-5xl flex-col gap-6">
        {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
        <section className="flex flex-col gap-2">
          <h2 className="font-semibold">{t('retention.rules')}</h2>
          {rules.length === 0 ? (
            <p className="text-sm text-muted">{t('retention.noRules')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="text-left text-sm text-muted">
                  <tr className="border-b border-line">
                    <th className={head}>{t('retention.what')}</th>
                    <th className={`${head} w-full`}>{t('retention.folder')}</th>
                    <th className={`${head} text-right`}>{t('retention.keepDays')}</th>
                    <th className={`${head} text-right`}>{t('retention.removeDays')}</th>
                    <th className="w-20" />
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule) => (
                    <tr key={rule.id} className="border-b border-line text-sm">
                      <td className={cell}>{t(`retention.what.${rule.what}`)}</td>
                      <td className={`${cell} max-w-0 truncate`}>
                        {rule.folder?.title ?? t('retention.everywhere')}
                      </td>
                      <td className={`${cell} text-right tabular-nums`}>{count(rule.keep_days)}</td>
                      <td className={`${cell} text-right tabular-nums`}>
                        {count(rule.remove_days)}
                      </td>
                      <td className={`${cell} text-right`}>
                        <button
                          type="button"
                          onClick={() => setDialog({ type: 'rule', rule })}
                          aria-label={`${t('retention.editRule')}: ${ruleName(rule)}`}
                          className={iconButton}
                        >
                          <Pencil size={16} aria-hidden />
                        </button>
                        <button
                          type="button"
                          onClick={() => setDialog({ type: 'dropRule', rule })}
                          aria-label={`${t('retention.dropRule')}: ${ruleName(rule)}`}
                          className={iconButton}
                        >
                          <Trash2 size={16} aria-hidden />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        <section className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-semibold">{t('retention.holds')}</h2>
            <button type="button" className={button} onClick={() => setDialog({ type: 'hold' })}>
              <ShieldCheck size={16} aria-hidden className="mr-1 inline" />
              {t('retention.newHold')}
            </button>
          </div>
          {holds === undefined ? null : holds.length === 0 ? (
            <p className="text-sm text-muted">{t('retention.noHolds')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="text-left text-sm text-muted">
                  <tr className="border-b border-line">
                    <th className={`${head} w-full`}>{t('retention.holdName')}</th>
                    <th className={head}>{t('retention.subject')}</th>
                    <th className={head}>{t('retention.since')}</th>
                    <th className="w-12" />
                  </tr>
                </thead>
                <tbody>
                  {holds.map((hold) => (
                    <tr key={hold.id} className="border-b border-line text-sm">
                      <td className={`${cell} max-w-0 truncate`}>{hold.name}</td>
                      <td className={cell}>{hold.person?.name ?? hold.folder?.title}</td>
                      <td className={`${cell} text-muted`}>{formatDate(hold.created_at)}</td>
                      <td className={`${cell} text-right`}>
                        <button
                          type="button"
                          onClick={() => setDialog({ type: 'release', hold })}
                          aria-label={`${t('retention.release')}: ${hold.name}`}
                          className={iconButton}
                        >
                          <Unlock size={16} aria-hidden />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
        {removals.length > 0 && (
          <section className="flex flex-col gap-2">
            <h2 className="font-semibold">{t('retention.removals')}</h2>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead className="text-left text-sm text-muted">
                  <tr className="border-b border-line">
                    <th className={`${head} w-full`}>{t('log.when')}</th>
                    {KINDS.map((each) => (
                      <th key={each} className={`${head} text-right`}>
                        {t(`retention.what.${each}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {removals.map((removal) => (
                    <tr key={removal.at} className="border-b border-line text-sm">
                      <td className={`${cell} text-muted`}>{formatDate(removal.at)}</td>
                      {KINDS.map((each) => (
                        <td key={each} className={`${cell} text-right tabular-nums`}>
                          {formatNumber(removal[each])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
      {dialog?.type === 'rule' && <RuleDialog rule={dialog.rule} onClose={close} />}
      {dialog?.type === 'hold' && <HoldDialog onClose={close} />}
      {dialog?.type === 'dropRule' && (
        <ConfirmDialog
          heading={t('retention.dropRuleTitle')}
          confirmLabel={t('retention.dropRule')}
          onConfirm={() => dropRule.mutate(dialog.rule, { onSuccess: close })}
          onClose={close}
        >
          <strong>{ruleName(dialog.rule)}</strong>
        </ConfirmDialog>
      )}
      {dialog?.type === 'release' && (
        <ConfirmDialog
          heading={t('retention.releaseTitle')}
          confirmLabel={t('retention.release')}
          onConfirm={() => release.mutate(dialog.hold, { onSuccess: close })}
          onClose={close}
        >
          <strong>{dialog.hold.name}</strong>
        </ConfirmDialog>
      )}
    </AdminFrame>
  );
}

export function RetentionPage() {
  const me = useSession().data?.user;
  const rules = useQuery({
    queryKey: [...RETENTION, 'rules'],
    queryFn: () => getJson<{ rules: Rule[]; removals: Removal[] }>('/api/retention/rules'),
    enabled: !!me?.is_admin,
  });
  const holds = useQuery({
    queryKey: [...RETENTION, 'holds'],
    queryFn: () => getJson<{ holds: Hold[] }>('/api/retention/holds'),
    enabled: !!me?.is_admin,
  });
  if (!me?.is_admin) return <Navigate to="/" replace />;
  return (
    <Loaded query={rules}>
      {(data) => (
        <Retention rules={data.rules} holds={holds.data?.holds} removals={data.removals} />
      )}
    </Loaded>
  );
}
