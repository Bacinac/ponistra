import { useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { useEffect, useRef } from 'react';
import {
  Link,
  matchPath,
  Navigate,
  NavLink,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router';
import { getJson } from './api';
import { Frame, Loading, useWide } from './frame';
import { useI18n } from './i18n';
import { shortcutLabel } from './keys';
import type { HelpResult } from './search';
import { iconButton, sideRow } from './styles';
import { useDark } from './theme';

interface Contents {
  sections: { id: string; title: string; articles: HelpResult[] }[];
  screens: { path: string; article: string }[];
}

interface Article {
  id: string;
  title: string;
  summary: string;
  html: string;
}

function useContents() {
  const { language } = useI18n();
  return useQuery({
    queryKey: ['help', language],
    queryFn: () => getJson<Contents>(`/api/help?lang=${language}`),
  });
}

function Contents({ contents }: { contents: Contents }) {
  const { t } = useI18n();
  return (
    <nav aria-label={t('help.title')} className="flex flex-col gap-4">
      {contents.sections.map((section) => (
        <section key={section.id} className="flex flex-col gap-0.5">
          <h2 className="px-2 text-xs font-semibold text-muted uppercase">{section.title}</h2>
          {section.articles.map((article) => (
            <NavLink key={article.id} to={`/help/${article.id}`} className={sideRow}>
              <span className="truncate">{article.title}</span>
            </NavLink>
          ))}
        </section>
      ))}
    </nav>
  );
}

/** An article's HTML comes from the release's own help. What depends on the reader is settled
    here: the shortcut on their kind of device, the picture in their language and scheme. */
function Body({ html }: { html: string }) {
  const { language } = useI18n();
  const dark = useDark();
  const navigate = useNavigate();
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = body.current;
    if (!root) return;
    for (const keys of root.querySelectorAll<HTMLElement>('kbd[data-keys]')) {
      keys.textContent = shortcutLabel(keys.dataset.keys!);
    }
    for (const shot of root.querySelectorAll<HTMLImageElement>('img[data-shot]')) {
      shot.src = `/help-shots/${shot.dataset.shot}.${language}.${dark ? 'dark' : 'light'}.webp`;
    }
  }, [html, language, dark]);
  return (
    <div
      ref={body}
      className="ponistra-help"
      onClick={(event) => {
        const link = (event.target as HTMLElement).closest('a');
        const to = link?.getAttribute('href');
        if (!to?.startsWith('/')) return;
        event.preventDefault();
        navigate(to);
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function Overview({ contents }: { contents: Contents }) {
  return (
    <div className="ponistra-help">
      {contents.sections.map((section) => (
        <section key={section.id}>
          <h2>{section.title}</h2>
          <ul className="ponistra-help-articles">
            {section.articles.map((article) => (
              <li key={article.id}>
                <Link to={`/help/${article.id}`}>{article.title}</Link>
                <p>{article.summary}</p>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function HelpPage() {
  const { t, language } = useI18n();
  const wide = useWide();
  const { section, article } = useParams();
  const [params] = useSearchParams();
  const from = params.get('from');
  const contents = useContents();
  const id = section && article ? `${section}/${article}` : null;
  const page = useQuery({
    queryKey: ['help', language, id],
    queryFn: () => getJson<Article>(`/api/help/${id}?lang=${language}`),
    enabled: id !== null,
  });
  if (!id && from && contents.data) {
    const screen = contents.data.screens.find(({ path }) => matchPath(path, from));
    return <Navigate to={screen ? `/help/${screen.article}` : '/help'} replace />;
  }
  const list = contents.data && <Contents contents={contents.data} />;
  return (
    <Frame
      title={id ? (page.data?.title ?? t('help.title')) : t('help.title')}
      folders={false}
      side={wide ? list : undefined}
    >
      {!wide && id && (
        <Link to="/help" aria-label={t('frame.close')} className={`${iconButton} mb-2 inline-flex`}>
          <X size={16} aria-hidden />
        </Link>
      )}
      {id ? (
        page.data ? (
          <>
            <p className="ponistra-help-summary">{page.data.summary}</p>
            <Body html={page.data.html} />
          </>
        ) : page.isError ? (
          <Navigate to="/help" replace />
        ) : (
          <Loading />
        )
      ) : !contents.data ? (
        <Loading />
      ) : wide ? (
        <Overview contents={contents.data} />
      ) : (
        list
      )}
    </Frame>
  );
}
