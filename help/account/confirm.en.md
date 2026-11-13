# Confirming it is you

Before a sensitive action Ponistra asks you to show again that it is you, with a passkey or a password.

## How to use it

1. Start a sensitive action, such as changing your password. The dialog {t:confirm.title} opens.
2. Press {t:confirm.passkey} and confirm on the device.
3. Or type {t:auth.password} and press {t:confirm.submit}.
4. Or press the button with the name of the organisation's sign-in provider. Its window opens; once you sign in there, the window closes by itself.
5. After the confirmation the action goes on by itself.

## How it works

A confirmation holds for 10 minutes in that browser, so it is not asked again within that time. For the terminal, opening the workspace, push and restart on the [Projects](help:agents/projects) page it holds for 8 hours. Signing in counts as a confirmation.

A confirmation is asked before changing the password, adding and removing a passkey, making an app password and connecting a phone, allowing access to an outside agent or another application, making and ending a link for people outside the installation, changing, deleting and exporting the vault, and adding and removing the vault's unlocking by passkey. An administrator is also asked before actions on users and on the installation's settings.

The dialog offers a passkey when the account has one and the browser supports it, the password when you may sign in with a password or with the organisation's directory password, and the sign-in provider when your account is connected to it. The provider then always asks you to sign in again, even when you are already signed in there.

## Limits

- When you close the dialog without confirming, the action is not carried out and it says it was not confirmed.
- If signing in with a passkey is required of you and you have one, the password is not offered.
- {t:confirm.none} It shows when the account may not sign in with a password and has no passkey, or the browser does not support it. Confirm then from the device that holds the passkey.
- After 5 wrong passwords it says {t:auth.locked}
- {t:confirm.blocked} Allow pop-up windows for the installation's address and try again.
- {t:auth.refused.someone_else} Sign out at the provider and sign in with your own account.

## Related

- [Passkeys](help:account/passkeys)
- [Password](help:account/password)
