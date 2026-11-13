# Mail sign-in through Google and Microsoft

For mail accounts at Google and Microsoft to sign in through the provider instead of with a password, an administrator enters here the installation's registration with each of them.

## How to use it

1. In {t:settings.title}, under {t:settings.installation}, choose {t:providers.title}.
2. Under {t:providers.signIn}, for {t:providers.google} or {t:providers.microsoft}, press {t:providers.copy} beside the {t:providers.redirect}.
3. At the provider make an app registration with that redirect address, as the note under the provider's name describes.
4. Type the {t:providers.clientId} and {t:providers.secret}, and for Microsoft also {t:providers.expires}.
5. Press {t:providers.save}.
6. You remove a registration with the {t:providers.remove} button and confirmation in the dialog {t:providers.removeTitle}

## How it works

The secret is kept locked and no longer shown; it says only {t:providers.secretKept} and its last four characters. A new secret typed into the same field replaces the previous one, and an empty field leaves it as it is. Beside the registration also stands when it was {t:providers.changed}.

Microsoft's secret has an end date. Thirty days before it ends a warning appears here to make a new secret, as otherwise the accounts stop signing in. When a removed registration is entered again, the accounts signing in through that provider resume fetching and sending mail.

The same page also turns on {t:mail.openedSetting}.

Entering and removing a client are written to the [journal](help:admin/journal), never the secret itself.

## Limits

- Until the registration is entered, accounts at that provider cannot sign in through it.
- If the installation's secret changes, the provider's kept secret can no longer be read and must be entered again.

## Related

- [Mail accounts](help:mail/accounts)
- [Read within the organisation](help:mail/opened)
