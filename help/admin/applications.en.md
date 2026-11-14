# Signing in to applications

Your organisation's other applications can sign their users in through Ponistra, so the user needs no separate password there.

## How to use it

### A new application

1. Open {t:admin.title} and choose {t:identity.title}.
2. Press {t:identity.new}.
3. Type the {t:identity.name} and the {t:identity.redirects}.
4. Under {t:identity.who} choose {t:identity.who.everyone} or {t:identity.who.admins}, then press {t:tree.create}.
5. Copy the {t:identity.issuer}, {t:identity.clientId} and {t:identity.secret} and enter them in the application's settings.

### An existing application

1. Open the menu in the application's row.
2. Choose {t:identity.edit}, {t:identity.renew} or {t:identity.delete}.
3. Confirm a new secret in the dialog {t:identity.renewTitle} Confirm removal in the dialog {t:identity.deleteTitle}

## How it works

For these applications Ponistra is the sign-in issuer by the OpenID Connect standard. When an application sends a user to sign in, Ponistra signs them in at once if they are already signed in, with a heading naming the application and {t:identity.as} beside their name. If the sign-in fails, the user tries again with the {t:identity.continue} button.

The application gets the user's identifier and, if it asks, their email address and name. The secret is shown only once, when it is made; a new secret cancels the previous one. The list shows {t:identity.who} and {t:identity.used} for each application, and while there is none it says: {t:identity.none}

Every change to an application and every user's sign-in to it is written to the [journal](help:admin/journal), never the secret itself.

## Limits

- Only active users can sign in, and with {t:identity.who.admins} only administrators.
- The application is returned only to the addresses entered under {t:identity.redirects}.
- A removed application can no longer sign in through Ponistra.
- Making, changing and a new secret may ask you to confirm that it is you.

## Related

- [Users](help:admin/users)
