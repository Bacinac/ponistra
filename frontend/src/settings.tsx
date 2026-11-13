import {
  Archive,
  AtSign,
  Bell,
  Bot,
  CalendarOff,
  DoorOpen,
  Fingerprint,
  HardDrive,
  HeartPulse,
  KeyRound,
  KeySquare,
  Languages,
  LogIn,
  Mail,
  MailX,
  MonitorSmartphone,
  ScrollText,
  Sparkles,
  Users,
  Video,
  X,
  type LucideIcon,
  Plane,
  Receipt,
} from 'lucide-react';
import { Suspense, type ComponentType, type ReactNode } from 'react';
import { Link, Navigate, NavLink, useParams } from 'react-router';
import { useSession } from './auth';
import { Frame, Loading, useWide } from './frame';
import { AwaySettings } from './away';
import { useI18n } from './i18n';
import { lazily } from './lazily';
import type { MessageKey } from './i18n/hr';
import { iconButton, sideRow } from './styles';

const Agents = lazily(() => import('./agents'), 'Agents');
const AppPasswords = lazily(() => import('./appPasswords'), 'AppPasswords');
const Collections = lazily(() => import('./collections'), 'Collections');
const Consents = lazily(() => import('./consents'), 'Consents');
const Devices = lazily(() => import('./devices'), 'Devices');
const DriveSettings = lazily(() => import('./drive'), 'DriveSettings');
const MailAccounts = lazily(() => import('./mail'), 'MailAccounts');
const MailSettings = lazily(() => import('./mail'), 'MailSettings');
const Notifications = lazily(() => import('./notifications'), 'Notifications');
const Passkeys = lazily(() => import('./passkeys'), 'Passkeys');
const PasswordForm = lazily(() => import('./auth'), 'PasswordForm');
const SignInChoice = lazily(() => import('./auth'), 'SignInChoice');
const ReadingLanguages = lazily(() => import('./translation'), 'ReadingLanguages');

interface Entry {
  to: string;
  icon: LucideIcon;
  title: MessageKey;
}

export const ACCOUNT: { heading: MessageKey; entries: (Entry & { body: ComponentType })[] }[] = [
  {
    heading: 'settings.signIn',
    entries: [
      { to: '/settings/sign-in', icon: LogIn, title: 'signIn.choice', body: SignInChoice },
      { to: '/settings/password', icon: KeyRound, title: 'password.title', body: PasswordForm },
      { to: '/settings/passkeys', icon: Fingerprint, title: 'passkeys.title', body: Passkeys },
      {
        to: '/settings/app-passwords',
        icon: KeySquare,
        title: 'appPasswords.title',
        body: AppPasswords,
      },
    ],
  },
  {
    heading: 'settings.devices',
    entries: [
      { to: '/settings/devices', icon: MonitorSmartphone, title: 'devices.mine', body: Devices },
      {
        to: '/settings/notifications',
        icon: Bell,
        title: 'notifications.title',
        body: Notifications,
      },
    ],
  },
  {
    heading: 'settings.mail',
    entries: [
      { to: '/settings/mail-accounts', icon: AtSign, title: 'mail.accounts', body: MailAccounts },
      { to: '/settings/senders', icon: MailX, title: 'mail.senders', body: MailSettings },
      { to: '/settings/away', icon: Plane, title: 'away.title', body: AwaySettings },
      { to: '/settings/collections', icon: Receipt, title: 'collections.title', body: Collections },
    ],
  },
  {
    heading: 'settings.leaving',
    entries: [
      { to: '/settings/google', icon: HardDrive, title: 'drive.title', body: DriveSettings },
    ],
  },
  {
    heading: 'settings.ai',
    entries: [
      { to: '/settings/agents', icon: Bot, title: 'agents.title', body: Agents },
      { to: '/settings/ai', icon: Sparkles, title: 'consents.title', body: Consents },
      {
        to: '/settings/translation',
        icon: Languages,
        title: 'translation.title',
        body: ReadingLanguages,
      },
    ],
  },
];

const PAGES = ACCOUNT.flatMap(({ entries }) => entries);

export const INSTALLATION: Entry[] = [
  { to: '/users', icon: Users, title: 'users.title' },
  { to: '/resources', icon: DoorOpen, title: 'resources.title' },
  { to: '/workdays', icon: CalendarOff, title: 'workdays.title' },
  { to: '/meetings', icon: Video, title: 'relay.title' },
  { to: '/providers', icon: Mail, title: 'providers.title' },
  { to: '/applications', icon: LogIn, title: 'identity.title' },
  { to: '/ai', icon: Sparkles, title: 'ai.title' },
  { to: '/retention', icon: Archive, title: 'retention.title' },
  { to: '/journal', icon: ScrollText, title: 'journal.title' },
  { to: '/health', icon: HeartPulse, title: 'health.title' },
];

function Group({ heading, entries }: { heading: string; entries: Entry[] }) {
  const { t } = useI18n();
  return (
    <section className="flex flex-col gap-0.5">
      <h2 className="px-2 text-xs font-semibold text-muted uppercase">{heading}</h2>
      {entries.map(({ to, icon: Icon, title }) => (
        <NavLink key={to} to={to} className={sideRow}>
          <Icon size={16} aria-hidden className="shrink-0" />
          <span className="truncate">{t(title)}</span>
        </NavLink>
      ))}
    </section>
  );
}

function Side() {
  const { t } = useI18n();
  const admin = useSession().data?.user?.is_admin;
  return (
    <nav aria-label={t('settings.title')} className="flex flex-col gap-4">
      {ACCOUNT.map(({ heading, entries }) => (
        <Group key={heading} heading={t(heading)} entries={entries} />
      ))}
      {admin && <Group heading={t('settings.installation')} entries={INSTALLATION} />}
    </nav>
  );
}

/** The frame of every page of the settings: the user's own and the installation's. On a phone
    the list of them is a page of its own, which each closes back to. */
export function SettingsFrame({
  title,
  actions,
  primary,
  more,
  children,
}: {
  title: string;
  actions?: ReactNode;
  primary?: ReactNode;
  more?: ReactNode;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const wide = useWide();
  return (
    <Frame
      title={title}
      folders={false}
      side={wide ? <Side /> : undefined}
      actions={actions}
      primary={primary}
      more={more}
    >
      {!wide && (
        <Link
          to="/settings"
          aria-label={t('frame.close')}
          className={`${iconButton} mb-2 inline-flex`}
        >
          <X size={16} aria-hidden />
        </Link>
      )}
      {children}
    </Frame>
  );
}

export function SettingsPage() {
  const { t } = useI18n();
  const wide = useWide();
  const section = useParams().section;
  const page = PAGES.find((each) => each.to === `/settings/${section}`);
  if (!section && !wide)
    return (
      <Frame title={t('settings.title')} folders={false}>
        <Side />
      </Frame>
    );
  if (!page) return <Navigate to={PAGES[0].to} replace />;
  const Body = page.body;
  return (
    <SettingsFrame title={t(page.title)}>
      <div className="flex w-full max-w-3xl flex-col gap-4">
        <Suspense fallback={<Loading />}>
          <Body />
        </Suspense>
      </div>
    </SettingsFrame>
  );
}
