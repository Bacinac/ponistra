# Sharing with someone outside

The owner shares an item with someone without an account in the installation by their email address, to read or to edit, and they open it under their own name.

## How to use it

### Sharing

1. In the item's menu or the header of the open item press {t:access.share}.
2. In the {t:outside.title} section press {t:outside.person}.
3. Type the person's {t:outside.name} and {t:outside.address}.
4. Under {t:access.role} choose {t:access.role.read} or {t:access.role.edit}.
5. Clear {t:outside.download} if the item may stay only in the browser.
6. Press {t:outside.share} or {t:tree.cancel}.

The person then appears among the others with access, marked {t:access.outside} beside their address. There the owner changes their role, turns {t:outside.download} on or off and removes their access, as for a colleague ([Sharing](help:documents/sharing)).

### Opening

1. The person gets a message with a link and opens it in a browser, with no account or password.
2. The item opens in Ponistra, and the person is signed in under their own name in that browser.

## How it works

The message leaves from your default mail account (SMTP), in the language you use Ponistra in, and stays among your sent messages. It holds the item's title, the role and the person's own link. If the message does not leave, the sharing is undone.

The person gets a visitor's account with no password: they come in only through their links and cannot sign in on the sign-in page. They see no modules, no search and no people of the installation, and pages they may not open take them back to {t:tree.shared}. There are all the items shared with them, by every owner. Access shared with everyone or with a group never reaches them.

With the role {t:access.role.edit} they edit and comment like a colleague, and their name stands in the document, the [access log](help:documents/sharing) and the presence of others. With {t:outside.download} they may download, export and print the item.

Being signed in in the browser lasts at most 30 days, and opening the same link again renews it. Removing their access ends the link at once, also in a browser where they are signed in already.

## Limits

- Only the item's owner shares, and only where the installation's policy lets them. Otherwise it says {t:error.links_not_allowed}
- The address of a user of the installation is refused: {t:error.colleague} A colleague is given access in [sharing](help:documents/sharing).
- Without a mail account that sends (ActiveSync does not) the message has nowhere to leave from: {t:error.no_account}
- There is no sharing for an item in a folder that allows no downloads, nor for a saved web link.
- A link that is no longer valid says {t:error.no_link}
- Someone outside cannot share further, make items, or read mail, contacts or the calendar. Such requests say {t:error.visitors_not_allowed}

## Related

- [Sharing](help:documents/sharing)
- [A link outside the installation](help:documents/outside)
- [Documents in mail as links](help:mail/shared-links)
- [Shared](help:documents/shared)
