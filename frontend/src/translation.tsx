import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Languages, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { ApiError, getJson, postJson, putJson } from './api';
import { Cancel, Modal } from './dialogs';
import { languageName, useI18n } from './i18n';
import { button, field, iconButton, primaryButton } from './styles';
import { errorMessage } from './tree';
import { useAi } from './editor/runs';

const READING = ['translation'] as const;

interface Reading {
  /** The languages the user reads; none chosen yet means the interface's. */
  languages: string[] | null;
  /** Whether a message in another language goes to Claude to be translated as it opens. */
  automatic: boolean;
  /** Every language the server tells a text by. */
  known: string[];
}

function useReading() {
  return useQuery({
    queryKey: READING,
    queryFn: () => getJson<Reading>('/api/translation'),
    staleTime: Infinity,
  });
}

function useReadingChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changed: Pick<Reading, 'languages' | 'automatic'>) =>
      putJson<Reading>('/api/translation', changed),
    onSuccess: (found) => queryClient.setQueryData(READING, found),
  });
}

/** The languages the user reads: what is written in another is offered to be translated into
 * the interface's. */
export function ReadingLanguages() {
  const { t, language } = useI18n();
  const reading = useReading();
  const change = useReadingChange();
  const found = reading.data;
  if (!found) {
    return reading.error ? (
      <p className="text-sm text-danger">{errorMessage(reading.error, t)}</p>
    ) : null;
  }
  const reads = found.languages ?? [language];
  const name = (code: string) => languageName(code, language);
  const others = found.known
    .filter((code) => !reads.includes(code))
    .sort((a, b) => name(a).localeCompare(name(b), language));
  const changed = (languages: string[]) => change.mutate({ languages, automatic: found.automatic });
  return (
    <div className="flex flex-col gap-2 text-sm">
      {change.error && <p className="text-danger">{errorMessage(change.error, t)}</p>}
      {t('translation.reads')}
      <ul aria-label={t('translation.reads')} className="flex flex-wrap gap-2">
        {reads.map((code) => (
          <li
            key={code}
            className="flex min-w-0 items-center gap-1 rounded-full bg-panel py-1 pr-1 pl-3"
          >
            <span className="truncate">{name(code)}</span>
            <button
              type="button"
              disabled={reads.length === 1 || change.isPending}
              onClick={() => changed(reads.filter((each) => each !== code))}
              title={t('translation.remove')}
              aria-label={`${t('translation.remove')}: ${name(code)}`}
              className={iconButton}
            >
              <X size={14} aria-hidden />
            </button>
          </li>
        ))}
      </ul>
      <select
        value=""
        aria-label={t('translation.add')}
        disabled={change.isPending}
        onChange={(event) => changed([...reads, event.target.value])}
        className={field}
      >
        <option value="" disabled>
          {t('translation.add')}
        </option>
        {others.map((code) => (
          <option key={code} value={code}>
            {name(code)}
          </option>
        ))}
      </select>
    </div>
  );
}

/** Whether mail in a language the user does not read goes to Claude as it opens. */
export function TranslationConsent({ ai }: { ai: boolean }) {
  const { t } = useI18n();
  const reading = useReading();
  const change = useReadingChange();
  const found = reading.data;
  if (!found) {
    return reading.error ? (
      <p className="text-sm text-danger">{errorMessage(reading.error, t)}</p>
    ) : null;
  }
  return (
    <>
      {change.error && <p className="text-sm text-danger">{errorMessage(change.error, t)}</p>}
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={found.automatic}
          disabled={!ai || change.isPending}
          onChange={(event) =>
            change.mutate({ languages: found.languages, automatic: event.target.checked })
          }
        />
        {t('consents.mail.automatic')}
      </label>
    </>
  );
}

function TranslationConsentDialog({
  onChoose,
  onClose,
}: {
  onChoose: (always: boolean) => void;
  onClose: () => void;
}) {
  const { t } = useI18n();
  return (
    <Modal heading={t('ai.consent.heading')} onClose={onClose}>
      <p className="text-sm">{t('translation.consent.body')}</p>
      <p className="text-sm text-muted">{t('translation.consent.note')}</p>
      <div className="flex flex-wrap justify-end gap-2">
        <Cancel />
        <button type="button" className={button} onClick={() => onChoose(true)}>
          {t('translation.consent.always')}
        </button>
        <button type="button" className={primaryButton} onClick={() => onChoose(false)}>
          {t('ai.consent.once')}
        </button>
      </div>
    </Modal>
  );
}

/** Lets the user's mail out to Claude as they choose where they have not agreed for all of it:
 * `ask` opens the question on the server's refusal, and `go` runs again with their answer, this
 * once or, once they agreed for all of their mail, as it stands. */
