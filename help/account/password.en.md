# Password

With your account's password you sign in to Ponistra and confirm sensitive actions when you have no passkey.

## How to use it

1. In Settings open {t:settings.signIn}; {t:password.title} is below {t:passkeys.title}.
2. Type {t:password.new}.
3. Press {t:password.change}.
4. If Ponistra asks, confirm that it is you.
5. When done, below the field it says: {t:password.changed}

## How it works

Ponistra does not keep the password, only a digest of it from which the password cannot be read. The browser you changed it in stays signed in.

The account's password is not the vault's password. The vault has a password of its own, which this change does not touch.

The installation's administrator sees in its journal that the password was changed, never the password itself.

## Limits

A new password must have at least 8 characters, may not be digits only, may not be too similar to your name or email address and may not be among commonly used passwords. If it is not so, below the field it says what it lacks.

If an administrator requires a passkey for your account, you sign in with a password only until you add the passkey.

When you sign in with the organisation's directory password, the password is changed in the directory, and here it says {t:error.password_in_directory}

## Related

- [Confirming it is you](help:account/confirm)
- [Passkeys](help:account/passkeys)
- [The vault's password and code](help:vault/recovery)
