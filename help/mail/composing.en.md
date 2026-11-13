# Writing a message

You write a new message, a reply or a forward in the same form, which keeps what is unfinished by itself.

## How to use it

![The form for writing a message](shot:mail-compose)

### A new message

1. In Mail press {t:mail.compose}.
2. Under {t:mail.sender} check the account you are sending from.
3. Under {t:mail.to} type a name or address and choose a suggestion. You remove a recipient with {t:mail.removeRecipient}.
4. For further recipients press {t:mail.copies} and type them under {t:mail.cc} or {t:mail.bcc}.
5. Type the {t:mail.subject} and the {t:mail.text}.
6. Press {t:mail.send}. Meanwhile the button shows: {t:mail.sending}
7. For the message to leave at a set time, press {t:mail.later} instead ([Sending later](help:mail/later)).
8. For Ponistra to remind you if no one answers, press the hourglass icon before sending ([Waiting for an answer](help:mail/awaiting)).

### Formatting

1. The {t:mail.formatting} bar above the text offers {t:mail.font}, {t:mail.size}, {t:mail.spacing}, links and images.
2. You can place an image in the text from the bar.

### Attachments

1. Press {t:mail.attach}, then {t:chat.fromComputer} and choose the files.
2. A document or file from Ponistra goes as a link with {t:mail.attach} and {t:chat.fromDocuments} as [Documents in mail as links](help:mail/shared-links) describes.
3. Paper photographed with a phone is attached as a PDF with {t:mail.scan}, as [Scanning](help:pdf/scan) describes.
4. You remove an attachment with {t:mail.removeFile}.

### Replying and forwarding

1. In an open message press {t:mail.reply}, {t:mail.replyAll} or {t:mail.forward}.
2. The original message is hidden below your text. It shows with {t:mail.showQuoted} or {t:mail.showForwarded}.

### An unfinished message

1. Close the form. The message stays saved.
2. Open {t:mail.role.drafts}. At the top of the folder is {t:mail.unsentTitle}.
3. Press it and go on writing, or in the form press {t:mail.discard} and confirm ({t:mail.discardTitle}).

## How it works

What you write saves by itself after a short pause, and the form then shows {t:mail.unsentKept}. An unfinished message stays in Ponistra and is available on each of your devices, but does not enter the provider's drafts folder.

A new message starts from the account you marked as default. As soon as you type the first recipient, the account changes by itself to the one you last wrote to them from or they last wrote to, until you choose another yourself. A reply starts from the account the message reached. Changing the account also changes the signature in the text.

Recipient suggestions come from your mail, contacts, colleagues in the installation and the server's directory. If the directory does not answer, suggestions come only from mail, as the field also says. If the directory has only an internal name for a recipient and no address, the form says so and asks you to type the address. Quoted text stands below your text and signature.

The message is sent through the account's server. A link in an application or another page (`mailto:`) opens this form with the fields filled in.

When the vault holds a mail key, {t:mail.sealing.sign} and {t:mail.sealing.encrypt} stand beside {t:mail.send}. A reply to an encrypted message is encrypted by itself until you turn it off. More in [Encrypted mail](help:mail/encrypted).

Without the network, on a device marked to work offline, what you write is saved on the device and the form shows {t:mail.keptOnDevice}. A sent message waits for the network under {t:mail.laterTitle} ([Working offline](help:account/offline)).

## Limits

- {t:mail.imageUnsupported}
- {t:mail.linkInvalid}
- If the server refuses some recipients, {t:mail.sentRefused} shows with their addresses. The others have received the message; send it to those refused again after correcting them.
- {t:mail.sentUnkept} means the message left, but your copy is not in the sent folder.
- A discarded message cannot be brought back.

## Related

- [Documents in mail as links](help:mail/shared-links)
- [Sending later](help:mail/later)
- [Waiting for an answer](help:mail/awaiting)
- [Signature](help:mail/signature)
- [Mail accounts](help:mail/accounts)
- [Draft replies](help:mail/drafts)
- [Encrypted and signed mail](help:mail/encrypted)
- [Working offline](help:account/offline)
