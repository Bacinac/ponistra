import { describe, expect, it } from 'vitest';
import { DOCUMENT_LOCALES } from '../tree';
import { localCode, PRESETS, presetCode, storedCode } from './formats';

describe('format codes', () => {
  it('are written with the separators of the document language', () => {
    expect(localCode('#,##0.00 "€"', 'hr')).toBe('#.##0,00 "€"');
    expect(storedCode('#.##0,00 "€"', 'hr')).toBe('#,##0.00 "€"');
    expect(localCode('0.00%;-0.00%', 'de')).toBe('0,00%;-0,00%');
    expect(localCode('#,##0.00', 'en')).toBe('#,##0.00');
  });

  it('leave dates, times and text that stands as written', () => {
    expect(localCode('dd.mm.yyyy. hh:mm', 'hr')).toBe('dd.mm.yyyy. hh:mm');
    expect(localCode('[h]:mm', 'hr')).toBe('[h]:mm');
    expect(localCode('0.0" kg, net"\\,_)', 'hr')).toBe('0,0" kg, net"\\,_)');
    expect(localCode('[Red][>=1000.5]#,##0', 'hr')).toBe('[Red][>=1000,5]#.##0');
    expect(storedCode('[Red][>=1000,5]#.##0', 'hr')).toBe('[Red][>=1000.5]#,##0');
  });

  it('group thousands with a space in French, a space elsewhere staying a space', () => {
    expect(localCode('#,##0.00 "€"', 'fr')).toBe('# ##0,00 "€"');
    expect(storedCode('# ##0,00 "€"', 'fr')).toBe('#,##0.00 "€"');
    expect(storedCode('# ?/?', 'fr')).toBe('# ?/?');
  });

  it('keep the dates as the built-ins of Excel, shown by the server in the form of each language', () => {
    for (const locale of DOCUMENT_LOCALES) {
      expect(presetCode('date', locale)).toBe('mm-dd-yy');
      expect(presetCode('dateTime', locale)).toBe('m/d/yy h:mm');
    }
  });

  it('come back as they were stored in every language', () => {
    for (const locale of DOCUMENT_LOCALES) {
      for (const preset of PRESETS) {
        const code = presetCode(preset, locale);
        expect(storedCode(localCode(code, locale), locale)).toBe(code);
      }
    }
  });
});
