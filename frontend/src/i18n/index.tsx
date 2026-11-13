import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { en } from './en';
import { hr, type MessageKey } from './hr';

export const LANGUAGES = ['hr', 'en'] as const;
export type Language = (typeof LANGUAGES)[number];
export const LANGUAGE_NAMES: Record<Language, string> = { hr: 'Hrvatski', en: 'English' };

const dictionaries: Record<Language, Record<MessageKey, string>> = { hr, en };

/** The name of a language, written in the interface's language and starting with a capital. */
export function languageName(tag: string, language: Language): string {
  const name = new Intl.DisplayNames([language], { type: 'language' }).of(tag) ?? tag;
  return name.charAt(0).toLocaleUpperCase(language) + name.slice(1);
}
/** The name of a document's locale, written in the interface's language: "en" as American. */
export function localeName(locale: string, language: Language): string {
  return languageName(locale === 'en' ? 'en-US' : locale, language);
}
const LOCALES: Record<Language, string> = { hr: 'hr-HR', en: 'en-GB' };
const STORAGE_KEY = 'ponistra.language';

function storedLanguage(): Language {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'en' ? 'en' : 'hr';
  } catch {
    return 'hr';
  }
}

interface I18n {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: MessageKey) => string;
  formatDate: (iso: string) => string;
  formatNumber: (value: number) => string;
  /** A calendar month, given as YYYY-MM. */
  formatMonth: (month: string) => string;
  /** A time of day, as a clock shows it. */
  formatTime: (date: Date) => string;
  /** A day as a calendar heads it: the weekday, the day and the month. */
  formatDay: (date: Date) => string;
  /** A day by its date alone, as a narrow column shows it. */
  formatShortDay: (date: Date) => string;
  /** Days given as YYYY-MM-DD, from the first to the last: one day when they are the same. */
  formatDays: (first: string, last: string) => string;
  /** A span of time in hours, minutes and seconds, as a stopwatch shows it. */
  formatDuration: (milliseconds: number) => string;
}

export function isMessageKey(key: string): key is MessageKey {
  return key in hr;
}

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(storedLanguage);

  useEffect(() => {
    document.documentElement.lang = language;
    const manifest = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (manifest) {
      manifest.href =
        language === 'hr' ? '/manifest.webmanifest' : `/manifest.${language}.webmanifest`;
    }
  }, [language]);

  const value = useMemo<I18n>(() => {
    const dateTime = new Intl.DateTimeFormat(LOCALES[language], {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
    const number = new Intl.NumberFormat(LOCALES[language]);
    const month = new Intl.DateTimeFormat(LOCALES[language], { month: 'long', year: 'numeric' });
    const time = new Intl.DateTimeFormat(LOCALES[language], { timeStyle: 'short' });
    const day = new Intl.DateTimeFormat(LOCALES[language], {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
    });
    const two = new Intl.NumberFormat(LOCALES[language], { minimumIntegerDigits: 2 });
    const days = new Intl.DateTimeFormat(LOCALES[language], { dateStyle: 'medium' });
    const shortDay = new Intl.DateTimeFormat(LOCALES[language], {
      day: 'numeric',
      month: 'numeric',
    });
    const local = (given: string) => {
      const [year, at, date] = given.split('-').map(Number);
      return new Date(year, at - 1, date);
    };
    return {
      language,
      setLanguage: (next) => {
        setLanguageState(next);
        try {
          localStorage.setItem(STORAGE_KEY, next);
        } catch {
          // Blocked storage only costs remembering the choice across visits.
        }
      },
      t: (key) => dictionaries[language][key],
      formatDate: (iso) => dateTime.format(new Date(iso)),
      formatNumber: (value) => number.format(value),
      formatMonth: (given) => {
        const [year, at] = given.split('-').map(Number);
        return month.format(new Date(year, at - 1, 1));
      },
      formatTime: (date) => time.format(date),
      formatDay: (date) => day.format(date),
      formatShortDay: (date) => shortDay.format(date),
      formatDays: (first, last) => days.formatRange(local(first), local(last)),
      formatDuration: (milliseconds) => {
        const seconds = Math.floor(milliseconds / 1000);
        return [
          number.format(Math.floor(seconds / 3600)),
          two.format(Math.floor(seconds / 60) % 60),
          two.format(seconds % 60),
        ].join(':');
      },
    };
  }, [language]);

  return <I18nContext value={value}>{children}</I18nContext>;
}

export function useI18n(): I18n {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n called outside I18nProvider');
  return context;
}
