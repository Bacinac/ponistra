# Working offline

A device marked for working offline keeps the folder tree, documents and recent mail, so you open, edit and write them without the network, and the changes join everyone else's and the messages leave once the network is back.

## How to use it

### Turning it on for a device

1. On the device you want to use without the network, open Settings, then {t:devices.mine}.
2. Under {t:offline.title} press {t:offline.enable}.
3. Wait until {t:offline.keeping} turns into {t:offline.kept} with the time of saving.

While it is off, it reads: {t:offline.off}

### Keeping a particular document

1. In a folder's list, open the document's menu with the right mouse button or a long press.
2. Choose {t:offline.mark}.
3. When the document no longer needs to be on the device, choose {t:offline.unmark} in the same menu.

### Working without the network

1. Open Ponistra on the marked device as usual, without the network as well.
2. Open a folder or a document and write.
3. When the network is back you need to do nothing: the changes are sent by themselves.

### Mail without the network

1. Open Mail on the marked device and read recent messages with their attachments.
2. Write, reply and forward as usual, then press {t:mail.send}. The message waits under {t:mail.laterTitle} marked {t:mail.queuedWaiting}; a message closed unfinished waits marked {t:mail.queuedUnsent}. While you write, what is written is saved on the device, and the composer reads {t:mail.keptOnDevice}.
3. When the network is back, the messages leave by themselves and the unfinished ones are saved to drafts.
4. To keep a message from leaving, open its menu under {t:mail.laterTitle} with the right mouse button or a long press and choose {t:mail.discard}.

### Turning it off

1. In Settings open {t:devices.mine}.
2. Press {t:offline.disable}. Everything the device saved is deleted from it.

## How it works

The device saves in the browser: the tree of every folder you have access to, the documents you opened recently, the documents marked with {t:offline.mark} and the application itself, so it opens without the network. Saving is repeated each time Ponistra opens, when the network comes back and a minute after something changes in the folders. If saving fails, {t:offline.failed} shows with the reason, and the device keeps what it saved before.

Changes made without the network are kept on the device and, once the network is back, merge with other people's changes as in simultaneous editing: nothing is overwritten.

Of the mail the device saves your accounts, the first page of each folder, the messages of the last month (the 200 latest at most) with their attachments up to 25 MB and the replies begun to them, and the messages waiting to be sent. A message the device saves this way does not count as opened. Saving the mail is also repeated a minute after mail arrives or changes.

A message written without the network leaves through the same queue as [messages sent later](help:mail/later), and leaves only once, even when the connection breaks while it is handed over. If the server refuses it, the reason shows under {t:mail.laterTitle}, and in the message's menu you can choose {t:mail.queuedAgain} or {t:mail.discard}.

Without the network everything the server does is disabled: search (the search field reads {t:offline.needed}), actions and AI on a document, a new document, a new note, moving, renaming and deleting in folders, and in mail moving, deleting, flags, snoozing, waiting for an answer, reactions, rules, account settings, attaching files from the computer, scanning and images in a message's text. It is enabled again by itself as soon as the connection to the server is back.

In the list of signed-in devices a device that keeps documents carries the mark {t:offline.marked}, so you and the administrator see where copies exist.

## Limits

A folder with no download is never saved on the device, nor anything in it, and {t:offline.mark} is disabled there.

Tables are calculated by the server, so only text documents and presentations work without the network. Files in folders, such as PDFs and images, are not saved.

Older messages, attachments larger than 25 MB and shared mailboxes are not saved from mail. Messages written without the network are deleted from the device with everything else if its sign-in runs out before they leave.

Signing out deletes everything the device saved. If you sign the device out from the list of signed-in devices or its sign-in runs out, everything is deleted as soon as it next connects to the server.

The application is saved only from a released version; until that succeeds, Ponistra cannot be reloaded without the network.

## Related

- [Signed-in devices](help:account/devices)
- [Sharing](help:documents/sharing)
- [Sending later](help:mail/later)
