function scrollerOf(element: Element): Element | null {
  for (let at = element.parentElement; at; at = at.parentElement) {
    const { overflowY } = getComputedStyle(at);
    if (overflowY === 'auto' || overflowY === 'scroll') return at;
  }
  return null;
}

/** Tells of each observed element once, when it comes within a few hundred pixels of the part of
 * the page it scrolls in. Watched against the viewport, an element scrolling inside another is
 * clipped by it before the margin counts, so it would show only once already in sight. */
export function watchNear(within: Element, near: (target: Element) => void): IntersectionObserver {
  const watcher = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        watcher.unobserve(entry.target);
        near(entry.target);
      }
    },
    { root: scrollerOf(within), rootMargin: '400px' },
  );
  return watcher;
}
