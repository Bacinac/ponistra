# Working with several messages

You can mark, move, block or delete chosen messages all at once.

## How to use it

### Choosing

1. Long-press a message in the list. On a computer you can also stand on its row and press {k:Space}.
2. After that, a tap or click on a message adds it to the choice or takes it out. A double click still opens the message.
3. Hold {k:Shift} for a range from the message chosen before.
4. Press {k:Mod-a} or the tick on the bar of the choice for all messages loaded.
5. In the bar's menu choose {t:explorer.selectAll} for the whole folder, {t:mail.selectSeen} or {t:mail.selectUnseen} for all such messages in the folder, and {t:explorer.invert} to reverse the choice.
6. Press {k:Escape} or {t:explorer.clear} to give up the choice.

### Actions

1. On the bar of the choice choose {t:mail.markSeen}, {t:mail.markUnseen}, {t:favourites.add} or {t:favourites.remove}. A right click on a message offers the same.
2. With {t:mail.moveTo} choose a folder.
3. With {t:mail.archive} or {t:mail.junk} the messages go to that folder. In junk mail the action is {t:mail.notJunk}.
4. {t:mail.blockSenders} blocks the senders of the chosen messages.
5. {t:mail.delete} or {k:Delete} moves the messages to the trash.
6. [{t:mail.snooze}](help:mail/snoozing) takes them out of the folder until the time you choose, and in the folder {t:mail.role.snoozed}, {t:mail.unsnooze} brings them back at once.

## How it works

Choosing the whole folder from the menu includes messages the list has not loaded yet and, when you are viewing one account, only its messages. The bar shows how many messages are chosen. If an action moves the open message, the list opens.

Blocking from the choice makes one rule for each sender's address and moves their mail to junk at once. Rules are edited in the [sender settings](help:mail/senders).

## Limits

- {t:mail.blockSenders} is not offered in sent mail and drafts, nor when the whole folder, or all read or unread messages, are chosen; choose them one by one instead.
- In the trash, {t:mail.deleteForGood} asks to confirm ({t:mail.deleteChosenTitle}) and cannot be undone. The messages stay at the provider, but Ponistra no longer takes them.
- A message within a retention period an administrator set, or on legal hold, cannot be deleted for good.
- Without the network the actions on chosen messages are disabled ([Working offline](help:account/offline)).

## Related

- [Mail overview](help:mail/overview)
- [Blocked senders and images by domain](help:mail/senders)
- [Working offline](help:account/offline)
