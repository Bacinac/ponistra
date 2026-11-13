import { useQuery, useQueryClient } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { lazy, Suspense, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router';
import { getJson, postJson } from './api';
import { Loading } from './frame';
import { useI18n } from './i18n';
import type { Meeting } from './meeting';
import { useMeetingName } from './meetingWindow';
import { useThemeOf } from './theme';
import { iconButton } from './styles';
import { useTitle } from './title';
import { errorMessage } from './tree';

const Call = lazy(() => import('./call'));

export interface Shown extends Meeting {
  /** The names of those in the meeting now. */
  present: string[];
  /** Whether an event plans it, asking people through its attendees. */
  planned: boolean;
}

/** A meeting's own page, the whole window: before joining, in the call, and after leaving. */
export function MeetingPage() {
  const id = useParams().id ?? '';
  const location = useLocation();
  // A meeting made now keeps its page, camera and choices included, as it takes its address.
  const page = location.state?.made ?? (id === 'new' ? location.key : id);
  const { t } = useI18n();
  const [blocked, setBlocked] = useState(location.state?.blocked === true);
  useMeetingName(id);
  useThemeOf('meetings');
  return (
    <div className="flex h-dvh flex-col bg-surface text-ink">
      {blocked && (
        <div
          role="alert"
          className="flex items-center gap-2 border-b border-line bg-panel px-4 py-2"
        >
          <p className="flex-1 text-sm">{t('meeting.blocked')}</p>
          <button
            type="button"
            onClick={() => setBlocked(false)}
            aria-label={t('frame.close')}
            className={iconButton}
          >
            <X size={16} aria-hidden />
          </button>
        </div>
      )}
      <Joinable key={page} id={id} />
    </div>
  );
}

/** A meeting made now is made once it is used, joined or asked people into: left before that,
    it leaves nothing behind. */
function useMade(): () => Promise<Shown> {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { key } = useLocation();
  const making = useRef<Promise<Shown> | null>(null);
  return () => {
    making.current ??= postJson<Meeting>('/api/meetings').then(
      (made) => {
        const shown = { ...made, present: [], planned: false };
        queryClient.setQueryData(['meeting', made.id], shown);
        navigate(`/meet/${made.id}`, { replace: true, state: { made: key } });
        return shown;
      },
      (error: Error) => {
        making.current = null;
        throw error;
      },
    );
    return making.current;
  };
}

const UNMADE: Shown = {
  id: '',
  title: '',
  link: '',
  conversation: '',
  present: [],
  planned: false,
};

function Joinable({ id }: { id: string }) {
  const { t } = useI18n();
  const unmade = id === 'new';
  const make = useMade();
  // Who is in is asked again only until the user is in too.
  const [inside, setInside] = useState(false);
  const shown = useQuery({
    queryKey: ['meeting', id],
    queryFn: () => getJson<Shown>(`/api/meetings/${id}`),
    enabled: !unmade,
    refetchInterval: inside ? false : 5000,
  });
  const meeting = unmade ? UNMADE : shown.data;
  const title = meeting && (meeting.title || t('meeting.untitled'));
  useTitle(title);
  if (shown.error) return <Trouble error={shown.error} />;
  if (!meeting) return <Centered />;
  return (
    <Suspense fallback={<Centered />}>
      <Call meeting={meeting} make={unmade ? make : undefined} onInside={setInside} />
    </Suspense>
  );
}

function Centered() {
  return (
    <div className="m-auto">
      <Loading />
    </div>
  );
}

function Trouble({ error }: { error: Error }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  return (
    <div className="m-auto flex max-w-md flex-col items-start gap-3 p-4">
      <p className="text-danger">{errorMessage(error, t)}</p>
      <button type="button" onClick={() => navigate('/')} className="text-sm underline">
        {t('meeting.back')}
      </button>
    </div>
  );
}
