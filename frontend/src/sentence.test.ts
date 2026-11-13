// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { en } from './i18n/en';
import { hr, type MessageKey } from './i18n/hr';
import { isSentence, searchHref, translatedQuery } from './sentence';

const croatian = (key: MessageKey) => hr[key];
const english = (key: MessageKey) => en[key];

describe('isSentence', () => {
  it('takes words enough for a sentence, none of them a filter', () => {
    expect(isSentence('ponude koje mi je Ana poslala')).toBe(true);
    expect(isSentence('  ugovor   za Rijeku ')).toBe(true);
    expect(isSentence('ugovor Rijeka')).toBe(false);
    expect(isSentence('ugovor za od:ana')).toBe(false);
    expect(isSentence('sastanak u 10:30 sutra')).toBe(true);
  });
});

describe('translatedQuery', () => {
  it('types each filter as the interface language types it', () => {
    const found = {
      text: 'ponude',
      kind: 'mail' as const,
      from: 'Ana Kovač',
      account: 'posao',
      folder: 'sent',
      since: '2026-09-01',
      until: '2026-09-30',
      attachment: true,
    };
    expect(translatedQuery(found, croatian)).toBe(
      'ponude vrsta:pošta od:"Ana Kovač" račun:posao mapa:sent datum:2026-09-01..2026-09-30 ima:privitak',
    );
    expect(translatedQuery(found, english)).toBe(
      'ponude kind:mail from:"Ana Kovač" account:posao folder:sent date:2026-09-01..2026-09-30 has:attachment',
    );
  });

  it('writes a period open at one end, one day, or when it was changed', () => {
    expect(translatedQuery({ text: '', since: '2026-03-01' }, croatian)).toBe('datum:2026-03-01..');
    expect(translatedQuery({ text: 'x', until: '2025-12-31', changed: true }, croatian)).toBe(
      'x izmjena:..2025-12-31',
    );
    expect(translatedQuery({ text: '', since: '2026-10-23', until: '2026-10-23' }, croatian)).toBe(
      'datum:2026-10-23',
    );
  });

  it('keeps a quote out of a value', () => {
    expect(translatedQuery({ text: 'ugovor', from: 'Ana "A" Kovač' }, croatian)).toBe(
      'ugovor od:"Ana A Kovač"',
    );
  });
});

it('puts the query in the search address', () => {
  expect(searchHref('ponude od:ana')).toBe('/search?q=ponude+od%3Aana');
});
