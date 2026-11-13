import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CalendarPlus,
  CircleHelp,
  ContactRound,
  Globe,
  ListTodo,
  Mic,
  Square,
  StickyNote,
} from 'lucide-react';
import { Suspense, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { getJson, postBytes, postJson, putJson } from './api';
import { EventDialog } from './calendar';
import { useCalendars, ZONE } from './calendarData';
import type { Start } from './compose';
import { Cancel, Modal } from './dialogs';
import { useI18n } from './i18n';
import { lazily } from './lazily';
import { useLinks } from './linksData';
import { useNewNote } from './notes';
import { usePalette, type Choice } from './palette';
import { PLACES, usePlaces } from './places';
import { searchHref, translatedQuery, type Translated } from './sentence';
import { button, field, primaryButton } from './styles';
import { TaskDialog } from './tasks';
import { useHeldRelease } from './release';
import { errorMessage, nodeHref, useOpen } from './tree';
import { fold, wordsOf } from './vault/search';
import { type Person, useAccounts } from './mailData';

const Compose = lazily(() => import('./compose'), 'Compose');

export const SPEECH = ['speech'];
// A note is said in minutes; longer speech is stopped and written as it stands.
const LONGEST = 10 * 60;
const KINDS = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus'];
const RELATED_SHOWN = 5;
// As the backend reads: longer speech is a dictated page, kept as a note without reading.
const SAID = 2000;

/** Whether the installation writes speech, and whether the user agreed to theirs going out. */
export function useSpeech() {
  return useQuery({
    queryKey: SPEECH,
    queryFn: () =>
      getJson<{ enabled: boolean; understands: boolean; given_at: string | null }>(
        '/api/speech/consent',
      ),
  });
}

function ConsentDialog({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const agree = useMutation({
    mutationFn: () => putJson('/api/speech/consent', {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SPEECH }),
  });
  return (
    <Modal heading={t('speech.consent.heading')} onClose={onClose}>
      <p className="text-sm">{t('speech.consent.body')}</p>
      {agree.isError && <p className="text-sm text-danger">{errorMessage(agree.error, t)}</p>}
      <div className="flex justify-end gap-2">
        <Cancel />
        <button
          type="button"
          disabled={agree.isPending}
          onClick={() => agree.mutate()}
          className={primaryButton}
        >
          {t('speech.consent.agree')}
        </button>
      </div>
    </Modal>
  );
}

/** The person a name said stands for: the first the address field would offer for it. */
async function addressee(said: string): Promise<Person | undefined> {
  if (said.includes('@')) return { name: '', address: said };
  const { people } = await getJson<{ people: Person[] }>(
    `/api/mail/people?${new URLSearchParams({ q: said })}`,
  );
  return people[0];
}

function minutes(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/** The commands whose label is what was said, and those that hold every word of it. */
function commandsFor(said: string, choices: Choice[]): { exact: Choice[]; related: Choice[] } {
  const words = wordsOf(said);
  const spoken = words.join(' ');
  const open = choices.filter((choice) => !choice.disabled);
  return {
    exact: open.filter((choice) => wordsOf(choice.label).join(' ') === spoken),
    related: words.length
      ? open
          .filter((choice) => words.every((word) => fold(choice.label).includes(word)))
          .slice(0, RELATED_SHOWN)
      : [],
  };
}

/** Opens a page in a tab of its own; false where the browser keeps a page from opening a tab this
 * long after the user's click, which a tab opened without its opener cannot tell. */
function opened(href: string): boolean {
  const tab = window.open(href, '_blank');
  if (tab) tab.opener = null;
  return tab !== null;
}

interface Page {
  id: string;
  title: string;
  href: string;
}

type Reading =
  | {
      intent: 'event';
      summary: string;
      day: string;
      time?: string;
      all_day?: boolean;
      end_day?: string;
      end_time?: string;
      location?: string;
    }
  | { intent: 'task'; text: string; due?: string }
  | { intent: 'note' }
  | { intent: 'open'; place: string; day?: string }
  | { intent: 'link'; name: string; links: Page[] }
  | { intent: 'person'; name: string; people: { id: number; name: string }[] }
  | { intent: 'help'; text: string; articles: { id: string; title: string }[] }
  | ({ intent: 'search' } & Translated)
  | { intent: 'mail'; to: string[]; subject: string; text: string; account?: string }
  | { intent: 'document'; title: string };

type Recorded =
  { name: 'starting' | 'recording' | 'writing' } | { name: 'failed'; failure: string };

type Stage =
  | { name: 'reading' }
  | { name: 'heard'; text: string; related: Choice[]; reading?: Reading; unread?: string }
  | { name: 'mail'; start: Start };

interface Recording {
  stage: Recorded;
  seconds: number;
  level: number;
  finish: () => void;
}

/** Records what the user says until they stop, or for ten minutes at most, and has the
 * installation write it, handing the text to `written`. */
function useRecording(written: (text: string) => void): Recording {
  const { t } = useI18n();
  const [stage, setStage] = useState<Recorded>({ name: 'starting' });
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const finish = useRef<() => void>(() => {});
  const heard = useRef(written);
  heard.current = written;
  useHeldRelease(true);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    let frame = 0;
    let ticking = 0;
    let gone = false;
    const parts: Blob[] = [];

    async function write(audio: Blob) {
      setStage({ name: 'writing' });
      try {
        const { text } = await postBytes<{ text: string }>('/api/speech', audio);
        if (gone) return;
        if (text) heard.current(text);
        else setStage({ name: 'failed', failure: t('speech.nothing') });
      } catch (error) {
        if (!gone) setStage({ name: 'failed', failure: errorMessage(error as Error, t) });
      }
    }

    void (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch {
        if (!gone) setStage({ name: 'failed', failure: t('speech.microphone') });
        return;
      }
      if (gone) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const mimeType = KINDS.find((kind) => MediaRecorder.isTypeSupported(kind));
      const made = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      made.ondataavailable = (event) => parts.push(event.data);
      made.onstop = () => {
        stream?.getTracks().forEach((track) => track.stop());
        if (!gone) void write(new Blob(parts, { type: made.mimeType.split(';')[0] }));
      };
      recorder.current = made;
      made.start();
      setStage({ name: 'recording' });

      context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      context.createMediaStreamSource(stream).connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const listen = () => {
        analyser.getByteTimeDomainData(samples);
        const peak = samples.reduce((most, sample) => Math.max(most, Math.abs(sample - 128)), 0);
        setLevel(peak / 128);
        frame = requestAnimationFrame(listen);
      };
      listen();
      const started = Date.now();
      ticking = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - started) / 1000);
        setSeconds(elapsed);
        if (elapsed >= LONGEST) finish.current();
      }, 250);
    })();

    finish.current = () => {
      window.clearInterval(ticking);
      cancelAnimationFrame(frame);
      if (recorder.current?.state === 'recording') recorder.current.stop();
    };

    return () => {
      gone = true;
      window.clearInterval(ticking);
      cancelAnimationFrame(frame);
      if (recorder.current?.state === 'recording') recorder.current.stop();
      stream?.getTracks().forEach((track) => track.stop());
      void context?.close();
    };
  }, []);

  return { stage, seconds, level, finish: () => finish.current() };
}

