# Sign-in and sharing rules

An administrator decides who must have a passkey to sign in and who may make a link for someone outside the installation.

## How to use it

1. On the {t:users.title} page, in the {t:policy.title} section, under {t:policy.passkeys} choose {t:policy.passkeys.nobody}, {t:policy.passkeys.administrators} or {t:policy.passkeys.everyone}.
2. In the {t:policy.outside.title} section, under {t:policy.outside}, choose {t:policy.outside.nobody}, {t:policy.outside.administrators} or {t:policy.outside.everyone}.

## How it works

The passkey rule applies from the next sign-in. Whoever must have a passkey signs in with a password only until they add one, and after that only with the passkey. A user without a passkey first adds one after signing in with the password.

If such a user loses their device, an administrator sets a new password for them under {t:users.edit}; this deletes their passkeys, and they add a new one at their next sign-in.

The sharing rule decides who may make a link with which someone without an account in the installation opens a board. With {t:policy.outside.nobody} all links already made stop working too.

Every change of the rules is written to the [journal](help:admin/journal).

## Limits

- Changing the rules may ask you to confirm that it is you.
- A user who must have a passkey cannot delete their last passkey.

## Related

- [Users](help:admin/users)
