# Sign-in and sharing rules

An administrator decides whether signing in with a passkey is allowed or required, whether a sign-in with a password asks for a second step, and who may make a link for someone outside the installation.

## How to use it

1. On the {t:users.title} page, in the {t:policy.title} section, under {t:policy.passkeys} choose {t:policy.passkeys.off}, {t:policy.passkeys.nobody}, {t:policy.passkeys.administrators} or {t:policy.passkeys.everyone}.
2. Turn {t:policy.secondFactor} on or off.
3. In the {t:policy.outside.title} section, under {t:policy.outside}, choose {t:policy.outside.nobody}, {t:policy.outside.administrators} or {t:policy.outside.everyone}.

## How it works

With {t:policy.passkeys.off} the sign-in page offers no passkey and a sign-in with one is refused; users sign in with a password or at the organisation's provider. With {t:policy.passkeys.nobody} everyone chooses whether to add a passkey.

The passkey rule applies from the next sign-in. Whoever must have a passkey signs in with a password only until they add one, and after that only with the passkey. A user without a passkey first adds one after signing in with the password.

With {t:policy.secondFactor} a sign-in with a password also asks for a code from an [authenticator app](help:account/authenticator) or a passkey, where signing in with a passkey is not off. A user with neither first adds one of them after signing in with the password. A user who added the app themselves gives its code even when this is off. A sign-in at the organisation's provider asks for no second step in Ponistra, as the provider asks for it by its own rule.

If such a user loses their device, an administrator sets a new password for them under {t:users.edit}; this deletes their authenticator app and, where a passkey is required of them or the second step is on, their passkeys, and they add new ones at their next sign-in.

The sharing rule decides who may make a link with which someone without an account in the installation opens a board. With {t:policy.outside.nobody} all links already made stop working too.

Every change of the rules is written to the [journal](help:admin/journal).

## Limits

- Changing the rules may ask you to confirm that it is you.
- A user who must have a passkey cannot delete their last passkey.
- While the second step is on, a user cannot remove the one that is their only one: the authenticator app without a passkey, nor the last passkey without the app.

## Related

- [Authenticator app](help:account/authenticator)
- [Users](help:admin/users)
