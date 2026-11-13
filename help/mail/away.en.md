# Away

While you are away, Ponistra answers mail from your account by itself, and colleagues see until when you are gone.

## How to use it

### Turning it on

1. Open Settings and choose {t:away.title}.
2. Enter the {t:away.first} and the {t:away.last}.
3. Enter the {t:away.textHr}, the {t:away.textEn} or both.
4. Press {t:away.save}. The period is written above the form.

### Changing and turning off

1. Change the dates or the text and press {t:away.save} again.
2. Press {t:away.off} if you came back early.

### What colleagues see

1. In the event form, for those invited who are away at the time chosen, {t:away.then} and the day they are back.
2. In a direct conversation and a small group, {t:away.then} and the day they are back, above the messages. Channels do not show it.

## How it works

The server keeps the period, so answers leave even when all your devices are off. It begins at midnight of the first day and ends at the midnight after the last, by the clock of the device on which you entered it.

Each sender gets at most one answer in the period. Changing the dates begins the period anew; changing only the text does not. If you entered both texts, the answer holds both, Croatian first.

The answer leaves from the account the message came to, within fifteen seconds of Ponistra taking it, and stays in your Sent mail. Only messages that came to the inbox are answered. An away setting at your mail provider stays as it is, so take care that both do not answer.

The answer follows RFC 3834: it is marked as automatic, its subject begins with "Auto:", it goes to the message's return path and is tied to it.

Colleagues see only that you are away and until when, never the text of the answer.

## Limits

- Automatic messages, mail from addresses such as `noreply` and `mailer-daemon`, mailing lists and bulk mail are not answered.
- Nor is a message where your address is not among the recipients in To and Cc.
- If an answer cannot leave, it is not tried again. This page says {t:away.failed} with the reason, and you get a [notification](help:account/notifications) once.
- {t:error.mail_away_empty}
- The last day cannot come before the first, and a period that has already ended cannot be saved.

## Related

- [Mail accounts](help:mail/accounts)
- [Waiting for an answer](help:mail/awaiting)
- [Notifications](help:account/notifications)
