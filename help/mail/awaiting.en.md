# Waiting for an answer

A message you sent comes back to the top of the inbox if no one has answered by the date you choose.

## How to use it

### While writing

1. In the [composer](help:mail/composing) press the hourglass icon, {t:mail.await}.
2. The question {t:mail.awaitAsk} opens.
3. Choose {t:when.tomorrow} or {t:when.monday}, or enter a {t:when.day} and {t:when.time} and confirm.
4. Beside the buttons it says until when you wait. The cross beside that text, {t:mail.unawait}, cancels it.
5. Send the message, now or [later](help:mail/later).

### On a message already sent

1. In the Sent folder open the message.
2. On the bar above it press {t:mail.await} and choose a time.
3. While it waits, the text above the message says until when, and its row in the list carries an hourglass.
4. Press {t:mail.unawait} if you no longer need an answer.

### When a message comes back

1. The message is at the top of the inbox, unread, marked {t:mail.unanswered}, and its row shows the recipients instead of the sender.
2. To go on waiting, open it and press {t:mail.await} again.
3. Otherwise move or delete it like any other message.

## How it works

The server keeps the date, so the message comes back even when all your devices are off. On that date Ponistra checks your mail: if someone has answered in the message's thread, nothing happens and the wait ends. If not, the message comes back and you get a [notification](help:account/notifications).

An answer is a message in the thread written by someone else. Servers that rewrite message identifiers leave no thread to follow, so a message under the same subject that came later from someone you wrote to counts as an answer too.

Automatic messages are no answer: absence notices, delivery reports and mail from addresses no one reads. Nor is an emoji reaction.

## Limits

- You can wait only on a message in Sent or one that has already come back without an answer.
- A message that comes back is in the inbox instead of Sent, as every message in Ponistra is in one folder. The copy at your provider stays where it was.
- A message in Trash or Junk does not come back.
- The date must come after the message leaves: {t:error.mail_awaited_before_sending}
- An answer you deleted for good before that date is no longer seen by Ponistra.
- Without the network waiting cannot be set or ended on an open message ([Working offline](help:account/offline)).

## Related

- [Writing a message](help:mail/composing)
- [Sending later](help:mail/later)
- [Snoozing a message](help:mail/snoozing)
- [Reading a message](help:mail/reading)
- [Working offline](help:account/offline)
