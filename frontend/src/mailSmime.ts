import * as asn1js from 'asn1js';
import * as pkijs from 'pkijs';
import type { Bytes } from './vault/crypto';

/** A certificate's key as the vault keeps it: the private key in PKCS #8 and the chain, the
 * user's own certificate first, each in DER. */
export interface SmimeKey {
  privateKey: Bytes;
  chain: Bytes[];
}

export interface Certified {
  fingerprint: string;
  addresses: string[];
  subject: string;
  issuer: string;
  notBefore: string;
  notAfter: string;
}

export interface Checked {
  valid: boolean;
  /** The certificate that signed, in DER. */
  signer: Bytes | null;
  /** What was signed: the content beside the signature, or the content inside it. */
  content: Bytes;
  signedAt: string | null;
}

/** Why a certificate or a message could not be used, by the key of its message. */
export class Unusable extends Error {}

const OID = {
  data: '1.2.840.113549.1.7.1',
  signedData: '1.2.840.113549.1.7.2',
  envelopedData: '1.2.840.113549.1.7.3',
  rsa: '1.2.840.113549.1.1.1',
  oaep: '1.2.840.113549.1.1.7',
  ec: '1.2.840.10045.2.1',
  email: '1.2.840.113549.1.9.1',
  contentType: '1.2.840.113549.1.9.3',
  messageDigest: '1.2.840.113549.1.9.4',
  signingTime: '1.2.840.113549.1.9.5',
  sha1: '1.3.14.3.2.26',
  sha256: '2.16.840.1.101.3.4.2.1',
  sha384: '2.16.840.1.101.3.4.2.2',
  sha512: '2.16.840.1.101.3.4.2.3',
  subjectAltName: '2.5.29.17',
  subjectKeyIdentifier: '2.5.29.14',
  commonName: '2.5.4.3',
  keyBag: '1.2.840.113549.1.12.10.1.1',
  shroudedKeyBag: '1.2.840.113549.1.12.10.1.2',
  certBag: '1.2.840.113549.1.12.10.1.3',
};
const AES_CBC: Record<string, number> = {
  '2.16.840.1.101.3.4.1.2': 128,
  '2.16.840.1.101.3.4.1.22': 192,
  '2.16.840.1.101.3.4.1.42': 256,
};
const HASHES: Record<string, string> = {
  [OID.sha1]: 'SHA-1',
  [OID.sha256]: 'SHA-256',
  [OID.sha384]: 'SHA-384',
  [OID.sha512]: 'SHA-512',
};
const CURVES: Record<string, string> = {
  '1.2.840.10045.3.1.7': 'P-256',
  '1.3.132.0.34': 'P-384',
  '1.3.132.0.35': 'P-521',
};

function bytes(buffer: ArrayBuffer | ArrayBufferView): Bytes {
  return buffer instanceof ArrayBuffer
    ? new Uint8Array(buffer)
    : new Uint8Array(
        buffer.buffer.slice(
          buffer.byteOffset,
          buffer.byteOffset + buffer.byteLength,
        ) as ArrayBuffer,
      );
}

