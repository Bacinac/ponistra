import { useEffect, useSyncExternalStore } from 'react';

const TAB = '(display-mode: browser)';

function subscribe(change: () => void) {
  const query = matchMedia(TAB);
  query.addEventListener('change', change);
  return () => query.removeEventListener('change', change);
}

/** Names the page after `name`: `Ugovor – Ponistra` in a browser tab, `Ugovor` alone in the
 * installed app's window, whose title bar the browser itself begins with the app's name. */
export function useTitle(name: string | undefined) {
  const tab = useSyncExternalStore(subscribe, () => matchMedia(TAB).matches);
  useEffect(() => {
    document.title = !name ? 'Ponistra' : tab ? `${name} – Ponistra` : name;
    return () => {
      document.title = 'Ponistra';
    };
  }, [name, tab]);
}
