import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ApiError, deleteJson, getJson, postJson, putJson } from './api';
import { Cancel, Modal } from './dialogs';
import { useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import type { SearchKind } from './search';
import { button, primaryButton } from './styles';
import { useAi } from './editor/runs';

const WORDS = 3;
const TYPED_FILTER = /(?:^|\s)\p{L}+:/u;
const CONSENT = ['search', 'ai'];

/** What the model read in a sentence: the words to look for and the filters it asks for. */
export interface Translated {
  text: string;
  kind?: SearchKind;
  from?: string;
  account?: string;
  folder?: string;
  since?: string;
  until?: string;
  changed?: boolean;
  attachment?: boolean;
}

type Answer = 'once' | 'always' | 'words';

/** Whether Enter hands the text to the model: words enough for a sentence, none of them a
 * filter. */
export function isSentence(text: string): boolean {
  return text.trim().split(/\s+/).length >= WORDS && !TYPED_FILTER.test(text);
}

function quoted(value: string): string {
  const bare = value.replaceAll('"', '').trim();
  return /\s/.test(bare) ? `"${bare}"` : bare;
}

/** The box's text for what the model read, each filter typed as the interface's language
 * types it. */
export function translatedQuery(found: Translated, t: (key: MessageKey) => string): string {
  const tokens = [found.text.trim()];
  if (found.kind) tokens.push(`${t('search.token.kind')}:${t(`search.value.${found.kind}`)}`);
  if (found.from) tokens.push(`${t('search.token.from')}:${quoted(found.from)}`);
  if (found.account) tokens.push(`${t('search.token.account')}:${quoted(found.account)}`);
  if (found.folder) tokens.push(`${t('search.token.folder')}:${quoted(found.folder)}`);
  if (found.since || found.until) {
    const key = found.changed ? 'search.token.changed' : 'search.token.date';
    const period =
      found.since === found.until ? found.since : `${found.since ?? ''}..${found.until ?? ''}`;
    tokens.push(`${t(key)}:${period}`);
  }
  if (found.attachment) tokens.push(t('search.token.has'));
  return tokens.filter(Boolean).join(' ');
}

export function searchHref(q: string): string {
  return `/search?${new URLSearchParams({ q })}`;
}

/** The user's answer for all of their searches: their sentences go to the model, they do
 * not, or it is still to be asked. */
export function useSearchConsent(enabled: boolean) {
  return useQuery({
    queryKey: CONSENT,
    queryFn: async () => (await getJson<{ translate: boolean | null }>('/api/search/ai')).translate,
    enabled,
  });
}

export function useSearchConsentChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (translate: boolean | null) =>
      translate === null ? deleteJson('/api/search/ai') : putJson('/api/search/ai', { translate }),
    onSuccess: (_, translate) => queryClient.setQueryData(CONSENT, translate),
  });
}

function SearchConsentDialog({
  onChoose,
  onClose,
}: {
  onChoose: (answer: Answer) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <Modal heading={t('ai.consent.heading')} onClose={onClose}>
      <p className="text-sm">{t('search.consent.body')}</p>
      <p className="text-sm text-muted">{t('search.consent.note')}</p>
      <div className="flex flex-wrap justify-end gap-2">
        <Cancel />
        <button type="button" className={button} onClick={() => onChoose('words')}>
          {t('search.consent.words')}
        </button>
        <button type="button" className={button} onClick={() => onChoose('always')}>
          {t('search.consent.always')}
        </button>
        <button type="button" className={primaryButton} onClick={() => onChoose('once')}>
          {t('ai.consent.once')}
        </button>
      </div>
    </Modal>
  );
}

/** Hands a sentence to the model and goes to the search with what it read, asking first where
 * the user has not answered for all their searches; `translate` tells whether it took the
 * text, and what it leaves the search takes as typed. */
export function useTranslator(go: (to: string) => void) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const ai = useAi().data === true;
  const consent = useSearchConsent(ai);
  const change = useSearchConsentChange();
  const [asking, setAsking] = useState<string | null>(null);
  const translating = useMutation({
    mutationFn: ({ sentence, once }: { sentence: string; once?: boolean }) =>
      postJson<{ translated: Translated }>('/api/search/translate', {
        sentence,
        ...(once && { consent: 'once' }),
      }),
    onSuccess: ({ translated }, { sentence }) =>
      go(searchHref(translatedQuery(translated, t) || sentence)),
    onError: (error, { sentence }) => {
      if (!(error instanceof ApiError && error.code === 'consent_needed')) return;
      queryClient.setQueryData(CONSENT, null);
      setAsking(sentence);
    },
  });
  const asked =
    translating.error instanceof ApiError && translating.error.code === 'consent_needed';

  function translate(text: string): boolean {
    if (!ai || consent.data === false || !isSentence(text)) return false;
    translating.mutate({ sentence: text.trim() });
    return true;
  }

  function choose(sentence: string, answer: Answer) {
    setAsking(null);
    if (answer === 'once') translating.mutate({ sentence, once: true });
    else
      change.mutate(answer === 'always', {
        onSuccess: () =>
          answer === 'always' ? translating.mutate({ sentence }) : go(searchHref(sentence)),
      });
  }

  return {
    translate,
    pending: translating.isPending || change.isPending,
    failed: asked ? null : translating.error,
    sentence: translating.variables?.sentence,
    dialog: asking !== null && (
      <SearchConsentDialog
        onChoose={(answer) => choose(asking, answer)}
        onClose={() => setAsking(null)}
      />
    ),
  };
}
