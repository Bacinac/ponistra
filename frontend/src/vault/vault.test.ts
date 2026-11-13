import { describe, expect, it } from 'vitest';
import {
  fromCode,
  fromPassword,
  newCode,
  newKdf,
  newPair,
  open,
  openSealed,
  random,
  seal,
  sealTo,
  spelledCode,
  textBytes,
} from './crypto';
import { counted, laidOut, pathOf, planned, type Folder } from './folders';
import { matches, wordsOf } from './search';
import { blank, changed, generated, openItem, sealSecret, type SealedItem } from './secret';
import { parseTotp, totpCode } from './totp';
import { exported, imported, parseCsv, Unreadable } from './transfer';

describe('the vault’s keys', () => {
  it('open only with the key that sealed them', async () => {
    const key = random(32);
    const sealed = await seal(key, textBytes('lozinka'));
    expect(new TextDecoder().decode(await open(key, sealed))).toBe('lozinka');
    await expect(open(random(32), sealed)).rejects.toThrow();
  });

  it('come from a password through Argon2id under the costs kept beside them', async () => {
    const kdf = newKdf();
    expect(kdf).toMatchObject({ memory: 65536, iterations: 3, parallelism: 4 });
    const key = await fromPassword('Kamen-Most-Rijeka-71', kdf);
    expect(await fromPassword('Kamen-Most-Rijeka-71', kdf)).toEqual(key);
    expect(await fromPassword('Kamen-Most-Rijeka-72', kdf)).not.toEqual(key);
  }, 30_000);

  it('come from a recovery code however it was typed', async () => {
    const code = newCode();
    expect(code).toMatch(/^([0-9A-HJKMNP-TV-Z]{4}-){7}[0-9A-HJKMNP-TV-Z]{4}$/);
    const typed = code.toLowerCase().replace(/-/g, ' ').replace(/0/g, 'o').replace(/1/g, 'l');
    expect(spelledCode(typed)).toBe(code.replace(/-/g, ''));
    expect(await fromCode(spelledCode(typed)!)).toEqual(await fromCode(spelledCode(code)!));
    expect(spelledCode('ABCD-EFGH')).toBeNull();
    expect(spelledCode(code.replace(/.$/, 'U'))).toBeNull();
  });

  it('reach a member sealed to their public key, and nobody else', async () => {
    const ana = await newPair();
    const marko = await newPair();
    const collection = random(32);
    const sealed = await sealTo(ana.publicKey, collection);
    expect(await openSealed(ana, sealed)).toEqual(collection);
    await expect(openSealed(marko, sealed)).rejects.toThrow();
    expect(await sealTo(ana.publicKey, collection)).not.toEqual(sealed);
  });
});

describe('an item among the search results', () => {
  const item = {
    secret: {
      ...blank('login'),
      name: 'Banka Žiro',
      username: 'ana.kovac',
      urls: ['https://www.banka.hr/prijava', 'nije adresa'],
      notes: 'tajna riječ',
      password: 'lozinka',
    },
  } as never;
  it('is matched by the starts of the words of its name, user name and hosts, not its secrets', () => {
    expect(wordsOf('Žiro-račun 2')).toEqual(['ziro', 'racun', '2']);
    expect(matches(item, ['bank', 'zir'])).toBe(true);
    expect(matches(item, ['kovac'])).toBe(true);
    expect(matches(item, ['www.banka'])).toBe(false);
    expect(matches(item, ['banka', 'hr'])).toBe(true);
    expect(matches(item, ['tajna'])).toBe(false);
    expect(matches(item, ['lozinka'])).toBe(false);
  });
});

describe('an item', () => {
  it('is sealed whole with a key of its own that moves to another collection', async () => {
    const first = random(32);
    const secret = { ...blank('login'), name: 'Poslužitelj', password: 'tajna' };
    const sealed = await sealSecret(first, secret);
    const item: SealedItem = {
      id: 'x',
      collection: 'c',
      folder: null,
      ...sealed,
      attachments: [],
      created_at: '',
      updated_at: '',
      updated_by: null,
      trashed_at: null,
    };
    const opened = await openItem(first, item);
    expect(opened.secret).toEqual(secret);
    const second = random(32);
    const moved = { ...item, key: (await sealSecret(second, secret, opened.key)).key };
    expect((await openItem(second, moved)).secret).toEqual(secret);
    await expect(openItem(second, item)).rejects.toThrow();
  });

  it('remembers the password it held before', () => {
    const before = { ...blank('login'), password: 'staro' };
    const after = changed(before, { ...before, password: 'novo' });
    expect(after.history.map((entry) => entry.password)).toEqual(['staro']);
    expect(changed(after, { ...after, name: 'x' }).history).toHaveLength(1);
  });

  it('is given a generated password with each set it asks for', () => {
    const password = generated({ length: 24, upper: true, digits: true, symbols: true });
    expect(password).toHaveLength(24);
    expect(password).toMatch(/[a-z]/);
    expect(password).toMatch(/[A-Z]/);
    expect(password).toMatch(/[0-9]/);
    expect(password).toMatch(/[^a-zA-Z0-9]/);
    expect(generated({ length: 8, upper: false, digits: false, symbols: false })).toMatch(
      /^[a-z]{8}$/,
    );
  });
});

