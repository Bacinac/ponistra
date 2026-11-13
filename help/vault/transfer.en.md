# Import and export of the vault

You bring passwords from another password manager or browser into a vault collection, and export a collection to a file every password manager reads.

## How to use it

### Import

1. Open the collection you import into and choose {t:vault.import} in the menu of other actions.
2. Press {t:vault.importChoose} and choose the other manager's export.
3. The dialog shows the format recognised ({t:vault.format.bitwarden}, {t:vault.format.chrome}, {t:vault.format.firefox}, {t:vault.format.keepassxc} or {t:vault.format.keepass}), the {t:vault.importItems} and the {t:vault.importSkipped}.
4. Press {t:vault.importDo}.
5. After the import delete the file from the device.

### Export

1. Open the collection and choose {t:vault.export} in the menu of other actions.
2. Read the warning and press {t:vault.exportDo}.
3. If Ponistra asks, confirm that it is you. The browser saves a file named after the collection.

## How it works

The file is read in the browser and is not sent to the server. Logins and notes are encrypted in the browser and go into the open collection, together with the folders they were in. Bitwarden is read from a JSON or CSV export, the others from a CSV export. Cards and identities from Bitwarden are skipped.

The export is a file in Bitwarden's JSON format, with the passwords readable and with the collection's folders. Attachments are not exported. A mail key goes out as a note: the private key and certificates as PEM, an OpenPGP key as an OpenPGP text block, so other tools can load it again. Like the passwords, the private key in the export is not encrypted. Each export is noted in a shared collection's log.

## Limits

- Only the collection's owner may export, and anyone who can edit in it may import.
- When the file is an encrypted export, it says: {t:vault.unreadable.encrypted}
- When the file is not recognised, it says: {t:vault.unreadable.unknown}
- The exported file is not protected. Keep it as you would the vault and delete it once it is imported.

## Related

- [Vault](help:vault/overview)
- [Shared collections](help:vault/collections)
