# Vault items

A vault item is a login with a username, password, one-time code and addresses, a note with free text, or a mail key.

## How to use it

### A new item

1. In an open collection press {t:vault.newItem}. For a note, choose {t:vault.newNote} in the menu of other actions.
2. Under {t:vault.kind} choose {t:vault.kind.login} or {t:vault.kind.note}. For a {t:vault.kind.mailkey} see [Mail keys in the vault](help:vault/mail-keys).
3. Type the {t:tree.name}, and for a login also the {t:vault.username}, {t:vault.password}, {t:vault.totp} and {t:vault.urls}.
4. If you wish, type {t:vault.notes}.
5. Press {t:tree.create}.

### Generating a password

1. Beside the password field press {t:vault.generate}.
2. Choose the {t:vault.generator.length} and {t:vault.generator.upper}, {t:vault.generator.digits} and {t:vault.generator.symbols}.
3. Press {t:vault.generator.again} for another password or {t:vault.generator.use} to put it in the field.

### Working with an open item

1. Choose the item in the list.
2. Beside the fields press {t:vault.copyUsername}, {t:vault.copyPassword} or {t:vault.copyTotp}.
3. You reveal the password with {t:vault.show} and hide it with {t:vault.hide}.
4. Beside each {t:vault.url} field press {t:vault.openUrl}.
5. Press {t:vault.edit} to change it, then {t:tree.save}.
6. Under {t:vault.history} are the item's earlier passwords, each of which can be copied.

### Attachments

1. In an open item press {t:vault.attach} and choose the files. Meanwhile the button shows: {t:vault.attaching}
2. Under {t:vault.attachments} press an attachment's name to download it.
3. To remove one, press {t:vault.removeAttachment}.

## How it works

The name, username, password, code, addresses, notes and attachments are encrypted in the browser. Only what is encrypted goes to the server, and an attachment is opened only in the browser when it is downloaded.

What you copy is cleared from the clipboard after 30 seconds, unless you have copied something else from the vault meanwhile. The one-time code is computed in the browser and changes every 30 seconds, unless the address sets otherwise; beside it stands how many seconds are left. For a one-time code, type an `otpauth://` address or the secret key the site shows beside the QR code.

When you change the password, the previous one is kept among the earlier passwords. The last 10 are kept. Below the item it says {t:vault.changed} with the time of the last change.

A generated password has 20 characters by default and contains capitals, digits and symbols. It always has lower-case letters and at least one character of each kind chosen.

In a shared collection, showing and copying a password or a one-time code is noted in the collection's log. In My vault nothing is noted.

## Limits

- When what you typed is not a one-time code secret, it says: {t:vault.totpInvalid}
- In a collection where you can only read, you cannot change an item or add attachments to it.
- A generated password is from 8 to 64 characters long.

## Related

- [Folders and moving](help:vault/folders)
- [The vault's trash](help:vault/trash)
- [Shared collections](help:vault/collections)
- [Mail keys in the vault](help:vault/mail-keys)
