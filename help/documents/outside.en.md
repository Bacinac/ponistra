# A link outside the installation

The owner of a document, file, board or folder makes a link with which someone without an account in the installation reads it, with an end date and a password if they like.

## How to use it

### Making a link

1. In the item's menu or the header of the open item press {t:access.share}.
2. In the {t:outside.title} section press {t:outside.make}.
3. For a folder leave {t:outside.kind} at {t:outside.kind.open}. The other kind, {t:outside.kind.upload}, is described in [Files asked for](help:documents/asked-files).
4. If you like, choose a date under {t:outside.until} and type a {t:outside.password}.
5. Clear {t:outside.download} if the item may stay only in the browser.
6. Press {t:outside.make} or {t:tree.cancel}.
7. Beside the link press {t:outside.copy} and send it to the person it is meant for.

Beside each link stand its kind, until when it is valid or {t:outside.always}, and {t:outside.withPassword} and {t:outside.noDownload} where they hold. A link of the kind {t:outside.kind.people} is made when a document is mailed as a link, and the recipients' addresses stand beside it ([Documents as links](help:mail/shared-links)). {t:outside.end} ends any of them at once.

### Opening a link

1. The person opens the link in a browser, without signing in, and the item opens in Ponistra.
2. If the link asks for a password, it says {t:outside.asked} The person types the password and presses {t:outside.open}.

## How it works

Whoever opens the link stays signed in in that browser as the link's visitor, for at most 30 days. They see only that item, and for a folder everything in it, as it is now, and can only read and comment on it. They see nothing else of Ponistra: no modules, no search, no people of the installation, and pages they may not open take them back to {t:tree.shared}. With {t:outside.download} they may also download, export and print the item; without it they read it only in the browser.

Everyone who opens the same link is the same visitor, so the [access log](help:documents/sharing) records each opening as {t:log.openedThroughLink} and the person as {t:log.outsider}. Making the link is recorded as {t:log.linkMade} and ending it as {t:log.linkEnded}.

A user of the installation who may read the item already and opens the link while signed in opens the item under their own name.

A link stops working at the end of the chosen day, when its owner ends it, when the item goes to the trash or is moved into a folder that allows no downloads, and when an administrator decides that nobody may share outside the installation. Ending it also signs out everyone who came in by it.

## Limits

- Only the item's owner makes a link, and only where the installation's policy lets them. Otherwise it says {t:error.links_not_allowed}
- A link whose date has already passed is not made: {t:error.invalid_link_date}
- There are no links for an item in a folder that allows no downloads, nor for a saved web link.
- After 10 wrong passwords the link takes no new tries for 15 minutes: {t:error.too_many_link_tries}
- A link that is no longer valid says {t:error.no_link}
- A user of the installation without rights to the item gets {t:error.signed_in_inside} The link is meant for people outside; the owner gives them access in [sharing](help:documents/sharing).

## Related

- [Sharing](help:documents/sharing)
- [Sharing with someone outside](help:documents/outside-people)
- [Files asked for](help:documents/asked-files)
