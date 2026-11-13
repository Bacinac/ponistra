import { BookUser, Video } from 'lucide-react';
import { Navigate, NavLink, useParams } from 'react-router';
import {
  Channels,
  ConversationPage,
  Conversations,
  NewConversation,
  lastConversation,
  nameOf,
  useShown,
  useSummary,
} from './chat';
import { Frame, useWide } from './frame';
import { useI18n } from './i18n';
import { useLive } from './live';
import { useMeetingWindow } from './meetingWindow';
import { button, sideRow } from './styles';

export function ChatPage() {
  const { t } = useI18n();
  const meetingWindow = useMeetingWindow();
  const wide = useWide();
  const id = useParams().conversation ?? null;
  const summary = useSummary(id ?? '');
  const opened = useShown(id ?? '', id !== null && !summary);
  const { conversations } = useLive();
  const last = id === null && wide ? lastConversation() : null;
  if (last && conversations.some((each) => each.id === last))
    return <Navigate to={`/chat/${last}`} replace />;
  const list = (
    <div className="flex flex-col gap-0.5">
      <Conversations current={id} />
      <div className="my-2 h-px bg-line" />
      <Channels />
      <NavLink to="/contacts" className={sideRow}>
        <BookUser size={16} aria-hidden className="shrink-0 text-muted" />
        {t('rail.contacts')}
      </NavLink>
    </div>
  );
  return (
    <Frame
      title={summary ? nameOf(summary, t) : opened.data?.title || t('rail.chat')}
      folders={false}
      actions={
        <button type="button" onClick={() => meetingWindow.open('/meet/new')} className={button}>
          <Video size={16} aria-hidden />
          <span className="sr-only sm:not-sr-only">{t('meeting.now')}</span>
        </button>
      }
      primary={<NewConversation />}
      side={wide ? list : undefined}
    >
      {id !== null ? (
        <ConversationPage key={id} id={id} />
      ) : (
        !wide && <div className="w-full max-w-3xl">{list}</div>
      )}
    </Frame>
  );
}
