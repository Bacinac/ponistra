import { useLayoutEffect, useSyncExternalStore } from 'react';
import { CHART_COLORS, onScreen } from './editor/colors';

export const THEMES = ['system', 'light', 'dark'] as const;
export type Theme = (typeof THEMES)[number];

/** The pages that open in a window of their own beside the app, each with a theme of its own or
    Ponistra's. */
export const PAGES = ['projects', 'meetings'] as const;
export type Page = (typeof PAGES)[number];
export const PAGE_THEMES = ['ponistra', 'light', 'dark'] as const;
export type PageTheme = (typeof PAGE_THEMES)[number];

const STORAGE_KEY = 'ponistra.theme';
const SYSTEM_DARK = '(prefers-color-scheme: dark)';
const listeners = new Set<() => void>();
let chosen: Theme = 'system';
const pages: Record<Page, PageTheme> = { projects: 'ponistra', meetings: 'ponistra' };
let shown: Page | null = null;

function stored<T extends string>(key: string, allowed: readonly T[], unchosen: T): T {
  try {
    const value = localStorage.getItem(key);
    return allowed.find((each) => each === value) ?? unchosen;
  } catch {
    return unchosen;
  }
}

function store(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Blocked storage only costs remembering the choice across visits.
  }
}

const pageKey = (page: Page) => `${STORAGE_KEY}.${page}`;

function changed(): void {
  for (const listener of listeners) listener();
}

/** The theme in force: the shown page's own, else the one chosen for Ponistra. */
function inForce(): Theme {
  const own = shown && pages[shown];
  return own && own !== 'ponistra' ? own : chosen;
}

function applied(): void {
  const theme = inForce();
  if (theme === 'system') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  changed();
}

/** Whether the interface is dark: as the user chose for Ponistra or the page shown, or as the
    system has it. */
export function isDark(): boolean {
  const theme = inForce();
  return theme === 'system' ? matchMedia(SYSTEM_DARK).matches : theme === 'dark';
}

/** Calls back each time the interface turns light or dark, by the user's choice or the system's. */
export function onScheme(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function chooseTheme(theme: Theme): void {
  chosen = theme;
  store(STORAGE_KEY, theme);
  applied();
}

export function choosePageTheme(page: Page, theme: PageTheme): void {
  pages[page] = theme;
  store(pageKey(page), theme);
  applied();
}

export function useTheme(): Theme {
  return useSyncExternalStore(onScheme, () => chosen);
}

export function usePageTheme(page: Page): PageTheme {
  return useSyncExternalStore(onScheme, () => pages[page]);
}

/** The page's own theme holds while the page is shown. */
export function useThemeOf(page: Page): void {
  useLayoutEffect(() => {
    shown = page;
    applied();
    return () => {
      shown = null;
      applied();
    };
  }, [page]);
}

export function useDark(): boolean {
  return useSyncExternalStore(onScheme, isDark);
}

export function installTheme(): void {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (!meta) throw new Error('Theme colour metadata is missing');
  onScheme(() => {
    meta.content = getComputedStyle(document.documentElement).backgroundColor;
  });
  matchMedia(SYSTEM_DARK).addEventListener('change', () => {
    if (inForce() === 'system') changed();
  });
  for (const page of PAGES) pages[page] = stored(pageKey(page), PAGE_THEMES, 'ponistra');
  chooseTheme(stored(STORAGE_KEY, THEMES, 'system'));
}

export function presenceColor(userId: number): string {
  const colors = getComputedStyle(document.documentElement)
    .getPropertyValue('--presence-colors')
    .split(',')
    .map((color) => color.trim())
    .filter(Boolean);
  if (!colors.length) throw new Error('Collaboration colour palette is missing');
  return colors[userId % colors.length];
}

/** The colours a chart is drawn in where it stands: its series', text's, axes' and surface's,
 * each resolved for the theme in force there, and the font of its text. */
export interface ChartLook {
  colors: string[];
  ink: string;
  muted: string;
  line: string;
  surface: string;
  raised: string;
  font: string;
}

export function chartLook(element: HTMLElement): ChartLook {
  const probe = element.appendChild(document.createElement('span'));
  probe.style.display = 'none';
  const resolved = (color: string) => {
    probe.style.color = color;
    return getComputedStyle(probe).color;
  };
  const look = {
    colors: CHART_COLORS.map((swatch) => resolved(onScreen(swatch))),
    ink: resolved('var(--ink)'),
    muted: resolved('var(--muted)'),
    line: resolved('var(--line)'),
    surface: resolved('var(--surface)'),
    raised: resolved('var(--raised)'),
    font: getComputedStyle(element).fontFamily,
  };
  probe.remove();
  return look;
}
