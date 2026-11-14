# Data retention

Retention rules set how long documents, files, mail and chat are kept before anyone may delete them for good and when Ponistra deletes them by itself, and a legal hold stops every deletion of a person's or a folder's content while a matter is open.

## How to use it

### A retention rule

1. Open {t:admin.title} and choose {t:retention.title}.
2. Press {t:retention.newRule}.
3. Under {t:retention.what} choose {t:retention.what.documents}, {t:retention.what.files}, {t:retention.what.mail} or {t:retention.what.chat}.
4. For documents and files leave {t:retention.everywhere} on, or turn it off, press {t:retention.chooseFolder}, choose a folder and press {t:retention.pick}.
5. Enter {t:retention.keepDays}, {t:retention.removeDays} or both and press {t:tree.create}.

The rules are listed under {t:retention.rules}. In a rule's row {t:retention.editRule} changes only its periods, and {t:retention.dropRule} removes it after you confirm in the {t:retention.dropRuleTitle} dialog. While there are no rules, it says {t:retention.noRules}

### A legal hold

1. On the same page press {t:retention.newHold}.
2. Under {t:retention.holdName} enter the matter's name, for instance a case number.
3. Under {t:retention.subject} choose {t:retention.person} and then a person from the list ({t:retention.choosePerson}), or {t:retention.folder} and then a folder.
4. Press {t:retention.hold}.

The list under {t:retention.holds} shows the matter, the person or folder and the date under {t:retention.since}. When the matter ends, press {t:retention.release} in its row and confirm in the {t:retention.releaseTitle} dialog. While nothing is on hold, it says {t:retention.noHolds}

## How it works

### The retention period

A document or file changed within the period cannot be deleted for good from the trash, nor can a folder holding it. Moving it to the trash and restoring it stay allowed. A mail message younger than the period cannot be deleted for good, and a chat message younger than the period cannot be taken back; editing a message stays allowed. The period of mail counts from the message's date, that of chat from the moment it was sent.

Where several rules apply to the same content, for instance the rule for all folders and the rule of a folder above a document, the longest retention period applies.

### Deletion by a rule

Once an hour Ponistra deletes for good what is older than the deletion period: documents and files by their last change, in the trash and outside it, mail messages by their date and chat messages by the moment they were sent. For a document or file the deletion period of the nearest folder above it with a rule applies, or the rule for {t:retention.everywhere} if no folder has one. Nothing is deleted before the longest retention period that applies to it. Folders are not deleted.

A deleted mail message does not come back at the next fetch from the mail server. A chat message with a reply that stays, stays with it. A conversation the last member leaves stays until a rule removes its last message. Under {t:retention.removals} it says how much of what each pass that deleted anything deleted.

### Legal hold

While a person is on hold, nothing of theirs is deleted: the documents and folders they made or own, with everything in them, their mail, the messages they wrote and every message of the conversations and channels they are a member of. Those messages cannot be edited either, and their account cannot be erased, only deactivated. While a folder is on hold, nothing in it is deleted, at any depth. Deletion by a rule passes over everything on hold.

Where deleting is not allowed, the action is disabled. In the trash a lock marked {t:retention.kept.held} or {t:retention.kept.retained} stands beside the item, and in a chat message's menu the same reason is written under {t:chat.takeBack}.

Every rule added, changed and removed and every hold placed and released is written to the [journal](help:admin/journal) as {t:journal.setting.retention} or {t:journal.setting.legal_hold}. The page refreshes by itself when another administrator changes something.

## Limits

- Only an administrator opens the page.
- Periods are entered in days, from 1 to 36,500. The deletion period cannot be shorter than the same rule's retention period, and there is only one rule for a kind and folder.
- Folders are chosen among those the administrator sees and may add to.
- For mail Ponistra deletes only its own copy. Messages on the mail server itself and in other applications stay as they are, and a wipe ordered by an ActiveSync server is carried out for messages on hold too.
- A user whose mail is still within its retention period cannot be erased until the period ends or the rule changes.
- Deletion by a rule cannot be undone.

## Related

- [Trash](help:documents/trash)
- [Journal](help:admin/journal)
- [Users](help:admin/users)
