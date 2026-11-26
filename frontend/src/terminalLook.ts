import type { ITheme } from '@xterm/xterm';

const ANSI = [
  'black',
  'red',
  'green',
  'yellow',
  'blue',
  'magenta',
  'cyan',
  'white',
  'brightBlack',
  'brightRed',
  'brightGreen',
  'brightYellow',
  'brightBlue',
  'brightMagenta',
  'brightCyan',
  'brightWhite',
] as const;

/** The terminal's colours as theme.css has them for the scheme in force where it stands. */
export function look(element: HTMLElement): ITheme {
  const probe = element.appendChild(document.createElement('span'));
  probe.style.display = 'none';
  const resolved = (color: string) => {
    probe.style.color = color;
    return getComputedStyle(probe).color;
  };
  const theme: ITheme = {
    background: resolved('var(--raised)'),
    foreground: resolved('var(--ink)'),
    cursor: resolved('var(--accent)'),
    cursorAccent: resolved('var(--raised)'),
    selectionBackground: resolved('var(--selected)'),
    selectionForeground: resolved('var(--ink)'),
    ...Object.fromEntries(ANSI.map((name, index) => [name, resolved(`var(--terminal-${index})`)])),
  };
  probe.remove();
  return theme;
}
