# Reading a message

An open message shows its sender, recipients, content and attachments, and every action on it.

## How to use it

![An open message with its actions on top](shot:mail-reader)

### Actions on a message

1. Open a message in the list. On a phone you return with {t:mail.back}.
2. On the bar above the message choose {t:mail.reply}, {t:mail.replyAll} or {t:mail.forward}.
3. With {t:mail.archive} or {t:mail.delete} the message leaves the folder and the list opens.
4. With [{t:mail.snooze}](help:mail/snoozing) the message comes back to the inbox at the time you choose.
5. In Sent, [{t:mail.await}](help:mail/awaiting) brings the message back to the top of the inbox if no one answers by the date you choose.
6. The menu of further actions holds {t:mail.markUnseen}, {t:mail.moveTo}, {t:mail.junk} and {t:mail.original}.

### Images in a message

1. When a message has outside images, the bar shows the {t:mail.images} icon.
2. Open it and choose {t:mail.showImages} for that message.
3. For all messages from that domain choose {t:mail.alwaysImages} or {t:mail.quietImages}.
4. You change the decision in the menu of further actions with {t:mail.askImages}.

### Attachments

1. Attachments are listed above the message, as {t:mail.files}.
2. Press an attachment's name or {t:mail.download} to download it.
3. Press {t:mail.toDocuments} to make the attachment a file among your documents.

### A meeting invitation

1. A message with an invitation shows a box with the meeting's time and place: {t:mail.invitation.request}, {t:mail.invitation.reply}, {t:mail.invitation.counter} or {t:mail.invitation.cancel}.
2. Press {t:mail.invitation.open} to see the meeting in the calendar.

## How it works

A message becomes read as soon as you open it. If you then mark it unread, it stays so even while you are looking at it. The mark applies only in Ponistra.

Outside images do not load until you allow it, as loading them can tell the sender that you opened the message. When you allow them, Ponistra's server loads them rather than your browser, so the sender does not see your address. Decisions by domain are held in one place, in the [sender settings](help:mail/senders).

{t:mail.original} downloads the message as it arrived, as an `.eml` file. {t:mail.toDocuments} saves a copy, so later changes do not affect the message.

If an invitation has been replaced by a newer one, the box shows: {t:mail.invitation.outdated} If the meeting is not in your calendars, it shows: {t:mail.invitation.notHeld} Above the content also stands a draft reply waiting on the message. A message you sent to colleagues shows [who opened it](help:mail/opened).

Moving out of {t:mail.role.junk} with {t:mail.notJunk} returns the message to the inbox and removes the block that sent it there.

## Limits

- {t:mail.delete} moves the message to the trash. From the trash, {t:mail.deleteForGood} after confirming ({t:mail.deleteTitle}) deletes it from Ponistra, which no longer takes it. The message stays at the provider.
- A message within a retention period an administrator set, or on legal hold, cannot be deleted for good.
- Images do not load in the message view when the domain is under {t:mail.imagesQuiet}.
- A message without a subject shows as {t:mail.noSubject}.
- On a device marked to work offline, recent messages and their attachments can be read without the network; while it is gone, of the actions on a message only replying and forwarding work ([Working offline](help:account/offline)).

## Related

- [Writing a message](help:mail/composing)
- [Blocked senders and images by domain](help:mail/senders)
- [Draft replies](help:mail/drafts)
- [Encrypted and signed mail](help:mail/encrypted)
- [Working offline](help:account/offline)
