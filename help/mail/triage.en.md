# Sorting into folders

Claude proposes for the chosen messages the folder each belongs in, and you move the proposals you accept.

## How to use it

1. Choose messages in the list, at most 50 at once (see [working with several messages](help:mail/selecting)).
2. In the menu of the choice bar or of a row choose {t:mail.triage}.
3. In the consent dialog press {t:ai.consent.once}.
4. In the dialog {t:mail.triageTitle} the proposed folder stands beside each message. Untick the messages you do not want moved.
5. Press {t:mail.triageApply}.

## How it works

Claude is given the sender, subject and opening of each chosen message and the list of your folders, and for each message chooses one folder or leaves it where it is. It may propose your folders, the archive and junk, but not the inbox, sent mail, drafts, snoozed messages or the trash. The archive and junk are made the first time something moves into them.

Nothing moves until you press {t:mail.triageApply}. The move holds in Ponistra only, as every move of mail does. When Claude leaves every message where it is, the dialog says so: {t:mail.triageNone}

The consent holds for this sorting only. Each sorting counts toward the installation's monthly AI limit, and the usage overview administrators see lists it as {t:action.mailTriage}.

## Limits

- The action is disabled while the installation's AI is off or when more than 50 messages are chosen.
- Sorting needs messages chosen one by one or on the page; choosing the whole folder ({t:explorer.selectAll}) does not offer it.
- Sent mail and drafts offer no sorting.
- In a shared mailbox sorting needs a role that allows editing.

## Related

- [Working with several messages](help:mail/selecting)
- [Blocked senders and images by domain](help:mail/senders)