function useConsented(go: (once: boolean) => void) {
  const reading = useReading();
  const change = useReadingChange();
  const [asking, setAsking] = useState(false);

  function choose(always: boolean) {
    setAsking(false);
    if (!always) go(true);
    else if (reading.data)
      change.mutate(
        { languages: reading.data.languages, automatic: true },
        { onSuccess: () => go(false) },
      );
  }

  return {
    ask: (error: Error) => {
      if (asked(error)) setAsking(true);
    },
    dialog: asking && (
      <TranslationConsentDialog onChoose={choose} onClose={() => setAsking(false)} />
    ),
    change,
    /** What failed: the translation, unless it only asked, or agreeing for all of the mail. */
    failure: (error: Error | null) => (error && !asked(error) ? error : change.error),
  };
}

function asked(error: Error): boolean {
  return error instanceof ApiError && error.code === 'consent_needed';
}

/** Whether the user does not read the language; false while it is unknown. */
export function useForeign(code: string | null | undefined): boolean {
  const { language } = useI18n();
  const reading = useReading();
  const reads = reading.data && (reading.data.languages ?? [language]);
  return Boolean(code && reads && !reads.includes(code));
}

/** A message's translation into the interface's language: the bar that offers it where the
 * message is in a language the user does not read, and shows it once translated, asking first
 * where the user has not agreed for all of their mail, or translating it as it opens where they
 * have; `translate` for the message's menu, where code cannot tell its language. `onInto` gives
 * the language to show it in, null for the original. */
export function useMessageTranslation(
  id: number,
  shown: { language: string | null; translated: string | null } | undefined,
  onInto: (language: string | null) => void,
) {
  const { t, language } = useI18n();
  const ai = useAi().data === true;
  const reading = useReading();
  const started = useRef(false);
  const translating = useMutation({
    mutationFn: (once: boolean) =>
      postJson<{ translated: string }>(`/api/mail/messages/${id}/translation`, {
        language,
        ...(once && { consent: 'once' }),
      }),
    onSuccess: ({ translated }) => onInto(translated),
    onError: (error) => consented.ask(error),
  });
  const consented = useConsented(translating.mutate);
  const foreign = useForeign(shown?.language);
  const automatic = ai && foreign && reading.data?.automatic === true;
  useEffect(() => {
    if (!automatic || started.current) return;
    started.current = true;
    translating.mutate(false);
  }, [automatic, translating]);

  const failure = consented.failure(translating.error);
  const pending = translating.isPending || consented.change.isPending;
  const from = shown?.language;
  const into = shown?.translated;
  const named = [from, into].filter(Boolean).map((code) => languageName(code!, language));
  const bar = (
    <>
      {ai && (foreign || into || pending || failure) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded bg-panel px-3 py-2 text-sm">
          <Languages size={16} aria-hidden className="shrink-0 text-muted" />
          {named.length > 0 && <span>{named.join(' → ')}</span>}
          {into ? (
            <button type="button" className="underline" onClick={() => onInto(null)}>
              {t('translation.original')}
            </button>
          ) : pending ? (
            <span className="text-muted">{t('translation.translating')}</span>
          ) : (
            <button type="button" className="underline" onClick={() => translating.mutate(false)}>
              {t('translation.translate')}
            </button>
          )}
          {failure && <span className="text-danger">{errorMessage(failure, t)}</span>}
        </div>
      )}
      {consented.dialog}
    </>
  );
  return {
    bar,
    offered: ai && !foreign && !into && !pending && from !== language,
    translate: () => translating.mutate(false),
  };
}

/** What the reply is written as: its subject, HTML and the lines saying what it answers. */
export interface Written {
  subject: string;
  html: string;
  heading: string[];
}

/** The reply in the language of the message it answers, and what the user wrote, which the
 * message keeps once sent. */
export interface TranslatedReply extends Written {
  language: string;
  source: { language: string; subject: string; blocks: Record<string, string>; run: string };
}

/** The reply translated into the language of the message it answers, offered where the user
 * does not read that language (D35-2), asking first where they have not agreed for all of their
 * mail. */
export function useReplyTranslation(answered: { id: number; language: string | null } | undefined) {
  const { language } = useI18n();
  const ai = useAi().data === true;
  const foreign = useForeign(answered?.language);
  const [reply, setReply] = useState<TranslatedReply | null>(null);
  const written = useRef<Written | null>(null);
  const translating = useMutation({
    mutationFn: (once: boolean) =>
      postJson<TranslatedReply>(`/api/mail/messages/${answered!.id}/translated-reply`, {
        ...written.current,
        language,
        ...(once && { consent: 'once' }),
      }),
    onSuccess: setReply,
    onError: (error) => consented.ask(error),
  });
  const consented = useConsented(translating.mutate);
  return {
    offered: ai && foreign && answered !== undefined,
    reply,
    pending: translating.isPending || consented.change.isPending,
    failure: consented.failure(translating.error),
    dialog: consented.dialog,
    translate(given: Written) {
      written.current = given;
      translating.mutate(false);
    },
    /** The translation as the user corrects it. */
    change: (changed: Partial<Written>) => setReply((kept) => kept && { ...kept, ...changed }),
    back: () => {
      setReply(null);
      translating.reset();
    },
  };
}
