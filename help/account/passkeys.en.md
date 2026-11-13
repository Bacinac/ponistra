# Passkeys

With a passkey you sign in with a fingerprint, your face or the device's PIN, without typing an email and password.

## How to use it

### Adding a passkey

1. In Settings open {t:passkeys.title}.
2. Type {t:passkeys.newName}, for example the device's name.
3. Press {t:passkeys.add}. Meanwhile the button shows: {t:passkeys.adding}
4. Confirm on the device with a fingerprint, face or PIN.
5. If Ponistra asks, confirm that it is you.

### Renaming and removing

1. In the passkey's row open the menu of actions.
2. Choose {t:tree.rename} and type the new name, then press {t:tree.save}.
3. Or choose {t:passkeys.delete} and confirm in the dialog {t:passkeys.deleteTitle}

### When an administrator requires a passkey

1. After signing in with a password, the page {t:passkeys.dueTitle} shows. Until a passkey is added, nothing else in Ponistra is available.
2. Type {t:passkeys.newName} and press {t:passkeys.add}.
3. If you cannot add a passkey now, press {t:auth.signOut}.

## How it works

Until there is a passkey, the page says: {t:passkeys.none}

The passkey stays on the device or in the password manager that keeps it, and Ponistra keeps only its public part. The list shows when each passkey was {t:passkeys.created} and when it was last used. When you add a passkey, the browsers where you turned notifications on get a notification of it.

A passkey added in a browser that supports it can also unlock your vault. That is turned on separately, in the vault's settings.

The installation's administrator sees in its journal when a passkey was added or removed, with its name.

## Limits

- {t:passkeys.unsupported} Sign in with a password then, or from another device.
- {t:passkeys.cancelled} It shows when you break off the confirmation on the device or its time runs out.
- {t:passkeys.kept} That device needs no second passkey.
- If signing in with a passkey is required of you, you cannot remove the last passkey.

## Related

- [Signing in and the sign-in method](help:account/sign-in)
- [Confirming it is you](help:account/confirm)
- [The vault's password and code](help:vault/recovery)
