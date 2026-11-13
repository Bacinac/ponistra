import { describe, expect, it } from 'vitest';
import { en } from '../i18n/en';
import {
  fieldsOf,
  filledFrom,
  same,
  scriptMessage,
  settling,
  storedFor,
  type FieldObject,
} from './form';

const objects = new Map<string, FieldObject[]>([
  ['Ime', [{ id: '1R', type: 'text', value: 'Ana' }]],
  [
    'Plaćanje',
    [
      { id: '2R', type: 'radiobutton', value: 'Kartica', exportValues: 'Gotovina' },
      { id: '3R', type: 'radiobutton', value: 'Kartica', exportValues: 'Kartica' },
    ],
  ],
  ['Opremljen', [{ id: '4R', type: 'checkbox', value: 'Off', exportValues: 'Da' }]],
  ['Grad', [{ id: '5R', type: 'combobox', value: 'Split' }]],
  ['Jezici', [{ id: '6R', type: 'listbox', value: 'hr', multipleSelection: true }]],
  ['Pošalji', [{ id: '7R', type: 'button' }]],
  ['Potpis', [{ id: '8R', type: 'signature', value: null }]],
  ['Osoba', [{ id: '9R', type: '' }]],
]);
const fields = fieldsOf(objects);
const field = (name: string) => fields.get(name)!;

describe('fieldsOf', () => {
  it('knows the fields a value is filled into, with their values as the file came', () => {
    expect([...fields.keys()]).toEqual(['Ime', 'Plaćanje', 'Opremljen', 'Grad', 'Jezici']);
    expect(field('Ime')).toEqual({
      name: 'Ime',
      kind: 'text',
      widgets: [{ id: '1R', on: null }],
      many: false,
      original: 'Ana',
    });
    expect(field('Plaćanje').widgets).toEqual([
      { id: '2R', on: 'Gotovina' },
      { id: '3R', on: 'Kartica' },
    ]);
    expect(field('Plaćanje').original).toBe('Kartica');
    expect(field('Opremljen').original).toBe('Off');
    expect(field('Grad').original).toBe('Split');
    expect(field('Jezici')).toMatchObject({ many: true, original: ['hr'] });
  });
});

describe('storedFor', () => {
  it('gives each widget what pdf.js keeps of it', () => {
    expect(
      storedFor(field('Ime'), field('Ime').widgets[0], { value: '1234.5', shown: '1.234,50' }),
    ).toEqual({ value: '1234.5', formattedValue: '1.234,50' });
    expect(storedFor(field('Ime'), field('Ime').widgets[0], { value: 'Ana' })).toEqual({
      value: 'Ana',
      formattedValue: null,
    });
    const [cash, card] = field('Plaćanje').widgets;
    expect(storedFor(field('Plaćanje'), cash, { value: 'Kartica' })).toEqual({ value: false });
    expect(storedFor(field('Plaćanje'), card, { value: 'Kartica' })).toEqual({ value: true });
    expect(storedFor(field('Grad'), field('Grad').widgets[0], { value: 'Zagreb' })).toEqual({
      value: ['Zagreb'],
    });
    expect(storedFor(field('Grad'), field('Grad').widgets[0], { value: '' })).toEqual({
      value: [],
    });
  });
});

