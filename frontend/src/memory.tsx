import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { getJson, postJson } from './api';
import { Loading } from './frame';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { button, primaryButton } from './styles';
import { codeText, errorMessage, Failure } from './tree';

type FindingKind =
  'orphan' | 'dangling' | 'link' | 'frontmatter' | 'oversize' | 'stale' | 'long' | 'unreadable';

interface Finding {
  file: string;
  kind: FindingKind;
  detail: string;
}

interface Store {
  store: string;
  folder: string | null;
  files: number;
  bytes: number;
  index: { lines: number; bytes: number; tokens: number; cut: number } | null;
  findings: Finding[];
  proposals: number;
  unanalysed: number;
}

type ProposalKind = 'state' | 'path' | 'time' | 'link' | 'index' | 'frontmatter' | 'session';

interface Changed {
  op: ' ' | '-' | '+' | '@';
  text: string;
}

interface Proposal {
  id: number;
  store: string;
  file: string;
  source: 'mechanical' | 'session';
  kind: ProposalKind;
  reason: string | null;
  state: 'open' | 'applied' | 'rejected' | 'stale' | 'reverted';
  removes: boolean;
  creates: boolean;
  created_at: string;
  decided_at: string | null;
  diff?: Changed[];
}

interface Advice {
  id: number;
  title: string;
  reason: string;
  action: 'accept' | 'reject' | 'look';
  proposals: number[];
}

interface Overview {
  root: string | null;
  stores: Store[];
  advice: Advice[];
  proposals: Proposal[];
  history: Proposal[];
  nightly: boolean;
}

interface Asked {
  state: 'sent' | 'taken' | 'done' | 'failed';
  error: string | null;
}

const MEMORY = ['memory', 'overview'];
const WAITING = ['memory', 'waiting'];

const KINDS: Record<ProposalKind, MessageKey> = {
  state: 'memory.kind.state',
  path: 'memory.kind.path',
  time: 'memory.kind.time',
  link: 'memory.kind.link',
  index: 'memory.kind.index',
  frontmatter: 'memory.kind.frontmatter',
  session: 'memory.kind.session',
};

const ADVICE: Record<Advice['action'], MessageKey> = {
  accept: 'memory.advice.accept',
  reject: 'memory.advice.reject',
  look: 'memory.advice.look',
};

const FINDINGS: Record<FindingKind, MessageKey> = {
  orphan: 'memory.finding.orphan',
  dangling: 'memory.finding.dangling',
  link: 'memory.finding.link',
  frontmatter: 'memory.finding.frontmatter',
  oversize: 'memory.finding.oversize',
  stale: 'memory.finding.stale',
  long: 'memory.finding.long',
  unreadable: 'memory.finding.unreadable',
};

const CHANGED: Record<Changed['op'], string> = {
  ' ': 'text-muted',
  '-': 'text-deleted line-through',
  '+': 'text-inserted',
  '@': 'text-muted',
};

/** A store's name as the page of code names its project, by its folder. */
export type Names = ReadonlyMap<string, string>;

function useStoreName(overview: Overview, names: Names) {
  const { t } = useI18n();
  return (store: string) => {
    const folder = overview.stores.find((each) => each.store === store)?.folder ?? null;
    if (!folder) return store;
    if (folder === overview.root) return t('workspace.general');
    const own = folder.split('/').pop() ?? store;
    return names.get(folder) ?? own.charAt(0).toUpperCase() + own.slice(1);
  };
}

function useRefresh() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ['memory'] });
}

/** How many proposals wait, beside the Memory tab of the page of code. */
export function useMemoryWaiting(): number {
  const query = useQuery({
    queryKey: WAITING,
    queryFn: () => getJson<{ count: number }>('/api/memory/waiting'),
    retry: false,
  });
  return query.data?.count ?? 0;
}

function Diff({ lines }: { lines: Changed[] }) {
  return (
    <pre className="mt-2 max-h-96 overflow-auto rounded bg-panel p-2 font-mono text-xs leading-5 whitespace-pre-wrap">
      {lines.map((line, at) =>
        line.op === '@' ? (
          <hr key={at} className="my-1 border-line" />
        ) : (
          <div key={at} className={CHANGED[line.op]}>
            <span aria-hidden className="select-none">
              {line.op}{' '}
            </span>
            {line.text || ' '}
          </div>
        ),
      )}
    </pre>
  );
}

