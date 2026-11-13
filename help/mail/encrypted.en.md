# Encrypted and signed mail

Ponistra reads and sends messages signed and encrypted with S/MIME and OpenPGP, with a key you keep in the vault.

## How to use it

### Reading an encrypted message

1. Open a message marked with a lock. Above it, it says {t:mail.sealed.encrypted}.
2. When the vault is locked, it says {t:mail.sealed.locked} Type the vault's password and press {t:vault.unlock}, or unlock it with a passkey.
3. The message opens with its text, images and attachments. Press an attachment's name to save it.

### Checking a signature

Above a signed message the outcome of the check is shown:

- {t:mail.signed.valid}, with the signer's address.
- {t:mail.signed.changed}. If you know the sender changed their key, press {t:mail.signed.accept}.
- {t:mail.signed.mismatch}, with the address the signature is for.
- {t:mail.signed.expired}
- {t:mail.signed.invalid}
- {t:mail.signed.unknown}. Load the sender's OpenPGP key as described below.

### Sending a signed or encrypted message

1. In the message form press {t:mail.sealing.sign}, {t:mail.sealing.encrypt} or both. The buttons appear when the vault holds a mail key of yours or when you answer an encrypted message.
2. When the vault is locked, unlock it below the form.
3. Press {t:mail.send} or {t:mail.later}.

### Recipients' keys

1. Open Settings, then {t:mail.senders}.
2. Under {t:mail.keys} are your published keys, marked {t:mail.keysOwn}, and the senders' keys Ponistra kept ({t:mail.keysNone} when there are none).
3. Press {t:mail.keysBring} and choose the OpenPGP public key (`.asc`) or certificate (`.cer`, `.crt`, `.pem`) of a person you want to write to encrypted.
4. Press {t:mail.keysRemove} beside a key that no longer holds.

## How it works

An encrypted message is opened in the browser with the vault's key. The opened content goes to the server only to be read like any message and its HTML cleaned; the server does not keep it. Images from other servers are never loaded in an encrypted message, so the sender cannot learn it was opened. When you close the message, the opened content leaves the browser too.

A sender's key is kept the first time you read a validly signed message of theirs, or from the Autocrypt header OpenPGP tools send. If they later sign with another key, you are told until you accept the new one. Only you see the keys kept for you, while the keys colleagues published from their vault are seen by the whole installation.

An encrypted message is encrypted to every recipient and to you. The form of your key for the sending address, S/MIME or OpenPGP, that every recipient has a key for is used. An S/MIME message that is also signed carries the signature inside the encryption, and OpenPGP signs inside the encrypted message.

A reply to an encrypted message is encrypted by default and quotes the opened text. A forwarded encrypted message carries its attachments opened, as attachments of the new message.

## Limits

- The subject, sender and recipients are not encrypted, only the body and attachments.
- Ponistra checks that a signature is valid and that the certificate is for the sender's address, and keeps the key with the first message. It does not check the certificate chain up to its issuer or its revocation.
- The search does not find the text of encrypted messages.
- An encrypted message cannot share documents by link; attach them as files.
- A reply to an encrypted message kept as unsent does not keep the quoted text.
- When the message is not encrypted to any of your keys, it says: {t:smime.notForMe} or {t:pgp.notForMe}
- 3DES encryption, ECDH keys and S/MIME authenticated encryption are not supported. It then says: {t:smime.unsupported} or {t:pgp.unsupported}
- When you have no vault, it says {t:mail.sealed.noVault} and when the vault holds no mail key, {t:mail.sealed.noKeys} Add the key to the vault.
- When the vault holds no key for the address you send from, it says {t:mail.sealing.noOwnKey} with the address.
- When there is no key for a recipient, it says {t:mail.sealing.noKeys} with their addresses. Load their key or turn {t:mail.sealing.encrypt} off.
- When a file is neither a key nor a certificate, it says: {t:pgp.notKey} or {t:smime.notCertificate}

## Related

- [Mail keys in the vault](help:vault/mail-keys)
- [Reading a message](help:mail/reading)
- [Writing a message](help:mail/composing)
