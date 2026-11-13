import { CalendarDays, Paperclip, Plus, Search, Shapes, X } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { Frame, Loading } from './frame';
import { useI18n } from './i18n';
import { Menu, MenuItem, MenuSub } from './menu';
import {
  eventHref,
  EventSummary,
  FilterChips,
  FilterErrors,
  KINDS,
  LAST,
  mailHref,
  MailSummary,
  useMailAccounts,
  conversationHref,
  ConversationSummary,
  personHref,
  PersonSummary,
  resultHref,
  ResultSummary,
  SEARCH_ICONS,
  SHORTEST,
  taskHref,
  TaskSummary,
  useSearch,
  useVaultHits,
  vaultHref,
  VaultLocked,
  VaultSummary,
  HelpSummary,
  versionHref,
  VersionSummary,
  asksVault,
  withFilter,
  type SearchFilter,
} from './search';
import { useTranslator } from './sentence';
import { button, field, iconButton, primaryButton } from './styles';
import { errorMessage, PlaceLink, useNode } from './tree';

const MOST = 50;

function AddFilter({
  text,
  filters,
  onChange,
}: {
  text: string;
  filters: SearchFilter[];
  onChange: (text: string) => void;
}) {
  const { t } = useI18n();
  const add = (keys: SearchFilter['key'][], token: string) =>
    onChange(withFilter(text, filters, keys, token));
  return (
    <Menu
      align="start"
      trigger={
        <button type="button" className={`${button} py-1`}>
          <Plus size={14} aria-hidden />
          {t('search.filter.add')}
        </button>
      }
    >
      <MenuSub icon={Shapes} label={t('search.kind')}>
        {KINDS.map((kind) => (
          <MenuItem
            key={kind}
            icon={SEARCH_ICONS[kind]}
            label={t(`search.kind.${kind}`)}
            onSelect={() => add(['kind'], `${t('search.token.kind')}:${t(`search.value.${kind}`)}`)}
          />
        ))}
      </MenuSub>
      <MenuSub icon={CalendarDays} label={t('search.filter.date')}>
        {LAST.map((last) => (
          <MenuItem
            key={last}
            icon={CalendarDays}
            label={t(`search.last.${last}`)}
            onSelect={() =>
              add(['date', 'changed'], `${t('search.token.date')}:${t(`search.value.${last}`)}`)
            }
          />
        ))}
      </MenuSub>
      <MenuItem
        icon={Paperclip}
        label={t('search.filter.has')}
        onSelect={() => add(['has'], t('search.token.has'))}
      />
    </Menu>
  );
}

function Group({
  heading,
  count,
  children,
}: {
  heading: string;
  count: number;
  children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-medium tracking-wide text-muted uppercase">{heading}</h2>
      <ul className="divide-y divide-line rounded border border-line">{children}</ul>
      {count === MOST && <p className="text-sm text-muted">{t('search.limited')}</p>}
    </section>
  );
}

