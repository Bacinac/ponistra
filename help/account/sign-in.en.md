# Signing in and the sign-in method

On the {t:auth.title} page you enter Ponistra with a password or a passkey, and in the settings you choose what that page offers first.

## How to use it

### Signing in

1. Open your installation's address. While you are not signed in, the {t:auth.title} page shows.
2. Type {t:auth.email} and {t:auth.password}, then press {t:auth.signIn}. Meanwhile the button shows: {t:auth.signingIn}
3. Instead of a password you can press {t:auth.passkey} and confirm with a fingerprint, face or the device's PIN. While no sign-in method is chosen, passkeys kept on the device are also offered below the email field as soon as you open it.
4. If an administrator has connected the organisation's sign-in provider, the page also offers a button with its name. Press it, sign in at the provider, and the browser comes back to Ponistra signed in.

### Sign-in method

1. In Settings open {t:settings.signIn}; {t:signIn.choice} is at the top.
2. Choose {t:signIn.none}, {t:password.title} or {t:signIn.passkey}.
3. With the passkey chosen, the sign-in page offers only the {t:auth.passkey} button. To sign in with a password there, press {t:auth.withPassword}.

### Signing out

1. Press your initials in the top right corner, {t:frame.account}.
2. Choose {t:auth.signOut}. The search box offers the same.

## How it works

The sign-in method decides only what the sign-in page shows first, not what is allowed. The account keeps it for every device, and the browser keeps a copy for the sign-in page, which thus knows it before you sign in. {t:signIn.passkey} can be chosen only once you have at least one passkey. When you remove the last one, the choice goes back to {t:signIn.none}.

Each new sign-in is announced by a notification in the browsers where you turned notifications on, and the notification leads to the list of signed-in devices.

Signing out ends the sign-in only in that browser. Sign-ins on other devices remain.

A sign-in in a browser ends after 14 days without use and at the latest 30 days after signing in, however much the browser is used. Ponistra then asks you to sign in again.

A sign-in at a provider must end in the browser where it started and within 10 minutes. If it is refused, Ponistra comes back to the sign-in page and below the buttons says why.

The installation's administrator sees in its journal every sign-in and every failed sign-in, with the address it came from.

## Limits

- When the email or the password is wrong, it says: {t:auth.invalid}
- After 5 failed attempts from the same network address for the same account it says {t:auth.locked}
- If an administrator requires a passkey for your account and you already have one, a password is no longer enough and the page asks for the passkey.
- When the provider's sign-in comes back refused, it says one of these:
  - {t:auth.refused.no_account} The source does not make accounts; an administrator makes yours.
  - {t:auth.refused.outside_domains} Sign in with the organisation's account.
  - {t:auth.refused.unverified_email} {t:auth.refused.no_email} This is set at the provider.
  - {t:auth.refused.inactive} Contact an administrator.
  - {t:auth.refused.visitor} A visitor comes in only by their own link.
  - {t:auth.refused.unknown_attempt} {t:auth.refused.expired_attempt}
  - {t:auth.refused.provider_refused} {t:auth.refused.provider_unreachable}
  - {t:auth.refused} The provider's answer did not pass the checks; an administrator sees why in the journal.
- When your account comes from the organisation's directory, you sign in on this page with your directory address and password if an administrator connected it so.
- Without a passkey and a password you cannot sign in by yourself. If you lost the device with your passkey, an administrator can set you a new password.

## Related

- [Passkeys](help:account/passkeys)
- [Password](help:account/password)
- [Signed-in devices](help:account/devices)
