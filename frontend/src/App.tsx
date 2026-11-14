import { Component, type ErrorInfo, type ReactNode, Suspense, useEffect } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router';
import { unavailable } from './api';
import { LoginForm, PasskeyDue, SetupForm, useSession } from './auth';
import { forgetDoor, rememberedDoor } from './door';
import { Loading, Lobby, Shell } from './frame';
import { BESIDE } from './workspace';
import { queriesTrail, reportCrash } from './crashes';
import { useFollowed } from './followed';
import { useI18n } from './i18n';
import { lazily } from './lazily';
import { usePushBridge } from './notifications';
import { JobBar } from './jobs';
import { LaunchesElsewhere } from './launch';
import { recoverFromCrash, takeNewRelease } from './release';
import { Ringing } from './ringing';
import { VaultProvider } from './vault/state';

const AiPage = lazily(() => import('./ai'), 'AiPage');
const ApplicationsPage = lazily(() => import('./identity'), 'ApplicationsPage');
const AuthorizePage = lazily(() => import('./identity'), 'AuthorizePage');
const CalendarPage = lazily(() => import('./calendar'), 'CalendarPage');
const ChatPage = lazily(() => import('./ChatPage'), 'ChatPage');
const CompanyPage = lazily(() => import('./FolderPage'), 'CompanyPage');
const ConnectPage = lazily(() => import('./phoneApp'), 'ConnectPage');
const ConsentPage = lazily(() => import('./agents'), 'ConsentPage');
const ContactsPage = lazily(() => import('./contacts'), 'ContactsPage');
const DocumentPage = lazily(() => import('./DocumentPage'), 'DocumentPage');
const FilePage = lazily(() => import('./FilePage'), 'FilePage');
const FolderPage = lazily(() => import('./FolderPage'), 'FolderPage');
const GuestMeetingPage = lazily(() => import('./guest'), 'GuestMeetingPage');
const OutsidePage = lazily(() => import('./outside'), 'OutsidePage');
const VisitPage = lazily(() => import('./outside'), 'VisitPage');
const HealthPage = lazily(() => import('./health'), 'HealthPage');
const JournalPage = lazily(() => import('./journal'), 'JournalPage');
const HelpPage = lazily(() => import('./help'), 'HelpPage');
const LinksPage = lazily(() => import('./links'), 'LinksPage');
const StartPage = lazily(() => import('./links'), 'StartPage');
const MailPage = lazily(() => import('./mail'), 'MailPage');
const MeetingPage = lazily(() => import('./MeetingPage'), 'MeetingPage');
const NotesPage = lazily(() => import('./notes'), 'NotesPage');
const PresentPage = lazily(() => import('./PresentPage'), 'PresentPage');
const PrintPage = lazily(() => import('./PrintPage'), 'PrintPage');
const ProvidersPage = lazily(() => import('./providers'), 'ProvidersPage');
const RelayPage = lazily(() => import('./relay'), 'RelayPage');
const ResourcesPage = lazily(() => import('./resources'), 'ResourcesPage');
const RetentionPage = lazily(() => import('./retention'), 'RetentionPage');
const SearchPage = lazily(() => import('./SearchPage'), 'SearchPage');
const SettingsPage = lazily(() => import('./settings'), 'SettingsPage');
const AdminPage = lazily(() => import('./settings'), 'AdminPage');
const SharedPage = lazily(() => import('./FolderPage'), 'SharedPage');
const FavouritesPage = lazily(() => import('./FolderPage'), 'FavouritesPage');
const BoardsPage = lazily(() => import('./FolderPage'), 'BoardsPage');
const WorkspacePage = lazily(() => import('./WorkspacePage'), 'WorkspacePage');
const WorkspaceBeside = lazily(() => import('./WorkspacePage'), 'WorkspaceBeside');
const SharingPage = lazily(() => import('./sharing'), 'SharingPage');
const SlidesPrintPage = lazily(() => import('./PrintPage'), 'SlidesPrintPage');
const TasksPage = lazily(() => import('./tasks'), 'TasksPage');
const TodayPage = lazily(() => import('./TodayPage'), 'TodayPage');
const TrashPage = lazily(() => import('./TrashPage'), 'TrashPage');
const UsersPage = lazily(() => import('./users'), 'UsersPage');
const VaultPage = lazily(() => import('./vault/page'), 'VaultPage');
const VersionPage = lazily(() => import('./versions'), 'VersionPage');
const WorkdaysPage = lazily(() => import('./workdays'), 'WorkdaysPage');

