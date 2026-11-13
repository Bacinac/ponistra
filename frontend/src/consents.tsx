import { useMutation, useQueryClient } from '@tanstack/react-query';
import { deleteJson, putJson } from './api';
import { useI18n } from './i18n';
import { useSearchConsent, useSearchConsentChange } from './sentence';
import { field } from './styles';
import { TranslationConsent } from './translation';
import { errorMessage } from './tree';
import { SPEECH, useSpeech } from './voice';
import { useAi } from './editor/runs';

const ANSWERS = { ask: null, always: true, words: false } as const;
type Answer = keyof typeof ANSWERS;

function answerOf(translate: boolean | null | undefined): Answer {
  return translate === true ? 'always' : translate === false ? 'words' : 'ask';
}

/** What the user lets go out to the models: their search sentences and their mail in other
 * languages to Claude, their speech to OpenAI. */
export function Consents() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const ai = useAi().data === true;
  const search = useSearchConsent(ai);
  const changeSearch = useSearchConsentChange();
  const speech = useSpeech();
  const changeSpeech = useMutation({
    mutationFn: (given: boolean) =>
      given ? putJson('/api/speech/consent', {}) : deleteJson('/api/speech/consent'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SPEECH }),
  });
  const failure = search.error ?? changeSearch.error ?? speech.error ?? changeSpeech.error;
  const spoken = speech.data?.enabled === true;
  return (
    <>
      {failure && <p className="text-sm text-danger">{errorMessage(failure, t)}</p>}
      <label className="flex flex-col gap-1 text-sm">
        {t('consents.search')}
        <select
          value={answerOf(search.data)}
          disabled={!ai || search.isPending || changeSearch.isPending}
          onChange={(event) => changeSearch.mutate(ANSWERS[event.target.value as Answer])}
          className={field}
        >
          {(Object.keys(ANSWERS) as Answer[]).map((answer) => (
            <option key={answer} value={answer}>
              {t(`consents.search.${answer}`)}
            </option>
          ))}
        </select>
        {!ai && <span className="text-muted">{t('consents.aiOff')}</span>}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={Boolean(speech.data?.given_at)}
          disabled={!spoken || changeSpeech.isPending}
          onChange={(event) => changeSpeech.mutate(event.target.checked)}
        />
        {t('consents.speech')}
      </label>
      {speech.data && !spoken && <p className="text-sm text-muted">{t('speech.off')}</p>}
      <TranslationConsent ai={ai} />
    </>
  );
}
