const KEY = 'ponistra.door';

export function rememberDoor(path: string) {
  try {
    sessionStorage.setItem(KEY, path);
  } catch {
    // Storage refused: a visitor whose link ends sees the sign-in page instead of the door.
  }
}

export function rememberedDoor(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function forgetDoor() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // Nothing kept, nothing to forget.
  }
}
