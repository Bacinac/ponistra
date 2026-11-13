# Mail keys in the vault

A mail key in the vault signs your messages and opens the encrypted messages you receive, an S/MIME certificate or an OpenPGP key.

## How to use it

### Loading an existing key

1. In an open collection choose {t:vault.newMailKey} in the menu of other actions. You can also press {t:vault.newItem} and choose {t:vault.kind.mailkey}.
2. Press {t:vault.mailkey.fromFile} and choose the file: an S/MIME certificate as `.p12` or `.pfx`, or an OpenPGP secret key as `.asc`.
3. Type the {t:vault.mailkey.password} the file is protected with. An unprotected OpenPGP key loads with the field empty.
4. Press {t:vault.mailkey.open}. The kind of key, its addresses, its fingerprint and the date it is valid until appear below.
5. Change the {t:tree.name} if you like, then press {t:tree.create}.

### A new OpenPGP key

1. Choose {t:vault.newMailKey}.
2. Press {t:vault.mailkey.make}.
3. Under {t:vault.mailkey.address} check the address; your user account's address is the default.
4. Press {t:vault.mailkey.create}, then {t:tree.create}.

### An open key

An open item says whether it is an {t:vault.mailkey.smime} or an {t:vault.mailkey.pgp}, the addresses it holds for, its fingerprint and {t:vault.mailkey.expires} or {t:vault.mailkey.expired}. {t:vault.mailkey.public} saves its public part, a `.cer` certificate or an `.asc` key, which you send to those who want to write to you encrypted.

## How it works

The file is opened in the browser. The vault keeps the secret key encrypted like the passwords, so the server never sees it.

When you save a new key, its public part is published in Ponistra for every address it holds. Colleagues in the same installation can then send you encrypted messages, and your sent encrypted messages are encrypted to you too, so you can read them again.

A new OpenPGP key uses Curve25519, which GnuPG, Thunderbird and other OpenPGP tools read. By default it does not expire.

A key in a shared collection can be used by all its members, for instance for a shared mailbox.

## Limits

- A key does not change once saved. For a new certificate add a new item, and delete the old one when you no longer need it for old messages.
- When the file is not PKCS #12, it says: {t:smime.notPkcs12}
- When the password is wrong, it says: {t:smime.wrongPassword} or {t:pgp.wrongPassphrase}
- Older `.p12` files are protected with RC2 or 3DES encryption, which the browser cannot open. It then says: {t:smime.oldPkcs12} In Windows, choose AES256-SHA256 encryption when exporting the certificate.
- When the file holds no secret key, it says: {t:smime.noKey}
- When an OpenPGP file holds only a public key and no secret one, it says: {t:pgp.notPrivate} Another person's public key is loaded in the Mail settings, see [Encrypted and signed mail](help:mail/encrypted).

## Related

- [Encrypted and signed mail](help:mail/encrypted)
- [Vault items](help:vault/items)
- [Import and export of the vault](help:vault/transfer)
