import type { Language } from '../i18n';

/** The language Ponistra OS set up the machine in: the installer's `LANG` reaches Chromium as
 * `navigator.language`. A language chosen on the page still comes first. */
export function machineLanguage(): Language {
  return navigator.language.toLowerCase().startsWith('hr') ? 'hr' : 'en';
}
