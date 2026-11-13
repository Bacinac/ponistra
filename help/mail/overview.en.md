# Mail overview

Mail gathers the messages of all your accounts in one place, in shared folders and in the folders of each account.

## How to use it

![The message list beside the folders](shot:mail-list)

### Moving between folders

1. Open {t:rail.mail} on the bar of modules, or type its name into the search box.
2. In the left column choose a shared folder: {t:mail.role.inbox}, {t:mail.role.sent}, {t:mail.role.drafts}, {t:mail.role.archive}, {t:mail.role.junk} or {t:mail.role.trash}.
3. Starred messages are under {t:favourites.title}, just below the inbox, and below them, while a message waits, [{t:mail.laterTitle}](help:mail/later). Messages you have [snoozed](help:mail/snoozing) wait in the folder {t:mail.role.snoozed}.
4. An account's own folders are below that account's name.
5. Choose a message in the list. While none is open, its place says: {t:mail.choose}
6. At the foot of the list press {t:mail.more} for older messages.

### One account's mail

1. Press the account's name in the left column. The shared folder then shows only its messages.
2. To go back, press {t:mail.allAccounts} or the account's name again.

### Order of the list

1. Open the {t:mail.sort} menu above the list.
2. Choose {t:mail.sortDate}, {t:mail.sortSender} (in sent mail and drafts, {t:mail.sortRecipient}) or {t:mail.sortPriority}.
3. Choose the direction: {t:mail.newestFirst} or {t:mail.oldestFirst}, {t:mail.aToZ} or {t:mail.zToA}, {t:mail.highFirst} or {t:mail.lowFirst}.

### Marking a whole folder as read

1. Long-press the folder or right-click it.
2. Choose {t:mail.allSeen}.

## How it works

Ponistra takes mail from the provider in one direction and keeps it. Each message is kept once, so one that reached two accounts shows once, with the colours of both. Marking, moving and deleting apply in Ponistra and do not change what the provider holds. The only thing sent to the provider is a message you send, with a copy in its sent folder.

The first download takes new mail first and then older mail, newest to oldest, so the list is usable before all of it has arrived. Meanwhile the account shows: {t:mail.syncing} While there is no folder yet, the page shows: {t:mail.firstSync} With no account connected the page says: {t:mail.none} The button to connect one is below it.

An unread message has its sender and subject emphasised. A paperclip marks {t:mail.attachments}, and a star that the message is a favourite. With several accounts, the bar beside a message has the colour of the account it reached. A message without a subject shows as {t:mail.noSubject}. Priority shows as {t:mail.highPriority} or {t:mail.lowPriority}, read from the message itself. An empty folder shows: {t:mail.empty} An empty Favourites says: {t:favourites.noMail}

The chosen order is remembered in that browser. On another device the list keeps the order of that browser.

## Limits

- What you do in Ponistra does not show in the provider's app or website, and the reverse: a message you move at the provider stays where it is in Ponistra.
- {t:mail.allSeen} applies only in Ponistra.
- The shared folders do not show messages of an account with {t:mail.together} turned off; those are in that account's folders.
- On a device marked to work offline, the first page of every folder can be read without the network ([Working offline](help:account/offline)).

## Related

- [Reading a message](help:mail/reading)
- [Working with several messages](help:mail/selecting)
- [Mail accounts](help:mail/accounts)
- [Working offline](help:account/offline)
