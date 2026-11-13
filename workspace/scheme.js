// PONISTRA's account menu (theme.ts) keeps the chosen scheme in this origin's storage. VS Code,
// set to follow the system's, is shown that choice in its place, and every change to it.
(() => {
  const key = 'ponistra.theme';
  const native = window.matchMedia.bind(window);
  const chosen = () => {
    try {
      const theme = localStorage.getItem(key);
      return theme === 'light' || theme === 'dark' ? theme : null;
    } catch {
      return null;
    }
  };
  const lists = new Map();
  window.matchMedia = (query) => {
    const asked = /prefers-color-scheme:\s*(light|dark)/.exec(query);
    if (!asked) return native(query);
    if (lists.has(query)) return lists.get(query).list;
    const system = native(query);
    const list = new EventTarget();
    Object.defineProperties(list, {
      media: { value: system.media },
      matches: {
        get: () => {
          const theme = chosen();
          return theme ? theme === asked[1] : system.matches;
        },
      },
    });
    list.onchange = null;
    list.addListener = (listener) => list.addEventListener('change', listener);
    list.removeListener = (listener) => list.removeEventListener('change', listener);
    const change = () => {
      const event = Object.assign(new Event('change'), { matches: list.matches, media: list.media });
      list.dispatchEvent(event);
      list.onchange?.(event);
    };
    system.addEventListener('change', () => {
      if (!chosen()) change();
    });
    lists.set(query, { list, change });
    return list;
  };
  window.addEventListener('storage', (event) => {
    if (event.key === key) for (const { change } of lists.values()) change();
  });
})();