function ProposalCard({ proposal, name }: { proposal: Proposal; name: string }) {
  const { t } = useI18n();
  const refresh = useRefresh();
  const decided = useMutation({
    mutationFn: (text: 'yes' | 'no') =>
      postJson<Proposal>(`/api/memory/proposals/${proposal.id}`, { text }),
    onSettled: refresh,
  });
  return (
    <li className="rounded border border-line p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-sm font-medium">{proposal.file}</span>
        <span className="text-xs text-muted">{name}</span>
        <span className="text-xs text-muted">{t(KINDS[proposal.kind])}</span>
        {proposal.removes && <span className="text-xs text-danger">{t('memory.removes')}</span>}
        {proposal.creates && <span className="text-xs text-muted">{t('memory.creates')}</span>}
      </div>
      {proposal.reason && <p className="mt-1 text-sm">{proposal.reason}</p>}
      {proposal.diff && <Diff lines={proposal.diff} />}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={decided.isPending}
          onClick={() => decided.mutate('yes')}
          className={primaryButton}
        >
          {t('memory.accept')}
        </button>
        <button
          type="button"
          disabled={decided.isPending}
          onClick={() => decided.mutate('no')}
          className={button}
        >
          {t('memory.reject')}
        </button>
        {decided.isError && (
          <span className="text-sm text-danger">{errorMessage(decided.error, t)}</span>
        )}
      </div>
    </li>
  );
}

function AdviceGroup({
  group,
  proposals,
  name,
}: {
  group: Advice;
  proposals: Proposal[];
  name: (store: string) => string;
}) {
  const { t, formatNumber } = useI18n();
  const refresh = useRefresh();
  const [open, setOpen] = useState(group.action === 'look');
  const followed = useMutation({
    mutationFn: (text: 'yes' | 'no') =>
      postJson<{ applied: number; rejected: number; stale: number }>(
        `/api/memory/advice/${group.id}`,
        { text },
      ),
    onSettled: refresh,
  });
  const count = formatNumber(group.proposals.length);
  const stale = followed.data?.stale ?? 0;
  return (
    <li className="rounded border border-line p-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-sm font-medium">{group.title}</span>
        <span className="text-xs text-muted">{t(ADVICE[group.action])}</span>
      </div>
      <p className="mt-1 text-sm">{group.reason}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={followed.isPending}
          onClick={() => followed.mutate('yes')}
          className={group.action === 'accept' ? primaryButton : button}
        >
          {t('memory.acceptAll').replace('{count}', count)}
        </button>
        <button
          type="button"
          disabled={followed.isPending}
          onClick={() => followed.mutate('no')}
          className={group.action === 'reject' ? primaryButton : button}
        >
          {t('memory.rejectAll').replace('{count}', count)}
        </button>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1 text-sm text-muted"
        >
          {open ? <ChevronDown size={14} aria-hidden /> : <ChevronRight size={14} aria-hidden />}
          {t('memory.showProposals')}
        </button>
        {stale > 0 && (
          <span className="text-sm text-danger">
            {t('memory.staleAfter').replace('{count}', formatNumber(stale))}
          </span>
        )}
        {followed.isError && (
          <span className="text-sm text-danger">{errorMessage(followed.error, t)}</span>
        )}
      </div>
      {open && (
        <ul className="mt-3 flex flex-col gap-3">
          {proposals.map((proposal) => (
            <ProposalCard key={proposal.id} proposal={proposal} name={name(proposal.store)} />
          ))}
        </ul>
      )}
    </li>
  );
}