export function SearchPage() {
  const { t, formatDate, formatNumber } = useI18n();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const q = params.get('q') ?? '';
  const within = params.get('in');
  const search = useSearch(q, { in: within }, MOST);
  const folder = useNode(within);
  const [draft, setDraft] = useState(q);
  const translator = useTranslator((to) => {
    setDraft(new URL(to, window.location.origin).searchParams.get('q') ?? '');
    void navigate(to);
  });
  const [shown, setShown] = useState(q);
  if (q !== shown) {
    setShown(q);
    setDraft(q);
  }

  function update(next: Record<string, string | null>) {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value);
      else merged.delete(key);
    }
    setParams(merged, { replace: true });
  }

  const ask = (text: string) => update({ q: text.trim() || null });
  const refine = (text: string) => update({ q: text.trim() || null });
  const text = q.trim();
  const found = text.length >= SHORTEST ? search.data : undefined;
  const filters = found?.filters ?? [];
  const documents = found?.documents ?? [];
  const mail = found?.mail ?? [];
  const talks = found?.conversations ?? [];
  const events = found?.events ?? [];
  const tasks = found?.tasks ?? [];
  const people = found?.people ?? [];
  const vault = useVaultHits(found, text);
  const versions = found?.versions ?? [];
  const help = found?.help ?? [];
  const accountsOf = useMailAccounts(mail);
  const row = 'flex items-start gap-3 px-3 py-2 hover:bg-hover';

  return (
    <Frame title={t('search.title')} searchable={false}>
      <section className="flex w-full max-w-4xl flex-col gap-4">
        <form
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            if (!translator.pending && !translator.translate(draft)) ask(draft);
          }}
          className="flex gap-2"
        >
          <input
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label={t('search.label')}
            placeholder={t('search.placeholder')}
            className={`${field} min-w-0 flex-1`}
          />
          <button type="submit" disabled={translator.pending} className={primaryButton}>
            <Search size={16} aria-hidden />
            <span className="sr-only sm:not-sr-only">{t('search.label')}</span>
          </button>
        </form>
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <FilterChips text={text} filters={filters} onChange={refine} />
            {within && (
              <span className="inline-flex min-w-0 items-center gap-1 rounded border border-line py-0.5 pr-0.5 pl-2">
                <span className="truncate">
                  {t('search.in')} „{folder.data?.node.title ?? '…'}”
                </span>
                <button
                  type="button"
                  aria-label={t('search.everywhere')}
                  title={t('search.everywhere')}
                  onClick={() => update({ in: null })}
                  className={iconButton}
                >
                  <X size={14} aria-hidden />
                </button>
              </span>
            )}
            <AddFilter text={text} filters={filters} onChange={refine} />
          </div>
          {translator.pending && <p className="text-sm text-muted">{t('search.ai.translating')}</p>}
          {translator.failed && (
            <p className="text-sm text-danger">
              {errorMessage(translator.failed, t)}{' '}
              <button
                type="button"
                onClick={() => ask(translator.sentence ?? draft)}
                className="underline underline-offset-2"
              >
                {t('search.ai.literal')}
              </button>
            </p>
          )}
          <FilterErrors filters={filters} />
          <VaultLocked shown={found !== undefined && asksVault(filters)} />
        </div>
        {text.length < SHORTEST ? (
          <p className="text-muted">{t('search.hint')}</p>
        ) : search.isPending ? (
          <Loading />
        ) : search.isError ? (
          <p className="text-danger">{errorMessage(search.error, t)}</p>
        ) : documents.length +
            mail.length +
            events.length +
            talks.length +
            tasks.length +
            people.length +
            vault.length +
            versions.length +
            help.length ===
          0 ? (
          <p className="text-muted">
            {t('search.none')} „{text}”.
          </p>
        ) : (
          <>
            {documents.length > 0 && (
              <Group heading={t('search.documents')} count={documents.length}>
                {documents.map((result) => (
                  <li key={result.id}>
                    <PlaceLink
                      to={resultHref(result)}
                      className="flex items-start gap-3 px-3 py-2 hover:bg-hover"
                    >
                      <ResultSummary result={result} />
                      <span className="hidden shrink-0 flex-col items-end text-sm text-muted sm:flex">
                        {formatDate(result.updated_at)}
                        {result.hits > 1 && (
                          <span className="text-xs">
                            {t('search.hits')}: {formatNumber(result.hits)}
                          </span>
                        )}
                      </span>
                    </PlaceLink>
                  </li>
                ))}
              </Group>
            )}
            {mail.length > 0 && (
              <Group heading={t('search.mail')} count={mail.length}>
                {mail.map((result) => (
                  <li key={result.id}>
                    <Link to={mailHref(result, accountsOf(result))} className={row}>
                      <MailSummary result={result} accounts={accountsOf(result)} />
                      {result.hits > 1 && (
                        <span className="hidden shrink-0 text-xs text-muted sm:block">
                          {t('search.hits')}: {formatNumber(result.hits)}
                        </span>
                      )}
                    </Link>
                  </li>
                ))}
              </Group>
            )}
            {events.length > 0 && (
              <Group heading={t('search.events')} count={events.length}>
                {events.map((result) => (
                  <li key={result.id}>
                    <Link to={eventHref(result)} className={row}>
                      <EventSummary result={result} />
                      {result.hits > 1 && (
                        <span className="hidden shrink-0 text-xs text-muted sm:block">
                          {t('search.occurrences')}: {formatNumber(result.hits)}
                        </span>
                      )}
                    </Link>
                  </li>
                ))}
              </Group>
            )}
            {talks.length > 0 && (
              <Group heading={t('search.conversations')} count={talks.length}>
                {talks.map((result) => (
                  <li key={result.id}>
                    <Link to={conversationHref(result)} className={row}>
                      <ConversationSummary result={result} />
                    </Link>
                  </li>
                ))}
              </Group>
            )}
            {tasks.length > 0 && (
              <Group heading={t('search.tasks')} count={tasks.length}>
                {tasks.map((result) => (
                  <li key={result.id}>
                    <Link to={taskHref(result)} className={row}>
                      <TaskSummary result={result} />
                    </Link>
                  </li>
                ))}
              </Group>
            )}
            {people.length > 0 && (
              <Group heading={t('search.people')} count={people.length}>
                {people.map((result) => (
                  <li key={`${result.kind}-${result.id}`}>
                    <Link to={personHref(result)} className={row}>
                      <PersonSummary result={result} />
                    </Link>
                  </li>
                ))}
              </Group>
            )}
            {vault.length > 0 && (
              <Group heading={t('search.vault')} count={vault.length}>
                {vault.map((result) => (
                  <li key={result.id}>
                    <Link to={vaultHref(result)} className={row}>
                      <VaultSummary result={result} />
                    </Link>
                  </li>
                ))}
              </Group>
            )}
            {versions.length > 0 && (
              <Group heading={t('search.versions')} count={versions.length}>
                {versions.map((result) => (
                  <li key={result.id}>
                    <Link to={versionHref(result)} className={row}>
                      <VersionSummary result={result} />
                      {result.hits > 1 && (
                        <span className="hidden shrink-0 text-xs text-muted sm:flex">
                          {t('search.versionHits')}: {formatNumber(result.hits)}
                        </span>
                      )}
                    </Link>
                  </li>
                ))}
              </Group>
            )}
            {help.length > 0 && (
              <Group heading={t('search.help')} count={help.length}>
                {help.map((result) => (
                  <li key={result.id}>
                    <Link to={`/help/${result.id}`} className={row}>
                      <HelpSummary result={result} />
                    </Link>
                  </li>
                ))}
              </Group>
            )}
          </>
        )}
      </section>
      {translator.dialog}
    </Frame>
  );
}
