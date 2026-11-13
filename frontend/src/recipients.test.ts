import { describe, expect, it } from 'vitest';
import { mailto, written } from './recipients';

describe('written', () => {
  it('reads the people written out by commas or semicolons, a name in quotes kept whole', () => {
    expect(
      written('Ana Kovač <ana@example.com>, "Horvat, Iva" <iva@example.com>; marko@example.com,'),
    ).toEqual([
      { name: 'Ana Kovač', address: 'ana@example.com' },
      { name: 'Horvat, Iva', address: 'iva@example.com' },
      { name: '', address: 'marko@example.com' },
    ]);
  });

  it('keeps what is no address as written, for the server to refuse', () => {
    expect(written('  Ana Horvat/Firma \n')).toEqual([{ name: '', address: 'Ana Horvat/Firma' }]);
    expect(written(' , ')).toEqual([]);
  });
});

describe('mailto', () => {
  it('reads the people, copies, subject and text a link asks for', () => {
    expect(
      mailto(
        'mailto:ana@example.com,Iva%20Horvat%20%3Civa@example.com%3E?CC=marko@example.com' +
          '&bcc=uprava@example.com&subject=Ponuda%20br.%207&body=Dobar%20dan%2C%0D%0A%0D%0Ahvala&x=y',
      ),
    ).toEqual({
      to: [
        { name: '', address: 'ana@example.com' },
        { name: 'Iva Horvat', address: 'iva@example.com' },
      ],
      cc: [{ name: '', address: 'marko@example.com' }],
      bcc: [{ name: '', address: 'uprava@example.com' }],
      subject: 'Ponuda br. 7',
      text: 'Dobar dan,\n\nhvala',
    });
  });

  it('keeps a plus a plus, takes recipients from to fields as well and survives a broken escape', () => {
    expect(mailto('mailto:?to=ana+posao@example.com&subject=100%+gotovo')).toEqual({
      to: [{ name: '', address: 'ana+posao@example.com' }],
      cc: [],
      bcc: [],
      subject: '100%+gotovo',
      text: '',
    });
  });
});