function Ask({
  path,
  sent,
  label,
  primary,
  disabled,
}: {
  path: string;
  sent: object;
  label: MessageKey;
  primary: boolean;
  disabled: boolean;
}) {
  const { t } = useI18n();
  const asked = useMutation({
    mutationFn: () => postJson<Asked>(path, sent),
  });
  const failed = asked.data?.state === 'failed' ? asked.data.error : null;
  return (
    <span className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={disabled || asked.isPending}
        onClick={() => asked.mutate()}
        className={primary ? primaryButton : button}
      >
        {t(label)}
      </button>
      {asked.isSuccess && !failed && (
        <span className="text-sm text-muted">{t('memory.analysing')}</span>
      )}
      {failed && <span className="text-sm text-danger">{codeText(failed, t)}</span>}
      {asked.isError && <span className="text-sm text-danger">{errorMessage(asked.error, t)}</span>}
    </span>
  );
}

function Nightly({ on }: { on: boolean }) {
  const { t } = useI18n();
  const refresh = useRefresh();
  const switched = useMutation({
    mutationFn: (next: boolean) => postJson('/api/memory/nightly', { on: next }),
    onSettled: refresh,
  });
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={switched.isPending ? Boolean(switched.variables) : on}
        disabled={switched.isPending}
        onChange={(event) => switched.mutate(event.target.checked)}
      />
      {t('memory.nightly')}
      {switched.isError && <span className="text-danger">{errorMessage(switched.error, t)}</span>}
    </label>
  );
}

