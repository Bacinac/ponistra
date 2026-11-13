import { EmojiPicker, type EmojiData, type Locale } from 'frimousse';
import emojisUrl from 'emojibase-data/en/data.json?url';
import groupsUrl from 'emojibase-data/en/messages.json?url';
import croatianUrl from 'cldr-annotations-full/annotations/hr/annotations.json?url';
import { useMemo } from 'react';
import { useI18n, type Language } from './i18n';
import type { MessageKey } from './i18n/hr';
import { field } from './styles';

interface Listed {
  emoji: string;
  label: string;
  tags?: string[];
  group?: number;
  subgroup?: number;
  version: number;
  skins?: { emoji: string; tone: number | number[] }[];
}

interface Groups {
  groups: { key: string; order: number }[];
  subgroups: { key: string; order: number }[];
}

type Named = Record<string, { default?: string[]; tts?: string[] }>;

const TONES = ['light', 'medium-light', 'medium', 'medium-dark', 'dark'] as const;
// The newest emoji every supported system draws; Windows draws nothing past Emoji 15.0.
const NEWEST = 15;
const COLUMNS = 9;
const loaded = new Map<string, Promise<unknown>>();

function json<T>(url: string, signal?: AbortSignal): Promise<T> {
  let found = loaded.get(url);
  if (!found) {
    found = fetch(url, { signal }).then((answer) => {
      if (!answer.ok) throw new Error(`${answer.status} ${url}`);
      return answer.json();
    });
    found.catch(() => loaded.delete(url));
    loaded.set(url, found);
  }
  return found as Promise<T>;
}

function skinsOf(listed: Listed): Record<(typeof TONES)[number], string> | undefined {
  const toned = (listed.skins ?? []).filter((each) => typeof each.tone === 'number');
  if (toned.length !== TONES.length) return undefined;
  return Object.fromEntries(
    toned.map((each) => [TONES[(each.tone as number) - 1], each.emoji]),
  ) as Record<(typeof TONES)[number], string>;
}

/** Emojibase's emoji, named and found in the user's language where CLDR names them in it. */
async function resolved(
  locale: Language,
  label: (key: string) => string,
  signal?: AbortSignal,
): Promise<EmojiData> {
  const [emojis, groups, named] = await Promise.all([
    json<Listed[]>(emojisUrl, signal),
    json<Groups>(groupsUrl, signal),
    locale === 'hr'
      ? json<{ annotations: { annotations: Named } }>(croatianUrl, signal).then(
          (found) => found.annotations.annotations,
        )
      : null,
  ]);
  const shown = new Map(
    groups.groups.filter((each) => each.key !== 'component').map((each) => [each.order, each.key]),
  );
  // Windows draws a country's flag as its two letters.
  const flags = groups.subgroups.find((each) => each.key === 'country-flag')?.order;
  return {
    locale: locale as Locale,
    categories: [...shown].map(([index, key]) => ({ index, label: label(key) })),
    skinTones: Object.fromEntries(TONES.map((tone) => [tone, tone])) as EmojiData['skinTones'],
    emojis: emojis
      .filter(
        (each) =>
          each.group !== undefined &&
          shown.has(each.group) &&
          each.subgroup !== flags &&
          each.version <= NEWEST,
      )
      .map((each) => {
        const own = named?.[each.emoji] ?? named?.[each.emoji.replaceAll('\uFE0F', '')];
        return {
          emoji: each.emoji,
          category: each.group!,
          label: own?.tts?.[0] ?? each.label,
          version: each.version,
          tags: [...(own?.default ?? []), ...(each.tags ?? [])],
          skins: skinsOf(each),
        };
      }),
  };
}

/** The whole set of emoji, by group and found by name, the user picks one of. */
export function EmojiGrid({ onPick }: { onPick: (emoji: string) => void }) {
  const { t, language } = useI18n();
  const resolve = useMemo(
    () =>
      (locale: Locale, { signal }: { signal?: AbortSignal }) =>
        resolved(locale as Language, (key) => t(`reactions.group.${key}` as MessageKey), signal),
    [t],
  );
  return (
    <EmojiPicker.Root
      locale={language as Locale}
      resolveEmojiData={resolve}
      columns={COLUMNS}
      onEmojiSelect={({ emoji }) => onPick(emoji)}
      className="flex h-96 flex-col gap-2"
    >
      <EmojiPicker.Search
        aria-label={t('reactions.search')}
        placeholder={t('reactions.search')}
        className={field}
      />
      <EmojiPicker.Viewport className="relative min-h-0 flex-1 outline-none">
        <EmojiPicker.Loading className="absolute inset-0 flex items-center justify-center text-sm text-muted">
          …
        </EmojiPicker.Loading>
        <EmojiPicker.Empty className="absolute inset-0 flex items-center justify-center text-sm text-muted">
          {t('reactions.none')}
        </EmojiPicker.Empty>
        <EmojiPicker.List
          className="select-none"
          components={{
            CategoryHeader: ({ category, ...props }) => (
              <div {...props} className="bg-raised px-1 pt-2 pb-1 text-xs font-semibold text-muted">
                {category.label}
              </div>
            ),
            Row: ({ children, ...props }) => (
              <div {...props} className="flex">
                {children}
              </div>
            ),
            Emoji: ({ emoji, ...props }) => (
              <button
                type="button"
                {...props}
                className="flex size-9 items-center justify-center rounded text-2xl leading-none data-active:bg-hover"
              >
                {emoji.emoji}
              </button>
            ),
          }}
        />
      </EmojiPicker.Viewport>
    </EmojiPicker.Root>
  );
}
