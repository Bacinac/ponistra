import { useEffect } from 'react';
import { useNavigate } from 'react-router';

/** The address of the help as seen from a page: the article about that screen, where there is one. */
export function helpFrom(pathname: string): string {
  return `/help?from=${encodeURIComponent(pathname)}`;
}

/** F1 opens the help on the article about the screen in front of the user. */
export function useHelpKey() {
  const navigate = useNavigate();
  useEffect(() => {
    function open(event: KeyboardEvent) {
      if (event.key !== 'F1') return;
      event.preventDefault();
      navigate(helpFrom(window.location.pathname));
    }
    window.addEventListener('keydown', open);
    return () => window.removeEventListener('keydown', open);
  }, [navigate]);
}