function hex(data: Uint8Array): string {
  return Array.from(data, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

function equal(one: Uint8Array, other: Uint8Array): boolean {
  return one.length === other.length && one.every((byte, at) => byte === other[at]);
}

function parsed(der: Bytes): pkijs.Certificate {
  try {
    return pkijs.Certificate.fromBER(der);
  } catch {
    throw new Unusable('smime.notCertificate');
  }
}

function nameOf(name: pkijs.RelativeDistinguishedNames): string {
  const common = name.typesAndValues.find((each) => each.type === OID.commonName);
  const shown = common ?? name.typesAndValues.find((each) => each.type === OID.email);
  return shown ? String(shown.value.valueBlock.value) : '';
}

/** The addresses a certificate is for: its alternative names, else the address in its name. */
function addressesOf(certificate: pkijs.Certificate): string[] {
  const named = certificate.extensions?.find((each) => each.extnID === OID.subjectAltName);
  const alternative = named?.parsedValue as pkijs.AltName | undefined;
  const found = (alternative?.altNames ?? [])
    .filter((each) => each.type === 1)
    .map((each) => String(each.value).toLowerCase());
  if (found.length > 0) return found;
  return certificate.subject.typesAndValues
    .filter((each) => each.type === OID.email)
    .map((each) => String(each.value.valueBlock.value).toLowerCase());
}

export async function described(der: Bytes): Promise<Certified> {
  const certificate = parsed(der);
  return {
    fingerprint: hex(bytes(await crypto.subtle.digest('SHA-256', der))),
    addresses: addressesOf(certificate),
    subject: nameOf(certificate.subject),
    issuer: nameOf(certificate.issuer),
    notBefore: certificate.notBefore.value.toISOString(),
    notAfter: certificate.notAfter.value.toISOString(),
  };
}

function der(value: pkijs.PkiObject): Bytes {
  return bytes(value.toSchema().toBER());
}

/** The key and the chain a PKCS #12 file (.p12, .pfx) holds, opened with its password. */
export async function fromPkcs12(file: Bytes, password: string): Promise<SmimeKey> {
  const secret = bytes(new TextEncoder().encode(password));
  let pfx: pkijs.PFX;
  try {
    pfx = pkijs.PFX.fromBER(file);
  } catch {
    throw new Unusable('smime.notPkcs12');
  }
  try {
    await pfx.parseInternalValues({ password: secret.buffer, checkIntegrity: true });
    const safe = pfx.parsedValue?.authenticatedSafe;
    if (!safe) throw new Unusable('smime.notPkcs12');
    await safe.parseInternalValues({
      safeContents: safe.safeContents.map(() => ({ password: secret.buffer })),
    });
    const bags = (safe.parsedValue?.safeContents ?? []).flatMap(
      (each: { value: pkijs.SafeContents }) => each.value.safeBags,
    );
    let privateKey: Bytes | null = null;
    const certificates: pkijs.Certificate[] = [];
    for (const bag of bags) {
      if (bag.bagId === OID.shroudedKeyBag) {
        const shrouded = bag.bagValue as pkijs.PKCS8ShroudedKeyBag;
        const opened = await pkijs.getCrypto(true).decryptEncryptedContentInfo({
          encryptedContentInfo: new pkijs.EncryptedContentInfo({
            contentType: OID.data,
            contentEncryptionAlgorithm: shrouded.encryptionAlgorithm,
            encryptedContent: shrouded.encryptedData,
          }),
          password: secret.buffer,
        });
        privateKey = new Uint8Array(opened);
      } else if (bag.bagId === OID.keyBag) {
        privateKey = der(bag.bagValue as pkijs.PrivateKeyInfo);
      } else if (bag.bagId === OID.certBag) {
        const value = (bag.bagValue as pkijs.CertBag).parsedValue;
        if (value instanceof pkijs.Certificate) certificates.push(value);
      }
    }
    if (!privateKey || certificates.length === 0) throw new Unusable('smime.noKey');
    return { privateKey, chain: await ordered(privateKey, certificates) };
  } catch (error) {
    if (error instanceof Unusable) throw error;
    const text = String(error);
    if (/password|integrity|MAC/i.test(text)) throw new Unusable('smime.wrongPassword');
    // RC2 and 3DES, which Windows long exported with, are no algorithms WebCrypto has.
    throw new Unusable('smime.oldPkcs12');
  }
}

/** The certificates with the one the key belongs to first. */
async function ordered(privateKey: Bytes, certificates: pkijs.Certificate[]): Promise<Bytes[]> {
  const info = pkijs.PrivateKeyInfo.fromBER(privateKey);
  const own = await Promise.all(
    certificates.map(async (certificate) => {
      const key = certificate.subjectPublicKeyInfo;
      if (info.privateKeyAlgorithm.algorithmId !== key.algorithm.algorithmId) return false;
      if (
        info.parsedKey instanceof pkijs.RSAPrivateKey &&
        key.parsedKey instanceof pkijs.RSAPublicKey
      )
        return equal(
          info.parsedKey.modulus.valueBlock.valueHexView,
          key.parsedKey.modulus.valueBlock.valueHexView,
        );
      return info.privateKeyAlgorithm.algorithmId === OID.ec;
    }),
  );
  const first = own.indexOf(true);
  if (first < 0) throw new Unusable('smime.noKey');
  return [certificates[first], ...certificates.filter((_, at) => at !== first)].map(der);
}

function bigint(data: Uint8Array): bigint {
  let value = 0n;
  for (const byte of data) value = (value << 8n) | BigInt(byte);
  return value;
}

function power(base: bigint, exponent: bigint, modulus: bigint): bigint {
  let result = 1n;
  base %= modulus;
  while (exponent > 0n) {
    if (exponent & 1n) result = (result * base) % modulus;
    base = (base * base) % modulus;
    exponent >>= 1n;
  }
  return result;
}

/** RSAES-PKCS1-v1_5, which WebCrypto does not decrypt and most S/MIME mail still encrypts its key
 * with (RFC 8017, 7.2.2). The key is the user's own and the ciphertext a message they hold, so
 * there is nobody to learn from how long this takes. */
function rsaOpened(privateKey: Bytes, sealed: Uint8Array): Uint8Array {
  const key = pkijs.PrivateKeyInfo.fromBER(privateKey).parsedKey;
  if (!(key instanceof pkijs.RSAPrivateKey) || key.otherPrimeInfos?.length)
    throw new Unusable('smime.unsupported');
  const integer = (value: asn1js.Integer) => bigint(value.valueBlock.valueHexView);
  const [n, p, q] = [integer(key.modulus), integer(key.prime1), integer(key.prime2)];
  const [dp, dq, qinv] = [integer(key.exponent1), integer(key.exponent2), integer(key.coefficient)];
  const c = bigint(sealed);
  const m1 = power(c, dp, p);
  const m2 = power(c, dq, q);
  const h = (((m1 - m2) % p) + p) % p;
  let m = m2 + ((qinv * h) % p) * q;
  const size = Math.ceil(n.toString(16).length / 2);
  const encoded = new Uint8Array(size);
  for (let at = size - 1; at >= 0; at--) {
    encoded[at] = Number(m & 0xffn);
    m >>= 8n;
  }
  const end = encoded.indexOf(0, 2);
  if (encoded[0] !== 0 || encoded[1] !== 2 || end < 10) throw new Unusable('smime.notForMe');
  return encoded.slice(end + 1);
}

function isFor(info: pkijs.KeyTransRecipientInfo, certificate: pkijs.Certificate): boolean {
  if (info.rid instanceof pkijs.IssuerAndSerialNumber)
    return (
      info.rid.issuer.isEqual(certificate.issuer) &&
      info.rid.serialNumber.isEqual(certificate.serialNumber)
    );
  const identifier = certificate.extensions?.find(
    (each) => each.extnID === OID.subjectKeyIdentifier,
  )?.parsedValue as asn1js.OctetString | undefined;
  return Boolean(
    identifier &&
    equal(
      identifier.valueBlock.valueHexView,
      (info.rid as asn1js.OctetString).valueBlock.valueHexView,
    ),
  );
}

async function sessionKey(info: pkijs.KeyTransRecipientInfo, key: SmimeKey): Promise<Uint8Array> {
  const sealed = info.encryptedKey.valueBlock.valueHexView;
  const algorithm = info.keyEncryptionAlgorithm.algorithmId;
  if (algorithm === OID.rsa) return rsaOpened(key.privateKey, sealed);
  if (algorithm !== OID.oaep) throw new Unusable('smime.unsupported');
  const params = info.keyEncryptionAlgorithm.algorithmParams
    ? new pkijs.RSAESOAEPParams({ schema: info.keyEncryptionAlgorithm.algorithmParams })
    : new pkijs.RSAESOAEPParams();
  const hash = HASHES[params.hashAlgorithm.algorithmId];
  if (!hash) throw new Unusable('smime.unsupported');
  const imported = await crypto.subtle.importKey(
    'pkcs8',
    key.privateKey,
    { name: 'RSA-OAEP', hash },
    false,
    ['decrypt'],
  );
  return new Uint8Array(
    await crypto.subtle.decrypt({ name: 'RSA-OAEP' }, imported, new Uint8Array(sealed)),
  );
}

/** What an EnvelopedData encrypted to the key's certificate carries. */
export async function opened(sealed: Bytes, key: SmimeKey): Promise<Bytes> {
  const info = pkijs.ContentInfo.fromBER(sealed);
  if (info.contentType !== OID.envelopedData) throw new Unusable('smime.unsupported');
  const enveloped = new pkijs.EnvelopedData({ schema: info.content });
  const own = parsed(key.chain[0]);
  const recipient = enveloped.recipientInfos.find(
    (each) => each.variant === 1 && isFor(each.value as pkijs.KeyTransRecipientInfo, own),
  );
  if (!recipient) throw new Unusable('smime.notForMe');
  const raw = await sessionKey(recipient.value as pkijs.KeyTransRecipientInfo, key);
  const content = enveloped.encryptedContentInfo;
  const length = AES_CBC[content.contentEncryptionAlgorithm.algorithmId];
  if (!length || raw.length * 8 !== length) throw new Unusable('smime.unsupported');
  const iv = (content.contentEncryptionAlgorithm.algorithmParams as asn1js.OctetString).valueBlock
    .valueHexView;
  const aes = await crypto.subtle.importKey('raw', bytes(raw), 'AES-CBC', false, ['decrypt']);
  return bytes(
    await crypto.subtle.decrypt(
      { name: 'AES-CBC', iv: bytes(iv) },
      aes,
      content.getEncryptedContent(),
    ),
  );
}

function signedOf(sealed: Bytes): pkijs.SignedData {
  const info = pkijs.ContentInfo.fromBER(sealed);
  if (info.contentType !== OID.signedData) throw new Unusable('smime.unsupported');
  return new pkijs.SignedData({ schema: info.content });
}

/** Whether a CMS SignedData signs `content` (beside it), or the content it carries itself. */
export async function checked(signature: Bytes, content: Bytes | null): Promise<Checked> {
  const signed = signedOf(signature);
  const carried = signed.encapContentInfo.eContent;
  const inside = content ?? (carried ? bytes(carried.getValue()) : null);
  if (!inside) throw new Unusable('smime.unsupported');
  let result: pkijs.SignedDataVerifyResult;
  try {
    result = await signed.verify({
      signer: 0,
      data: content ? content.buffer : undefined,
      extendedMode: true,
      checkChain: false,
    });
  } catch (error) {
    result = error as pkijs.SignedDataVerifyResult;
  }
  const time = signed.signerInfos[0]?.signedAttrs?.attributes.find(
    (each) => each.type === OID.signingTime,
  )?.values[0] as asn1js.UTCTime | asn1js.GeneralizedTime | undefined;
  return {
    valid: result.signatureVerified === true,
    signer: result.signerCertificate ? der(result.signerCertificate) : null,
    content: inside,
    signedAt: time ? time.toDate().toISOString() : null,
  };
}

function signing(certificate: pkijs.Certificate): RsaHashedImportParams | EcKeyImportParams {
  const key = certificate.subjectPublicKeyInfo.algorithm;
  if (key.algorithmId === OID.rsa) return { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' };
  const curve =
    key.algorithmParams instanceof asn1js.ObjectIdentifier
      ? CURVES[key.algorithmParams.valueBlock.toString()]
      : undefined;
  if (key.algorithmId === OID.ec && curve) return { name: 'ECDSA', namedCurve: curve };
  throw new Unusable('smime.unsupported');
}

/** A detached signature over the entity, with the user's certificates in it so that whoever
 * receives it can check it and encrypt back. */
export async function signature(
  entity: Bytes,
  key: SmimeKey,
): Promise<{ data: Bytes; micalg: string }> {
  const chain = key.chain.map(parsed);
  const own = chain[0];
  const privateKey = await crypto.subtle.importKey('pkcs8', key.privateKey, signing(own), false, [
    'sign',
  ]);
  const digest = await crypto.subtle.digest('SHA-256', entity);
  const signed = new pkijs.SignedData({
    version: 1,
    encapContentInfo: new pkijs.EncapsulatedContentInfo({ eContentType: OID.data }),
    signerInfos: [
      new pkijs.SignerInfo({
        version: 1,
        sid: new pkijs.IssuerAndSerialNumber({
          issuer: own.issuer,
          serialNumber: own.serialNumber,
        }),
        signedAttrs: new pkijs.SignedAndUnsignedAttributes({
          type: 0,
          attributes: [
            new pkijs.Attribute({
              type: OID.contentType,
              values: [new asn1js.ObjectIdentifier({ value: OID.data })],
            }),
            new pkijs.Attribute({
              type: OID.signingTime,
              values: [new asn1js.UTCTime({ valueDate: new Date() })],
            }),
            new pkijs.Attribute({
              type: OID.messageDigest,
              values: [new asn1js.OctetString({ valueHex: digest })],
            }),
          ],
        }),
      }),
    ],
    certificates: chain,
  });
  await signed.sign(privateKey, 0, 'SHA-256', entity.buffer);
  const info = new pkijs.ContentInfo({
    contentType: OID.signedData,
    content: signed.toSchema(true),
  });
  return { data: der(info), micalg: 'sha-256' };
}

/** The entity encrypted to each certificate, AES-256 for the content and RSA-OAEP or ECDH for its
 * key, as current Outlook and Thunderbird read. */
export async function sealed(entity: Bytes, certificates: Bytes[]): Promise<Bytes> {
  const enveloped = new pkijs.EnvelopedData();
  for (const each of certificates)
    enveloped.addRecipientByCertificate(parsed(each), { oaepHashAlgorithm: 'SHA-256' });
  await enveloped.encrypt({ name: 'AES-CBC', length: 256 } as AesKeyGenParams, entity.buffer);
  const info = new pkijs.ContentInfo({
    contentType: OID.envelopedData,
    content: enveloped.toSchema(),
  });
  return der(info);
}
