import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router';
import { patchJson } from './api';
import { keepSignIn, type Me, type Session, SESSION_KEY, useSession } from './auth';
import { useI18n } from './i18n';
import { choosePageTheme, chooseTheme, usePageTheme, useTheme } from './theme';

type Given = Partial<Pick<Me, 'language' | 'theme' | 'projects_theme' | 'meetings_theme'>>;

/** One choice between the account and this browser: what the account says arrives here, and what
 * is chosen here, or was chosen here before the account held anything, goes to the account. Choices
 * reach it one at a time, the newest only, and what it answers while one is on its way is not
 * applied: it was either this browser's own older choice or is overwritten by the one going. */
function useKept<T extends string>(
  kept: T | '',
  here: T,
  unchosen: T,
  apply: (value: T) => void,
  keep: (value: T) => Promise<unknown>,
) {
  const seen = useRef<{ kept: string; here: T } | null>(null);
  const applied = useRef<T | null>(null);
  const going = useRef<{ next: T | null } | null>(null);
  useEffect(() => {
    const was = seen.current;
    seen.current = { kept, here };
    const chose = was ? was.here !== here && here !== applied.current : !kept && here !== unchosen;
    if (was?.here !== here) applied.current = null;
    if (going.current) {
      if (chose) going.current.next = here;
      return;
    }
    if (chose) {
      const sending = { next: here as T | null };
      going.current = sending;
      void (async () => {
        try {
          for (let value = sending.next; value !== null; value = sending.next) {
            sending.next = null;
            await keep(value);
          }
        } catch {
          // A refused choice stays in this browser; the mutation cache handles a lost session.
        } finally {
          going.current = null;
        }
      })();
      return;
    }
    if (kept && kept !== was?.kept && kept !== here) {
      applied.current = kept;
      apply(kept);
    }
  });
}

function Kept({ user }: { user: Me }) {
  const queryClient = useQueryClient();
  const { language, setLanguage } = useI18n();
  const theme = useTheme();
  const projects = usePageTheme('projects');
  const meetings = usePageTheme('meetings');
  const { mutateAsync } = useMutation({
    mutationFn: (given: Given) => patchJson<Session>('/api/auth/preferences', given),
    onSuccess: (session) => queryClient.setQueryData(SESSION_KEY, session),
  });
  useKept(user.language, language, 'hr', setLanguage, (value) => mutateAsync({ language: value }));
  useKept(user.theme, theme, 'system', chooseTheme, (value) => mutateAsync({ theme: value }));
  useKept(
    user.projects_theme,
    projects,
    'ponistra',
    (value) => choosePageTheme('projects', value),
    (value) => mutateAsync({ projects_theme: value }),
  );
  useKept(
    user.meetings_theme,
    meetings,
    'ponistra',
    (value) => choosePageTheme('meetings', value),
    (value) => mutateAsync({ meetings_theme: value }),
  );
  useEffect(() => keepSignIn(user.sign_in), [user.sign_in]);
  return null;
}

/** The signed-in user's language and themes, the same on every device. The browser holds them too,
 * for the sign-in page; the printer's page keeps the look of paper whatever the account chose. */
export function Preferences() {
  const { pathname } = useLocation();
  const user = useSession().data?.user;
  return user && !pathname.startsWith('/print/') ? <Kept user={user} /> : null;
}