interface CrashProps {
  /** Where the user is; leaving it clears the error. */
  at: string;
  message: string;
  className: string;
  children: ReactNode;
}

class Crash extends Component<CrashProps, { error: Error | null; at: string }> {
  state = { error: null as Error | null, at: this.props.at };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  static getDerivedStateFromProps(props: CrashProps, state: { at: string }) {
    return props.at === state.at ? null : { error: null, at: props.at };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportCrash({
      path: this.props.at,
      message: error.message,
      stack: error.stack ?? '',
      components: info.componentStack ?? '',
      queries: queriesTrail(),
    });
    recoverFromCrash();
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        role="alert"
        className={`flex items-center justify-center bg-surface p-4 ${this.props.className}`}
      >
        <p className="text-danger">
          {this.props.message}: {this.state.error.message}
        </p>
      </div>
    );
  }
}

function PushBridge() {
  usePushBridge(useNavigate());
  return null;
}

function Followed() {
  useFollowed();
  return null;
}

export default function App() {
  const { t } = useI18n();
  const { pathname } = useLocation();
  const session = useSession();
  const unprintable =
    pathname.startsWith('/print/') &&
    (session.isError || (session.isSuccess && !session.data.user));

  useEffect(takeNewRelease, [pathname]);

  useEffect(() => {
    if (unprintable) void import('./PrintPage').then(({ unprinted }) => unprinted());
  }, [unprintable]);

  if (pathname === '/connect') return <ConnectPage />;
  if (session.isPending) return <div className="min-h-dvh bg-surface" />;
  if (session.isError) {
    return (
      <Lobby>
        {unavailable(session.error) ? (
          <p role="status" className="flex items-center gap-2 text-muted">
            <LoaderCircle aria-hidden className="size-4 shrink-0 animate-spin" />
            {t('status.away')}
          </p>
        ) : (
          <p className="text-danger">
            {t('status.down')}: {session.error.message}
          </p>
        )}
      </Lobby>
    );
  }
  if ((pathname.startsWith('/o/') || pathname.startsWith('/v/')) && !session.data.setup) {
    return (
      <Crash at={pathname} message={t('error.unexpected')} className="min-h-dvh">
        <Routes>
          <Route path="/o/:token" element={<OutsidePage />} />
          <Route path="/v/:key" element={<VisitPage />} />
        </Routes>
      </Crash>
    );
  }
  if (!session.data.user) {
    if (pathname.startsWith('/meet/') && pathname !== '/meet/new' && !session.data.setup) {
      return (
        <Crash at={pathname} message={t('error.unexpected')} className="min-h-dvh">
          <Routes>
            <Route path="/meet/:id" element={<GuestMeetingPage />} />
          </Routes>
        </Crash>
      );
    }
    const door = rememberedDoor();
    if (door && !session.data.setup) return <Navigate to={door} replace />;
    return <Lobby>{session.data.setup ? <SetupForm /> : <LoginForm />}</Lobby>;
  }
  if (!session.data.user.visitor) forgetDoor();
  if (session.data.passkey_due) {
    return (
      <Lobby>
        <PasskeyDue />
      </Lobby>
    );
  }
  if (session.data.user.visitor) {
    return (
      <Crash at={pathname} message={t('error.unexpected')} className="min-h-dvh">
        <Shell>
          <Crash at={pathname} message={t('error.unexpected')} className="h-full">
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/shared" element={<SharedPage />} />
                <Route path="/f/:folder" element={<FolderPage />} />
                <Route path="/d/:node" element={<DocumentPage />} />
                <Route path="/d/:node/:tab" element={<DocumentPage />} />
                <Route path="/d/:node/versions/:version/:tab?" element={<VersionPage />} />
                <Route path="/p/:node" element={<FilePage />} />
                <Route path="/help/:section?/:article?" element={<HelpPage />} />
                <Route path="*" element={<Navigate to="/shared" replace />} />
              </Routes>
            </Suspense>
          </Crash>
        </Shell>
        <JobBar />
      </Crash>
    );
  }
  if (pathname === '/agents/consent') {
    return <ConsentPage />;
  }
  if (pathname === '/authorize') {
    return <AuthorizePage />;
  }
  if (pathname === BESIDE) {
    return (
      <Crash at={pathname} message={t('error.unexpected')} className="min-h-dvh">
        <Suspense fallback={<Loading />}>
          <WorkspaceBeside />
        </Suspense>
        <PushBridge />
      </Crash>
    );
  }
  if (pathname === '/start') {
    return (
      <Crash at={pathname} message={t('error.unexpected')} className="min-h-dvh">
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/start" element={<StartPage />} />
          </Routes>
        </Suspense>
        <Followed />
        <PushBridge />
      </Crash>
    );
  }
  if (pathname.startsWith('/meet/')) {
    return (
      <Crash at={pathname} message={t('error.unexpected')} className="min-h-dvh">
        <Routes>
          <Route path="/meet/:id" element={<MeetingPage />} />
        </Routes>
        <Followed />
        <Ringing />
        <PushBridge />
        <LaunchesElsewhere />
      </Crash>
    );
  }
  if (pathname.startsWith('/print/') || pathname.startsWith('/present/')) {
    return (
      <Crash at={pathname} message={t('error.unexpected')} className="min-h-dvh">
        <Routes>
          <Route path="/print/:node" element={<PrintPage />} />
          <Route path="/print/:node/slides" element={<SlidesPrintPage />} />
          <Route path="/present/:node" element={<PresentPage />} />
        </Routes>
        {pathname.startsWith('/present/') && <LaunchesElsewhere />}
      </Crash>
    );
  }
  return (
    <Crash at={pathname} message={t('error.unexpected')} className="min-h-dvh">
      <VaultProvider>
        <Shell>
          <Crash at={pathname} message={t('error.unexpected')} className="h-full">
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route path="/" element={<TodayPage />} />
                <Route path="/documents" element={<FolderPage />} />
                <Route path="/f/:folder" element={<FolderPage />} />
                <Route path="/d/:node" element={<DocumentPage />} />
                <Route path="/d/:node/:tab" element={<DocumentPage />} />
                <Route path="/d/:node/versions/:version/:tab?" element={<VersionPage />} />
                <Route path="/p/:node" element={<FilePage />} />
                <Route path="/notes" element={<NotesPage />} />
                <Route path="/links" element={<LinksPage />} />
                <Route path="/boards" element={<BoardsPage />} />
                <Route path="/workspace" element={<WorkspacePage />} />
                <Route path="/search" element={<SearchPage />} />
                <Route path="/help/:section?/:article?" element={<HelpPage />} />
                <Route path="/company" element={<CompanyPage />} />
                <Route path="/shared" element={<SharedPage />} />
                <Route path="/favourites" element={<FavouritesPage />} />
                <Route path="/share" element={<SharingPage />} />
                <Route path="/trash" element={<TrashPage />} />
                <Route path="/users" element={<UsersPage />} />
                <Route path="/resources" element={<ResourcesPage />} />
                <Route path="/retention" element={<RetentionPage />} />
                <Route path="/workdays" element={<WorkdaysPage />} />
                <Route path="/tasks" element={<TasksPage />} />
                <Route path="/ai" element={<AiPage />} />
                <Route path="/providers" element={<ProvidersPage />} />
                <Route path="/meetings" element={<RelayPage />} />
                <Route path="/applications" element={<ApplicationsPage />} />
                <Route path="/health" element={<HealthPage />} />
                <Route path="/journal" element={<JournalPage />} />
                <Route path="/settings/:section?" element={<SettingsPage />} />
                <Route path="/admin" element={<AdminPage />} />
                <Route path="/mail" element={<MailPage />} />
                <Route path="/mail/:folder" element={<MailPage />} />
                <Route path="/mail/:folder/:message" element={<MailPage />} />
                <Route path="/contacts/:contact?" element={<ContactsPage />} />
                <Route path="/chat/:conversation?" element={<ChatPage />} />
                <Route path="/calendar/:view?/:date?" element={<CalendarPage />} />
                <Route path="/vault/:collection?/:item?" element={<VaultPage />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </Suspense>
          </Crash>
        </Shell>
      </VaultProvider>
      <JobBar />
      <Ringing />
      <PushBridge />
    </Crash>
  );
}
