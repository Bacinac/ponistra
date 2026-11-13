export const APPLE = /Mac|iPhone|iPad/.test(navigator.userAgent);

const MODIFIERS = ['Ctrl', 'Mod', 'Alt', 'Shift'] as const;
type Modifier = (typeof MODIFIERS)[number];
const APPLE_ORDER: Modifier[] = ['Ctrl', 'Alt', 'Shift', 'Mod'];
const SIGNS: Record<Modifier, [apple: string, other: string]> = {
  Ctrl: ['⌃', 'Ctrl'],
  Mod: ['⌘', 'Ctrl'],
  Alt: ['⌥', 'Alt'],
  Shift: ['⇧', 'Shift'],
};

export function shortcutLabel(keys: string, apple = APPLE): string {
  const parts = keys.split('-');
  const key = parts.pop()!;
  const shown = key.length === 1 ? key.toUpperCase() : key;
  const order = apple ? APPLE_ORDER : MODIFIERS;
  const held = order.filter((modifier) => parts.includes(modifier));
  const signs = held.map((modifier) => SIGNS[modifier][apple ? 0 : 1]);
  return apple ? signs.join('') + shown : [...signs, shown].join('+');
}
