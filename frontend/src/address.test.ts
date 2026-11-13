import { describe, expect, it } from 'vitest';
import { compact, idIn, segment } from './address';

const ID = '6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b';

describe('an address', () => {
  it('writes a title as plain words before the id', () => {
    expect(segment('Ugovor o najmu – Đakovo, Šibenik & Čakovec', ID)).toBe(
      `ugovor-o-najmu-djakovo-sibenik-cakovec-${compact(ID)}`,
    );
    expect(segment('  ?! ', ID)).toBe(compact(ID));
    expect(segment('x'.repeat(80), ID)).toBe(`${'x'.repeat(60)}-${compact(ID)}`);
  });

  it('is read by its id alone, whatever the words before it say', () => {
    expect(compact(ID)).toHaveLength(22);
    expect(idIn(segment('Ponuda', ID))).toBe(ID);
    expect(idIn(`stari-naziv-${compact(ID)}`)).toBe(ID);
    expect(idIn(compact(ID))).toBe(ID);
    for (const id of [
      '00000000-0000-0000-0000-000000000000',
      'ffffffff-ffff-ffff-ffff-ffffffffffff',
    ]) {
      expect(idIn(segment('Rub', id))).toBe(id);
    }
  });

  it('finds no id where there is none', () => {
    expect(idIn(undefined)).toBeNull();
    expect(idIn(ID)).toBeNull();
    expect(idIn(`ponuda${compact(ID)}`)).toBeNull();
    expect(idIn('z'.repeat(22))).toBeNull();
  });
});
