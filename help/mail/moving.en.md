# Moving mail between accounts

Ponistra puts the mail one account brought into another account at its provider, for instance when an organisation moves from one mail provider to another.

## How to use it

1. Connect both accounts: the one the messages move from and the one they move into.
2. On the mail page long press or right click the account you move from.
3. Choose {t:mail.moveMailItem} The item is offered when you have at least one other account connected over IMAP.
4. In the dialog {t:mail.moveMail} choose the account under {t:mail.moveMailTo}.
5. Press {t:mail.moveMailStart}. You may close the dialog; the move goes on as the job {t:job.mailMove}, its progress shown in the bottom right corner.
6. When it ends, the dialog says how many messages moved.

## How it works

Ponistra sends each message as it came, with its read, favourite and answered marks and its original date. Messages from the inbox, sent mail and the archive go into the matching folders of the other account, which Ponistra makes where it has none. Messages from the account's own folders go into folders of the same name of the other account, made where there are none, and in Ponistra move under the other account. Your own folders in Ponistra keep their messages.

A moved message belongs to the other account from then on: it bears its colour, and a reply to it goes from it. The move runs on the server with the browser closed. If a restart of the server cuts it off, it goes on where it stopped; so does a move you start again. Nothing is deleted from the account moved from.

## Limits

- The trash, junk and drafts stay on the account moved from.
- Messages the other account already has are not sent again.
- The other account must be connected over IMAP (with a password, Google or Microsoft). An account connected over ActiveSync can only be moved from.
- A cut exactly between sending a message and noting it may leave one message twice at the other provider; in Ponistra it is still one.
- If the other server refuses the sign-in or drops the connection, the move stops with an error; start it again once the account works.
- In a shared mailbox its owner starts the move.

## Related

- [Mail accounts](help:mail/accounts)
- [Shared mailboxes](help:mail/mailboxes)
