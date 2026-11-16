# Authenticator app

An authenticator app on your phone gives the code a sign-in with a password asks for as a second step, so the password alone no longer opens your account.

## How to use it

### Adding the app

1. In Settings open {t:settings.signIn}; {t:authenticator.title} is below the passkeys.
2. Press {t:authenticator.add}. If Ponistra asks, confirm that it is you.
3. Open the authenticator app on your phone and scan the QR code, or type into it the secret written below the code.
4. Type the six-digit code the app shows into {t:authenticator.code} and press {t:authenticator.confirm}. Until you confirm, the app is not added; {t:tree.cancel} gives up.

### Signing in with the app

1. On the sign-in page type {t:auth.email} and {t:auth.password} and press {t:auth.signIn}.
2. {t:auth.secondTitle} opens. Type the code from the app into {t:authenticator.code} and press {t:auth.signIn}.
3. If the installation asks for a second step and you have a passkey, you can press {t:confirm.passkey} instead of typing a code.
4. {t:auth.back} returns to typing the email and password.

### When the administrator asks for a second step

1. After a sign-in with a password the page {t:authenticator.dueTitle} appears. Until a second step is added, nothing else in Ponistra is available.
2. Add the app as above, or below it add a passkey where the installation allows sign-in with a passkey.
3. If you cannot add one now, press {t:auth.signOut}.

### Removing it

1. In Settings, under {t:settings.signIn}, {t:authenticator.title} shows {t:authenticator.since} and the date it was added.
2. Press {t:authenticator.remove} and confirm in the dialog {t:authenticator.removeTitle} Ponistra may ask you to confirm that it is you.

## How it works

The code changes every 30 seconds. Ponistra also accepts the code of the 30 seconds before and after, in case the phone's clock runs a little slow or fast, and never accepts the same code twice.

The app's secret is kept encrypted in the installation's database. It is shown only once, when adding; for a new phone, remove the app and add it again.

Once the app is added, every sign-in with a password asks for a code, even where the installation does not ask for a second step. [Confirming your identity](help:account/confirm) with the password asks for it too. A sign-in with a passkey and a sign-in at the organisation's provider do not ask for a code: the passkey already is a second step, and the provider applies its own rule.

The second step has to be finished within 5 minutes of typing the password. Every wrong code is recorded as a failed sign-in and counts towards locking the account, and after 3 wrong codes the password has to be typed again.

When you add the app, the browsers where you turned notifications on get a notification about it. The installation's administrator sees in its journal when the app was added or removed.

## Limits

- {t:authenticator.invalid} Check that the phone's clock is right and type the code the app shows now.
- {t:auth.secondExpired} Shown once 5 minutes have passed or after 3 wrong codes.
- {t:authenticator.last} The installation asks for a second step and you have no passkey to stand in for it. Add a passkey first.
- Without the phone with the app, a sign-in with a password does not pass. An administrator can set you a new password; that removes the app, and you add it again.
- Ponistra keeps one app per account.

## Related

- [Sign-in and the way of signing in](help:account/sign-in)
- [Passkeys](help:account/passkeys)
- [Confirming your identity](help:account/confirm)
