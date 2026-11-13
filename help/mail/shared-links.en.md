# Documents in mail as links

A message carries a document or file from Ponistra as a link instead of an attachment, and each recipient opens it under their own address, as it is when they open it.

## How to use it

### Adding to a message

1. In the message form press {t:mail.attach}, then {t:chat.fromDocuments}
2. Choose a document or file. The list offers only what you own.
3. The item appears under the message's {t:mail.shared}. Beside it choose {t:access.role.read} or {t:access.role.edit}.
4. Clear the {t:outside.download} box if the item may stay only in the recipient's browser.
5. You remove the item with {t:mail.removeFile}.
6. Send the message as usual.

### A message too large

1. If the outgoing server refuses the message as too large, it says {t:error.mail_too_large}
2. Press {t:mail.filesAsLinks}. The attached files are saved in your Documents and move among the links.
3. Send the message again.

### Opening by a recipient outside

1. The recipient opens the link from the message in a browser.
2. They type the {t:outside.address} the message came to and press {t:outside.sendCode}.
3. The page says that a code waits at that address, if the link was sent there. With {t:outside.otherAddress} they type another.
4. They type the {t:outside.code} from the message and press {t:outside.open}.

## How it works

The links are made only when the message leaves, and stand at the end of your text with each item's title. If the message does not leave, everything it gave is undone. A message [sent later](help:mail/later) shares the items only at the moment it leaves, and checks them already when you schedule it.

Recipients who are users of the installation (in any of the recipient fields) get the item directly, with the chosen role, as if you had shared it with them; a stronger role they have already stays. They open the link signed in, under their own name.

For recipients outside each item gets one link, of the kind {t:outside.kind.people}, which lets in only their addresses. The code has 6 digits, leaves from your mail account (SMTP) and is valid for 15 minutes, and a new one reaches the same address at most once a minute. The page answers the same for every address, so it tells nobody whom the message was sent to. Whoever types the right code stays signed in in that browser under their address for at most 30 days and sees the item as [someone outside](help:documents/outside-people), with the role and download you chose.

A mail provider usually keeps every message sent through its server, so the messages with codes may also stand in your sent mail folder.

The link shows in the item's [sharing](help:documents/sharing), beside the recipients' addresses. There you end it, and with it the access of every recipient outside. The access log records each opening under the recipient's address.

## Limits

- A message carries at most 20 items as links; otherwise it says {t:error.invalid_shared}
- You may make a link outside the installation only where the installation's policy lets you: {t:error.links_not_allowed} A message to colleagues alone goes even then.
- An item in a folder that allows no downloads, a folder and a saved web link are not offered.
- A wrong or expired code says {t:error.wrong_code} After 5 wrong tries: {t:error.too_many_code_tries}
- A user of the installation without rights to the item gets {t:error.signed_in_inside}
- Without a mail account of yours that sends (ActiveSync does not) no codes leave.

## Related

- [Writing a message](help:mail/composing)
- [Sharing with someone outside](help:documents/outside-people)
- [A link outside the installation](help:documents/outside)
- [Sharing](help:documents/sharing)