/** What a recording shows while it runs and is written, and the button that ends it. */
function RecordingModal({
  recording,
  reading = false,
  onClose,
}: {
  recording: Recording;
  reading?: boolean;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const { stage, seconds, level } = recording;
  return (
    <Modal heading={t('speech.record.heading')} onClose={onClose}>
      {stage.name === 'failed' ? (
        <p className="text-sm text-danger">{stage.failure}</p>
      ) : stage.name === 'writing' || reading ? (
        <p className="text-sm text-muted" role="status">
          {t(reading ? 'speech.reading' : 'speech.writing')}
        </p>
      ) : (
        <div className="flex items-center gap-3" role="status">
          <span
            aria-hidden
            className="size-3 shrink-0 rounded-full bg-danger"
            style={{
              opacity: stage.name === 'recording' ? 0.4 + 0.6 * Math.min(1, level * 3) : 0.2,
            }}
          />
          <span className="text-sm">
            {stage.name === 'recording' ? t('speech.listening') : t('speech.starting')}
          </span>
          <span className="ml-auto text-sm text-muted tabular-nums">{minutes(seconds)}</span>
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Cancel />
        {stage.name !== 'failed' && (
          <button
            type="button"
            disabled={stage.name !== 'recording' || reading}
            onClick={recording.finish}
            className={primaryButton}
          >
            <Square size={16} aria-hidden />
            {t('speech.done')}
          </button>
        )}
      </div>
    </Modal>
  );
}

/** Records what the user says until they stop and has the installation write it. A command of
 * the search box said by its name runs. Anything else goes to the installation's model: a place
 * it names opens, a search runs, a message or a document opens in its own dialog, and an event,
 * a task or a note is shown to be checked beside the commands it names. */
function VoiceDialog({ understands, onClose }: { understands: boolean; onClose: () => void }) {
  const { t, formatDays } = useI18n();
  const calendars = useCalendars();
  const [editing, setEditing] = useState<'event' | 'task' | null>(null);
  const note = useNewNote();
  const navigate = useNavigate();
  const accounts = useAccounts();
  const palette = usePalette();
  const places = usePlaces();
  const links = useLinks();
  const open = useOpen();
  const [stage, setStage] = useState<Stage | null>(null);
  const heard = useRef<(text: string) => void>(() => {});
  const recording = useRecording((text) => heard.current(text));

  const toPage = (page: Page): Choice => ({
    id: `link:${page.id}`,
    label: `${t('places.open')}: ${page.title}`,
    icon: Globe,
    disabled: false,
    run: () => open(page.href),
  });

  /** Opens the one page meant, or offers the pages to be clicked: several, or one the browser
   * would not open. */
  const visit = (pages: Page[], text: string, related: Choice[]) => {
    if (pages.length === 1 && opened(pages[0].href)) {
      onClose();
      return;
    }
    const offered = pages.map(toPage);
    const ids = new Set(offered.map((choice) => choice.id));
    setStage({
      name: 'heard',
      text,
      related: [...offered, ...related.filter((choice) => !ids.has(choice.id))],
    });
  };

  heard.current = (text) => {
    const pages = (links.data?.links ?? []).map((link) => ({ ...link, href: nodeHref(link) }));
    const { exact, related } = commandsFor(text, [
      ...(palette?.('') ?? []),
      ...places(''),
      ...pages.map(toPage),
    ]);
    if (exact.length === 1) {
      const page = pages.find((each) => exact[0].id === `link:${each.id}`);
      if (page) {
        visit([page], text, related);
        return;
      }
      onClose();
      exact[0].run();
      return;
    }
    if (!understands || text.length > SAID) {
      setStage({ name: 'heard', text, related });
      return;
    }
    setStage({ name: 'reading' });
    const unread = (error: Error) =>
      setStage({ name: 'heard', text, related, unread: errorMessage(error, t) });
    postJson<Reading>('/api/speech/understand', { text, zone: ZONE }).then((reading) => {
      if (reading.intent === 'open') {
        onClose();
        const to = PLACES.find((place) => place.id === reading.place)?.to ?? '/';
        void navigate(
          reading.place === 'calendar' && reading.day ? `${to}/day/${reading.day}` : to,
        );
      } else if (reading.intent === 'link') {
        if (reading.links.length === 0) {
          onClose();
          void navigate(searchHref(reading.name));
          return;
        }
        visit(reading.links, text, related);
      } else if (reading.intent === 'person') {
        const [only, ...others] = reading.people;
        if (only && others.length === 0) {
          onClose();
          void navigate(`/contacts/${only.id}`);
          return;
        }
        const people = reading.people.map((person) => ({
          id: `contact-${person.id}`,
          label: person.name,
          icon: ContactRound,
          disabled: false,
          run: () => void navigate(`/contacts/${person.id}`),
        }));
        setStage({
          name: 'heard',
          text,
          related: [...people, ...related],
          unread: only ? undefined : t('speech.noPerson').replace('{name}', reading.name),
        });
      } else if (reading.intent === 'help') {
        const articles = reading.articles.map((article) => ({
          id: `help-${article.id}`,
          label: article.title,
          icon: CircleHelp,
          disabled: false,
          run: () => void navigate(`/help/${article.id}`),
        }));
        setStage({
          name: 'heard',
          text,
          related: [...articles, ...related],
          unread: articles.length ? undefined : t('speech.noHelp'),
        });
      } else if (reading.intent === 'search') {
        onClose();
        void navigate(searchHref(translatedQuery(reading, t) || text));
      } else if (reading.intent === 'document') {
        onClose();
        void navigate(
          `/documents?${new URLSearchParams({ create: 'document', title: reading.title })}`,
        );
      } else if (reading.intent === 'mail') {
        const mine = accounts.data?.accounts ?? [];
        const said = mine.find((account) => account.address === reading.account);
        const sender = said ?? mine.find((account) => account.default) ?? mine[0];
        if (!sender) {
          setStage({ name: 'heard', text, related, unread: t('speech.noAccount') });
          return;
        }
        Promise.all(reading.to.map(addressee)).then(
          (to) =>
            setStage({
              name: 'mail',
              start: {
                account: sender.id,
                chosen: Boolean(said),
                to: to.filter((person) => person !== undefined),
                subject: reading.subject,
                text: reading.text,
              },
            }),
          unread,
        );
      } else {
        setStage({ name: 'heard', text, related, reading });
      }
    }, unread);
  };

  if (stage?.name === 'mail') {
    return (
      <Suspense>
        <Compose accounts={accounts.data?.accounts ?? []} start={stage.start} onClose={onClose} />
      </Suspense>
    );
  }

  if (stage?.name === 'heard' && editing === 'event' && stage.reading?.intent === 'event') {
    const { reading } = stage;
    return (
      <EventDialog
        calendars={(calendars.data?.calendars ?? []).filter((each) => !each.read_only)}
        start={{
          day: reading.day,
          time: reading.time,
          allDay: reading.all_day ?? !reading.time,
          endDay: reading.end_day,
          endTime: reading.end_time,
          summary: reading.summary,
          location: reading.location,
          description: stage.text,
        }}
        onClose={onClose}
      />
    );
  }

  if (stage?.name === 'heard' && editing === 'task' && stage.reading?.intent === 'task') {
    return (
      <TaskDialog draft={{ text: stage.reading.text, due: stage.reading.due }} onClose={onClose} />
    );
  }

  if (stage?.name === 'heard') {
    const { reading } = stage;
    const proposed =
      reading?.intent === 'event'
        ? {
            icon: CalendarPlus,
            label: t('speech.toEvent'),
            what: reading.summary,
            when: `${formatDays(reading.day, reading.end_day ?? reading.day)}${reading.time ? ` ${reading.time}` : ''}${reading.end_time ? `–${reading.end_time}` : ''}`,
            run: () => setEditing('event'),
            disabled: !calendars.data?.calendars.some((each) => !each.read_only),
          }
        : reading?.intent === 'task'
          ? {
              icon: ListTodo,
              label: t('speech.toTask'),
              what: reading.text,
              when: reading.due ? formatDays(reading.due, reading.due) : '',
              run: () => setEditing('task'),
              disabled: false,
            }
          : null;
    const keep = (
      <button
        type="button"
        disabled={note.isPending || !stage.text.trim()}
        onClick={() => note.mutate({ text: stage.text })}
        className={proposed ? button : primaryButton}
      >
        <StickyNote size={16} aria-hidden />
        {t('speech.toNote')}
      </button>
    );
    return (
      <Modal heading={t('speech.heard')} onClose={onClose}>
        <textarea
          aria-label={t('speech.text')}
          value={stage.text}
          onChange={(event) => setStage({ ...stage, text: event.target.value })}
          rows={Math.min(8, Math.max(3, Math.ceil(stage.text.length / 60)))}
          className={field}
        />
        {proposed && (
          <section
            aria-label={t('speech.proposed')}
            className="flex items-center gap-3 rounded-lg border border-line p-3"
          >
            <proposed.icon size={20} aria-hidden className="shrink-0 text-accent" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{proposed.what}</p>
              {proposed.when && <p className="text-sm text-muted">{proposed.when}</p>}
            </div>
          </section>
        )}
        {stage.unread && <p className="text-sm text-danger">{stage.unread}</p>}
        {stage.related.length > 0 && (
          <ul aria-label={t('speech.commands')} className="flex flex-col gap-1">
            {stage.related.map((choice) => (
              <li key={choice.id}>
                <button
                  type="button"
                  onClick={() => {
                    onClose();
                    choice.run();
                  }}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-hover"
                >
                  <choice.icon size={16} aria-hidden className="text-muted" />
                  {choice.label}
                </button>
              </li>
            ))}
          </ul>
        )}
        {note.isError && <p className="text-sm text-danger">{errorMessage(note.error, t)}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <Cancel />
          {keep}
          {proposed && (
            <button
              type="button"
              disabled={proposed.disabled}
              title={proposed.disabled ? t('speech.noCalendar') : undefined}
              onClick={proposed.run}
              className={primaryButton}
            >
              <proposed.icon size={16} aria-hidden />
              {proposed.label}
            </button>
          )}
        </div>
      </Modal>
    );
  }

  return (
    <RecordingModal recording={recording} reading={stage?.name === 'reading'} onClose={onClose} />
  );
}

function DictateDialog({
  onText,
  onClose,
}: {
  onText: (text: string) => void;
  onClose: () => void;
}) {
  const recording = useRecording((text) => {
    onText(text);
    onClose();
  });
  return <RecordingModal recording={recording} onClose={onClose} />;
}

/** The microphone beside a field: what is said is written into it, nothing more. */
export function DictateButton({ onText }: { onText: (text: string) => void }) {
  const { t } = useI18n();
  const speech = useSpeech();
  const [open, setOpen] = useState(false);
  const off = speech.isSuccess && !speech.data.enabled;
  const ready = speech.isSuccess && !off;
  return (
    <>
      <button
        type="button"
        aria-label={t('speech.dictate')}
        title={off ? t('speech.off') : t('speech.dictate')}
        disabled={!ready}
        onClick={() => setOpen(true)}
        className={button}
      >
        <Mic size={16} aria-hidden />
      </button>
      {open &&
        ready &&
        (speech.data.given_at ? (
          <DictateDialog onText={onText} onClose={() => setOpen(false)} />
        ) : (
          <ConsentDialog onClose={() => setOpen(false)} />
        ))}
    </>
  );
}

function wantsVoice(event: KeyboardEvent): boolean {
  return (
    !event.defaultPrevented &&
    event.altKey &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey &&
    event.code === 'KeyM'
  );
}

/** The microphone beside the search box on every page, and Alt+M: what is said runs a command
 * or becomes a note. `?voice` in the address opens it, as the launcher shortcut does. */
export function VoiceButton() {
  const { t } = useI18n();
  const speech = useSpeech();
  const [params, setParams] = useSearchParams();
  const open = params.has('voice');
  const off = speech.isSuccess && !speech.data.enabled;
  const ready = speech.isSuccess && !off;

  const setOpen = useRef<(open: boolean) => void>(() => {});
  setOpen.current = (wanted) =>
    setParams(
      (now) => {
        const next = new URLSearchParams(now);
        if (wanted) next.set('voice', '');
        else next.delete('voice');
        return next;
      },
      { replace: !wanted },
    );

  useEffect(() => {
    function listen(event: KeyboardEvent) {
      if (!wantsVoice(event) || !ready) return;
      event.preventDefault();
      setOpen.current(true);
    }
    window.addEventListener('keydown', listen);
    return () => window.removeEventListener('keydown', listen);
  }, [ready]);

  return (
    <>
      <button
        type="button"
        aria-label={t('speech.say')}
        title={off ? t('speech.off') : `${t('speech.say')} (Alt+M)`}
        disabled={!ready}
        onClick={() => setOpen.current(true)}
        className="shrink-0 rounded-full bg-ai-soft p-1.5 text-ai hover:ring-1 hover:ring-ai disabled:opacity-40 disabled:hover:ring-0"
      >
        <Mic size={18} aria-hidden />
      </button>
      {open &&
        ready &&
        (speech.data.given_at ? (
          <VoiceDialog
            understands={speech.data.understands}
            onClose={() => setOpen.current(false)}
          />
        ) : (
          <ConsentDialog onClose={() => setOpen.current(false)} />
        ))}
    </>
  );
}
