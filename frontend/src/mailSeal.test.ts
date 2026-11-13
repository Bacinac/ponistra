import { describe, expect, it } from 'vitest';
import fixture from './mailSeal.fixture.json';
import * as pgp from './mailPgp';
import * as smime from './mailSmime';
import { fromBase64, textBytes, type Bytes } from './vault/crypto';

const entity = textBytes('Content-Type: text/plain; charset=utf-8\r\n\r\nCijena je 100 €.\r\n');

describe('S/MIME', () => {
  it('opens a key brought in PKCS #12 and reads what another tool encrypted and signed', async () => {
    await expect(smime.fromPkcs12(fromBase64(fixture.p12), 'kriva')).rejects.toThrow(
      'smime.wrongPassword',
    );
    const key = await smime.fromPkcs12(fromBase64(fixture.p12), 'lozinka');
    const certified = await smime.described(key.chain[0]);
    expect(certified.addresses).toEqual(['ana@example.com']);
    const content = fromBase64(fixture.content);
    expect(await smime.opened(fromBase64(fixture.enveloped), key)).toEqual(content);
    const checked = await smime.checked(fromBase64(fixture.signature), content);
    expect(checked.valid).toBe(true);
    const changed = new Uint8Array(content) as Bytes;
    changed[changed.length - 3] ^= 1;
    expect((await smime.checked(fromBase64(fixture.signature), changed)).valid).toBe(false);
  });

  it('signs and encrypts so that it reads its own back', async () => {
    const key = await smime.fromPkcs12(fromBase64(fixture.p12), 'lozinka');
    const signed = await smime.signature(entity, key);
    expect(signed.micalg).toBe('sha-256');
    expect((await smime.checked(signed.data, entity)).valid).toBe(true);
    const sealed = await smime.sealed(entity, [key.chain[0]]);
    expect(await smime.opened(sealed, key)).toEqual(entity);
  });
});

describe('OpenPGP', () => {
  it('signs, encrypts and reads back, and knows a signature over changed bytes', async () => {
    const armored = await pgp.generated('Ana', 'ana@example.com');
    const described = await pgp.described(await pgp.privateKey(armored));
    expect(described.addresses).toEqual(['ana@example.com']);
    const keys = await pgp.publicKeys(described.public);
    const signed = await pgp.signature(entity, armored);
    expect(signed.micalg).toMatch(/^pgp-sha(256|384|512)$/);
    const checked = await pgp.checked(entity, signed.data, keys);
    expect([checked.valid, checked.signer]).toEqual([true, described.fingerprint]);
    const changed = textBytes('Content-Type: text/plain\r\n\r\nCijena je 900 €.\r\n');
    expect((await pgp.checked(changed, signed.data, keys)).valid).toBe(false);
    const sealed = await pgp.sealed(entity, keys, armored);
    const opened = await pgp.opened(sealed, armored, keys);
    expect(opened.data).toEqual(entity);
    expect(opened.checked?.valid).toBe(true);
    const other = await pgp.generated('Iva', 'iva@example.com');
    await expect(pgp.opened(sealed, other, keys)).rejects.toThrow('pgp.notForMe');
  });
});