describe('filledFrom', () => {
  const none = () => undefined;

  it('keeps typed text, and the text as shown only while the field’s script showed it so', () => {
    const before = { value: '1234.5', shown: '1.234,50' };
    expect(filledFrom(field('Ime'), { id: '1R', value: '12' }, none, before)).toEqual({
      value: '12',
    });
    expect(
      filledFrom(field('Ime'), { id: '1R', value: 1234.5, shown: '1.234,50' }, none, { value: '' }),
    ).toEqual(before);
    expect(filledFrom(field('Ime'), { id: '1R', shown: '1.234,5' }, none, before)).toEqual({
      value: '1234.5',
      shown: '1.234,5',
    });
    expect(filledFrom(field('Ime'), { id: '1R', shown: null }, none, before)).toEqual({
      value: '1234.5',
    });
  });

  it('takes the state of the box that is on, or Off', () => {
    const kept = new Map<string, unknown>([
      ['2R', true],
      ['3R', false],
    ]);
    const radio = field('Plaćanje');
    expect(filledFrom(radio, { id: '2R' }, (id) => kept.get(id), { value: 'Kartica' })).toEqual({
      value: 'Gotovina',
    });
    expect(filledFrom(radio, { id: '2R' }, none, { value: 'Kartica' })).toEqual({
      value: 'Kartica',
    });
    expect(filledFrom(radio, { id: '3R' }, () => false, { value: 'Kartica' })).toEqual({
      value: 'Off',
    });
  });

  it('takes one option of a list that drops down, and all chosen of one that takes many', () => {
    expect(filledFrom(field('Grad'), { id: '5R', value: ['Zagreb'] }, none, { value: '' })).toEqual(
      { value: 'Zagreb' },
    );
    expect(filledFrom(field('Grad'), { id: '5R', value: [] }, none, { value: 'Split' })).toEqual({
      value: '',
    });
    expect(
      filledFrom(field('Jezici'), { id: '6R' }, () => ['hr', 'de'], { value: ['hr'] }),
    ).toEqual({ value: ['hr', 'de'] });
    expect(filledFrom(field('Jezici'), { id: '6R', value: 'en' }, none, { value: [] })).toEqual({
      value: ['en'],
    });
  });
});

describe('same', () => {
  it('compares values and how they are shown', () => {
    expect(same({ value: ['hr', 'de'] }, { value: ['hr', 'de'] })).toBe(true);
    expect(same({ value: ['hr', 'de'] }, { value: ['de', 'hr'] })).toBe(false);
    expect(same({ value: '1' }, { value: '1', shown: '1,00' })).toBe(false);
  });
});

describe('settling', () => {
  it('gives a value filled in elsewhere to the scripts as committed there', () => {
    expect(settling(field('Ime'), { value: '1234.5', shown: '1.234,50' })).toEqual({
      id: '1R',
      name: 'Validate',
      value: '1234.5',
    });
    expect(settling(field('Jezici'), { value: ['hr', 'en'] })).toEqual({
      id: '6R',
      name: 'Validate',
      value: ['hr', 'en'],
    });
  });

  it('turns on the box that shows the state, and turns a box off', () => {
    expect(settling(field('Plaćanje'), { value: 'Kartica' })).toEqual({
      id: '3R',
      name: 'Validate',
      value: true,
    });
    expect(settling(field('Opremljen'), { value: 'Off' })).toEqual({
      id: '4R',
      name: 'Validate',
      value: false,
    });
  });

  it('leaves a radio group with none chosen to the scripts as they have it', () => {
    expect(settling(field('Plaćanje'), { value: 'Off' })).toBeNull();
  });
});

describe('scriptMessage', () => {
  const say = {
    t: (key: keyof typeof en) => en[key],
    formatNumber: (value: number) => new Intl.NumberFormat('hr-HR').format(value),
  };

  it('puts pdf.js’s own form messages in the reader’s language, numbers as the reader writes them', () => {
    expect(
      scriptMessage('The value entered does not match the format of the field [ Iznos ]', say),
    ).toBe('The value entered does not match the format of the field [ Iznos ]');
    expect(
      scriptMessage(
        'Invalid date / time: please ensure that the date / time exists. Field [ Datum ] should match format dd.mm.yyyy',
        say,
      ),
    ).toBe('The date or time does not exist in the field [ Datum ]; expected format dd.mm.yyyy');
    expect(
      scriptMessage(
        'Invalid value: must be greater than or equal to 1000.5 and less than or equal to 20000.',
        say,
      ),
    ).toBe('Invalid value: must be from 1.000,5 to 20.000.');
    expect(scriptMessage('Invalid value: must be greater than or equal to 10.', say)).toBe(
      'Invalid value: must be at least 10.',
    );
    expect(scriptMessage('Invalid value: must be less than or equal to 2.5.', say)).toBe(
      'Invalid value: must be at most 2,5.',
    );
  });

  it('leaves the file’s own messages as the file says them', () => {
    expect(scriptMessage('Unesite OIB.', say)).toBe('Unesite OIB.');
  });
});