function StoreRow({ store, name }: { store: Store; name: string }) {
  const { t, formatNumber } = useI18n();
  const [open, setOpen] = useState(false);
  const kinds = new Map<FindingKind, Finding[]>();
  for (const finding of store.findings)
    kinds.set(finding.kind, [...(kinds.get(finding.kind) ?? []), finding]);
  return (
    <li className="border-b border-line py-2 last:border-b-0">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <button
          type="button"
          aria-expanded={open}
          disabled={!store.findings.length}
          onClick={() => setOpen(!open)}
          className="flex min-w-40 items-center gap-1 text-left font-medium disabled:cursor-default"
        >
          {store.findings.length ? (
            open ? (
              <ChevronDown size={14} aria-hidden />
            ) : (
              <ChevronRight size={14} aria-hidden />
            )
          ) : (
            <span className="w-3.5" />
          )}
          {name}
        </button>
        <span className="text-muted">
          {t('memory.files')}: <span className="tabular-nums">{formatNumber(store.files)}</span>
        </span>
        {store.index && (
          <span className={store.index.cut ? 'text-danger' : 'text-muted'}>
            {t('memory.indexLines')}:{' '}
            <span className="tabular-nums">{formatNumber(store.index.lines)}</span>
          </span>
        )}
        {store.index && (
          <span className="text-muted">
            {t('memory.tokens')}:{' '}
            <span className="tabular-nums">≈ {formatNumber(store.index.tokens)}</span>
          </span>
        )}
        <span className={store.findings.length ? 'text-ink' : 'text-muted'}>
          {t('memory.findings')}:{' '}
          <span className="tabular-nums">{formatNumber(store.findings.length)}</span>
        </span>
        <Ask
          path="/api/memory/analyse"
          sent={{ store: store.store }}
          label="memory.analyseStore"
          primary={false}
          disabled={!store.unanalysed}
        />
      </div>
      {open && (
        <dl className="mt-2 ml-5 flex flex-col gap-2 text-sm">
          {store.index?.cut ? <p className="text-danger">{t('memory.cut')}</p> : null}
          {[...kinds].map(([kind, found]) => (
            <div key={kind}>
              <dt className="font-medium">
                {t(FINDINGS[kind])}{' '}
                <span className="text-muted tabular-nums">{formatNumber(found.length)}</span>
              </dt>
              <dd className="mt-0.5 flex flex-col font-mono text-xs text-muted">
                {found.map((finding, at) => (
                  <span key={at} className="truncate">
                    {finding.file}
                    {finding.detail ? ` · ${finding.detail}` : ''}
                  </span>
                ))}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  );
}

function History({ history, name }: { history: Proposal[]; name: (store: string) => string }) {
  const { t, formatDay, formatTime } = useI18n();
  const refresh = useRefresh();
  const taken = useMutation({
    mutationFn: (id: number) => postJson<Proposal>(`/api/memory/proposals/${id}/revert`),
    onSettled: refresh,
  });
  if (!history.length) return null;
  return (
    <section aria-label={t('memory.history')}>
      <h2 className="text-base font-semibold">{t('memory.history')}</h2>
      {taken.isError && <p className="text-sm text-danger">{errorMessage(taken.error, t)}</p>}
      <ul className="mt-1 flex flex-col">
        {history.map((proposal) => (
          <li
            key={proposal.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line py-1.5 text-sm last:border-b-0"
          >
            <span className="font-mono">{proposal.file}</span>
            <span className="text-xs text-muted">{name(proposal.store)}</span>
            <span className="text-xs text-muted">{t(KINDS[proposal.kind])}</span>
            {proposal.decided_at && (
              <span className="text-xs text-muted">
                {formatDay(new Date(proposal.decided_at))}{' '}
                {formatTime(new Date(proposal.decided_at))}
              </span>
            )}
            <span className="ml-auto">
              {proposal.state === 'applied' ? (
                <button
                  type="button"
                  disabled={taken.isPending}
                  onClick={() => taken.mutate(proposal.id)}
                  className={button}
                >
                  {t('memory.revert')}
                </button>
              ) : (
                <span className="text-xs text-muted">{t('memory.reverted')}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function MemoryView({ overview, names }: { overview: Overview; names: Names }) {
  const { t, formatNumber } = useI18n();
  const name = useStoreName(overview, names);
  const unanalysed = overview.stores.some((store) => store.unanalysed > 0);
  const byId = new Map(overview.proposals.map((proposal) => [proposal.id, proposal]));
  const advised = overview.advice;
  const grouped = new Set(advised.flatMap((group) => group.proposals));
  const unsorted = overview.proposals.filter((proposal) => !grouped.has(proposal.id));
  return (
    <div className="flex min-w-0 flex-col gap-6 overflow-y-auto">
      <div className="flex flex-wrap items-center gap-4">
        <Ask
          path="/api/memory/analyse"
          sent={{}}
          label="memory.analyse"
          primary
          disabled={!unanalysed}
        />
        <Ask
          path="/api/memory/review"
          sent={{}}
          label="memory.review"
          primary={false}
          disabled={!overview.proposals.length}
        />
        <Nightly on={overview.nightly} />
      </div>
      <section aria-label={t('memory.proposals')}>
        <h2 className="text-base font-semibold">
          {t('memory.proposals')}{' '}
          <span className="text-muted tabular-nums">{formatNumber(overview.proposals.length)}</span>
        </h2>
        {advised.length > 0 && (
          <ul className="mt-2 flex flex-col gap-3">
            {advised.map((group) => (
              <AdviceGroup
                key={group.id}
                group={group}
                proposals={group.proposals.flatMap((id) => byId.get(id) ?? [])}
                name={name}
              />
            ))}
          </ul>
        )}
        {advised.length > 0 && unsorted.length > 0 && (
          <h3 className="mt-4 text-sm font-semibold">{t('memory.unsorted')}</h3>
        )}
        {unsorted.length > 0 && (
          <ul className="mt-2 flex flex-col gap-3">
            {unsorted.map((proposal) => (
              <ProposalCard key={proposal.id} proposal={proposal} name={name(proposal.store)} />
            ))}
          </ul>
        )}
        {!overview.proposals.length && (
          <p className="mt-1 text-sm text-muted">{t('memory.none')}</p>
        )}
      </section>
      <section aria-label={t('memory.stores')}>
        <h2 className="text-base font-semibold">{t('memory.stores')}</h2>
        <ul className="mt-1 flex flex-col">
          {overview.stores.map((store) => (
            <StoreRow key={store.store} store={store} name={name(store.store)} />
          ))}
        </ul>
      </section>
      <History history={overview.history} name={name} />
    </div>
  );
}

/** The agent's memory on the page of code: what each store adds to every session and what is
    wrong with it, the proposals to accept or reject and what was written, to take back (MEM1–5). */
export function Memory({ names }: { names: Names }) {
  const query = useQuery({
    queryKey: MEMORY,
    queryFn: () => getJson<Overview>('/api/memory'),
    retry: false,
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <Failure error={query.error} />;
  return <MemoryView overview={query.data} names={names} />;
}