describe('a one-time code', () => {
  it('is RFC 6238’s', async () => {
    const secret = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ';
    const totp = parseTotp(`otpauth://totp/Primjer:ana?secret=${secret}&digits=8&period=30`)!;
    expect(await totpCode(totp, 59_000)).toBe('94287082');
    expect(await totpCode(totp, 1_111_111_109_000)).toBe('07081804');
    expect(await totpCode(parseTotp(secret.toLowerCase().match(/.{4}/g)!.join(' '))!, 59_000)).toBe(
      '287082',
    );
    expect(parseTotp('nije tajna')).toBeNull();
    expect(parseTotp('otpauth://hotp/x?secret=GEZDGNBV')).toBeNull();
  });
});

describe('an export from another password manager', () => {
  it('is read as RFC 4180 has it', () => {
    expect(parseCsv('﻿a,"b,""c""\nd"\r\n1,2\n\n')).toEqual([
      ['a', 'b,"c"\nd'],
      ['1', '2'],
    ]);
  });

  it('comes from Chrome, Firefox, KeePass and Bitwarden', () => {
    const chrome = imported(
      'name,url,username,password,note\nBanka,https://banka.hr,ana,t1,bilj\n',
    );
    expect(chrome.format).toBe('chrome');
    expect(chrome.items[0]).toMatchObject({ folder: [] });
    expect(chrome.items[0].secret).toMatchObject({
      name: 'Banka',
      urls: ['https://banka.hr'],
      username: 'ana',
      password: 't1',
      notes: 'bilj',
    });
    const firefox = imported(
      '"url","username","password","httpRealm","formActionOrigin","guid"\n"https://mail.example.com","ana","t2","","",""\n',
    );
    expect(firefox.items[0].secret).toMatchObject({ name: 'mail.example.com', password: 't2' });
    const keepass = imported(
      '"Group","Title","Username","Password","URL","Notes","TOTP"\n"Root/Posao/Mreža","VPN","ana","t3","vpn.example.com","","JBSWY3DP"\n',
    );
    expect(keepass.format).toBe('keepassxc');
    expect(keepass.items[0].secret).toMatchObject({ name: 'VPN', totp: 'JBSWY3DP' });
    expect(keepass.items[0].folder).toEqual(['Posao', 'Mreža']);
    const bitwarden = imported(
      JSON.stringify({
        encrypted: false,
        folders: [{ id: 'f1', name: 'Posao/Git' }],
        items: [
          {
            type: 1,
            folderId: 'f1',
            name: 'Git',
            login: { username: 'ana', password: 't4', uris: [{ uri: 'https://git.example.com' }] },
          },
          { type: 2, name: 'Alarm', notes: '1234' },
          { type: 3, name: 'Kartica' },
        ],
      }),
    );
    expect(bitwarden.skipped).toBe(1);
    expect(bitwarden.items.map(({ secret, folder }) => [secret.kind, secret.name, folder])).toEqual(
      [
        ['login', 'Git', ['Posao', 'Git']],
        ['note', 'Alarm', []],
      ],
    );
    expect(() => imported('{"encrypted": true, "items": []}')).toThrow(Unreadable);
    expect(() => imported('a,b\n1,2')).toThrow(Unreadable);
  });

  it('goes back out as Bitwarden reads it', () => {
    const items = [
      {
        secret: {
          ...blank('login'),
          name: 'Git',
          username: 'ana',
          password: 't',
          urls: ['https://git'],
        },
        folder: ['Posao', 'Razvoj'],
      },
      { secret: { ...blank('note'), name: 'Alarm', notes: '1234' }, folder: [] },
    ];
    expect(imported(exported(items)).items).toEqual(items);
  });

  it('carries a mail key out in a note, as PEM every tool reads', () => {
    const mailkey = {
      format: 'smime' as const,
      addresses: ['ana@example.com'],
      fingerprint: 'ab'.repeat(32),
      expires: null,
      private: 'QUJD',
      public: ['REVG'],
    };
    const secret = { ...blank('mailkey'), name: 'Ana', notes: 'Posao', mailkey };
    const [item] = JSON.parse(exported([{ secret, folder: [] }])).items;
    expect([item.type, item.notes]).toEqual([
      2,
      'Posao\n\n-----BEGIN PRIVATE KEY-----\nQUJD\n-----END PRIVATE KEY-----\n' +
        '-----BEGIN CERTIFICATE-----\nREVG\n-----END CERTIFICATE-----',
    ]);
  });
});

describe('folders', () => {
  const folders: Folder[] = [
    { id: 'a', parent: null, name: 'Posao' },
    { id: 'b', parent: 'a', name: 'Razvoj' },
    { id: 'c', parent: null, name: 'Banke' },
  ];

  it('lie in a tree and name their path', () => {
    expect(pathOf('b', folders)).toEqual(['Posao', 'Razvoj']);
    expect(pathOf(null, folders)).toEqual([]);
    expect(counted(folders, ['b', 'b', null, 'a', 'c'])).toEqual(
      new Map([
        ['b', 2],
        ['a', 3],
        ['c', 1],
      ]),
    );
    const order = laidOut(folders, (x, y) => x.localeCompare(y));
    expect(order.map(({ folder, depth }) => [folder.name, depth])).toEqual([
      ['Banke', 0],
      ['Posao', 0],
      ['Razvoj', 1],
    ]);
  });

  it('are made only where a path needs them, those of one name reused', () => {
    const { made, ends } = planned(
      [['posao', 'Razvoj'], ['Posao', 'Mreža'], [], ['Kupnja']],
      folders,
    );
    expect(made.map(({ parent, name }) => [parent, name])).toEqual([
      ['a', 'Mreža'],
      [null, 'Kupnja'],
    ]);
    expect(ends).toEqual(['b', made[0].id, null, made[1].id]);
  });
});
