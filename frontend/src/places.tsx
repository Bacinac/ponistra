import {
  BookUser,
  CircleHelp,
  FilePlus,
  Globe,
  Languages,
  ListTodo,
  LogOut,
  MailPlus,
  Settings,
  FolderKanban,
  LayoutDashboard,
  StickyNote,
  SunMoon,
  Video,
  Trash2,
  Vault,
  type LucideIcon,
  Star,
} from 'lucide-react';
import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useLogout, useSession } from './auth';
import { MODULES } from './modules';
import { LANGUAGE_NAMES, LANGUAGES, useI18n } from './i18n';
import type { MessageKey } from './i18n/hr';
import { useNewNote } from './notes';
import type { Choice, Palette } from './palette';
import { ACCOUNT, INSTALLATION } from './settings';
import {
  choosePageTheme,
  chooseTheme,
  PAGE_THEMES,
  type Page,
  usePageTheme,
  THEMES,
  useTheme,
} from './theme';
import { fold } from './vault/search';
import { useReachable } from './live';
import { useGoToProjects } from './workspace';

/** Every part of the suite one goes to by name: the modules, and the places within them a user
    asks for by their own. */
export const PLACES: { id: string; icon: LucideIcon; to: string; label: MessageKey }[] = [
  ...MODULES.map(({ id, icon, to }) => ({ id, icon, to, label: `rail.${id}` as MessageKey })),
  { id: 'contacts', icon: BookUser, to: '/contacts', label: 'rail.contacts' },
  { id: 'favourites', icon: Star, to: '/favourites', label: 'favourites.title' },
  { id: 'notes', icon: StickyNote, to: '/notes', label: 'notes.title' },
  { id: 'links', icon: Globe, to: '/links', label: 'links.title' },
  { id: 'boards', icon: LayoutDashboard, to: '/boards', label: 'boards.title' },
  { id: 'vault', icon: Vault, to: '/vault', label: 'vault.title' },
  { id: 'tasks', icon: ListTodo, to: '/tasks', label: 'tasks.title' },
  { id: 'trash', icon: Trash2, to: '/trash', label: 'trash.title' },
  { id: 'settings', icon: Settings, to: '/settings', label: 'settings.title' },
  { id: 'help', icon: CircleHelp, to: '/help', label: 'help.title' },
];

/** The commands the search box offers on every page beside what the page's own palette
    gives: going to a part of the suite or, to its owner, the code workspace, a new note, message or document, a setting of the account or, to an administrator, of the installation,
    the theme, the language and signing out. The pages' own choices come first. */
export function usePlaces(): Palette {
  const { t, language, setLanguage } = useI18n();
  const theme = useTheme();
  const projectsTheme = usePageTheme('projects');
  const meetingsTheme = usePageTheme('meetings');
  const navigate = useNavigate();
  const goToProjects = useGoToProjects();
  const user = useSession().data?.user;
  const admin = user?.is_admin ?? false;
  const owner = Boolean(user?.workspace);
  const logout = useLogout();
  const newNote = useNewNote();
  const reachable = useReachable();
  return useCallback(
    (query: string): Choice[] => {
      const wanted = fold(query.trim());
      const note: Choice = {
        id: 'newNote',
        label: t('notes.new'),
        icon: StickyNote,
        disabled: newNote.isPending || !reachable,
        run: () => newNote.mutate({}),
      };
      const made: Choice[] = [
        {
          id: 'newMessage',
          label: t('mail.compose'),
          icon: MailPlus,
          disabled: false,
          run: () => navigate('/mail?compose'),
        },
        {
          id: 'newDocument',
          label: t('tree.newDocument'),
          icon: FilePlus,
          disabled: !reachable,
          run: () => navigate('/documents?create=document'),
        },
      ];
      const places = PLACES.map(({ id, icon, to, label }): Choice => ({
        id: `go:${id}`,
        label: `${t('places.open')}: ${t(label)}`,
        icon,
        disabled: false,
        run: () => navigate(to),
      }));
      const projects: Choice[] = owner
        ? [
            {
              id: 'go:projects',
              label: `${t('places.open')}: ${t('rail.projects')}`,
              icon: FolderKanban,
              disabled: false,
              run: goToProjects,
            },
          ]
        : [];
      const settings = [
        ...ACCOUNT.filter(({ owner: only }) => !only || owner).flatMap(({ entries }) =>
          entries.map((entry) => ({ entry, heading: t('settings.title') })),
        ),
        ...(admin
          ? INSTALLATION.map((entry) => ({ entry, heading: t('settings.installation') }))
          : []),
      ].map(({ entry, heading }): Choice => ({
        id: `place:${entry.to}`,
        label: `${heading}: ${t(entry.title)}`,
        icon: entry.icon,
        disabled: false,
        run: () => navigate(entry.to),
      }));
      const themes = THEMES.map((value): Choice => ({
        id: `theme:${value}`,
        label: `${t('frame.theme')}: ${t(`frame.theme.${value}`)}`,
        icon: SunMoon,
        disabled: value === theme,
        run: () => chooseTheme(value),
      }));
      const pageThemes = (
        [
          ['projects', FolderKanban, projectsTheme],
          ['meetings', Video, meetingsTheme],
        ] as const
      )
        .filter(([page]) => owner || page !== 'projects')
        .flatMap(([page, icon, now]: readonly [Page, LucideIcon, string]) =>
          PAGE_THEMES.map((value): Choice => ({
            id: `theme:${page}:${value}`,
            label: `${t(`frame.theme.${page}`)}: ${t(`frame.theme.${value}`)}`,
            icon,
            disabled: value === now,
            run: () => choosePageTheme(page, value),
          })),
        );
      const languages = LANGUAGES.map((code): Choice => ({
        id: `language:${code}`,
        label: `${t('frame.language')}: ${LANGUAGE_NAMES[code]}`,
        icon: Languages,
        disabled: code === language,
        run: () => setLanguage(code),
      }));
      const out: Choice = {
        id: 'signOut',
        label: t('auth.signOut'),
        icon: LogOut,
        disabled: false,
        run: () => logout.mutate(),
      };
      return [
        note,
        ...made,
        ...places,
        ...projects,
        ...settings,
        ...themes,
        ...pageThemes,
        ...languages,
        out,
      ].filter((choice) => fold(choice.label).includes(wanted));
    },
    [
      t,
      language,
      setLanguage,
      theme,
      projectsTheme,
      meetingsTheme,
      navigate,
      goToProjects,
      admin,
      owner,
      logout,
      newNote,
      reachable,
    ],
  );
}
