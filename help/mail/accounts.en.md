# Mail accounts

You connect Ponistra to existing mailboxes at any provider, and each account keeps its own settings.

## How to use it

### Connecting an account

1. In Mail, or in Settings under {t:mail.accounts}, press {t:mail.connect}.
2. If the administrator has set it up, press {t:mail.oauth.google} or {t:mail.oauth.microsoft} and sign in at the provider.
3. Otherwise, under {t:mail.oauthOr} type {t:mail.address} and {t:mail.password}. Some providers ask for an {t:mail.appPassword}; the link {t:mail.appPasswordMake} leads to their page.
4. Type {t:mail.name}.
5. Press {t:mail.connect}. Meanwhile the button shows: {t:mail.checking}

### Server settings

1. If Ponistra does not find the servers itself, open {t:mail.servers}.
2. Choose {t:mail.protocol}: {t:mail.protocol.imap} or {t:mail.protocol.activesync}.
3. Type {t:mail.username}.
4. For {t:mail.imap} and {t:mail.smtp} type {t:mail.host}, {t:mail.port} and {t:mail.security}: {t:mail.security.tls}, {t:mail.security.starttls} or {t:mail.security.none}. For ActiveSync type {t:mail.activesync}.

### The account's menu

Long-press the account's name in Mail's left column or right-click it, then choose:

- {t:tree.rename}: a name of the account only you see.
- {t:mail.edit}: address, password and servers. If you leave the password empty, the present one stays.
- {t:mail.signature}: [the account's signature](help:mail/signature).
- {t:mail.color}: {t:mail.color.petrol}, {t:mail.color.green}, {t:mail.color.orange}, {t:mail.color.violet}, {t:mail.color.rose}, {t:mail.color.gold} or {t:mail.color.blue}.
- {t:mail.default}: the account a new message starts from.
- {t:mail.together}: the account's messages show in the shared folders. The same switch is the dot beside the account's name.
- {t:mail.remove}: removes the account after confirming ({t:mail.removeTitle}).

## How it works

Ponistra takes mail from the mailbox and sends through it. It changes nothing at the provider, except that sending adds a copy to the sent mail. The password is kept encrypted. With sign-in through the provider Ponistra keeps no password of the account.

You can switch an account with a password to sign-in through the provider with {t:mail.oauthSwitch.google} or {t:mail.oauthSwitch.microsoft}. When the provider stops accepting the sign-in, a red icon appears beside the account. Pressing it shows the error, and {t:mail.edit} holds the sign-in again: {t:mail.oauthAgain.google} or {t:mail.oauthAgain.microsoft}.

When the provider still gives the sign-in but the account's incoming server refuses it or does not answer, the icon stays beside the account and Ponistra keeps trying again, first after a minute, then at longer intervals up to half an hour. The account recovers by itself as soon as the server accepts it. A message that the outgoing server refuses that way is sent again once with a new sign-in.

After removing an account new mail no longer arrives, and the messages taken stay in a group of folders of their own in the left column.

Colours make accounts recognisable in the list of messages and in the form for writing.

## Limits

- Sign-in through Google and Microsoft is offered only when an administrator sets it up.
- For some addresses Microsoft takes no password, only sign-in through Microsoft, so without that sign-in such an account cannot be connected.
- Outlook.com lets apps reach mail only when IMAP is allowed in its settings (Settings → Mail → Forwarding and IMAP); in Microsoft 365 and Google Workspace an administrator can turn IMAP off for a mailbox.
- Some providers take no account password for mail, only an app password, with two-step verification turned on.
- Deleting and moving in Ponistra do not reach the provider.

## Related

- [Mail overview](help:mail/overview)
- [Signature](help:mail/signature)
