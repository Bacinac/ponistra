# Sending later

A message you wrote waits in Ponistra and leaves from your account at the moment you choose.

## How to use it

### Choosing the time

1. Write the message in the [composer](help:mail/composing).
2. Press {t:mail.later}. It asks: {t:mail.laterTitleAsk}
3. Choose {t:when.tomorrow} or {t:when.monday}, or enter {t:when.day} and {t:when.time} and press {t:mail.later}.

### The messages waiting

1. In the left column of Mail, below the inbox, open {t:mail.laterTitle}. The row is there only while a message waits; with none, the page says: {t:mail.laterNone}
2. The number by the row says how many wait, and is red when one of them was left unsent.
3. Long-press a row or right-click it for the menu: {t:mail.laterEdit}, {t:mail.laterNow}, {t:mail.laterMove} or {t:mail.discard}.

### Changing a message

1. Press the row or choose {t:mail.laterEdit}. The message opens in the composer and stops waiting, so it cannot leave while you change it.
2. When done, press {t:mail.later} or {t:mail.send} again. If you close the composer, the message stays under {t:mail.unsentTitle}.

## How it works

The server keeps the time, so the message leaves with all your devices off. It looks every fifteen seconds, so a message can leave that much after the moment chosen.

You enter the time by your device's clock. On leaving, the message takes the date of the moment it really left and ends up in your sent mail like any other. Its files and images are kept while it waits.

The message is checked when you schedule it, so one with no recipient or an invalid address cannot be scheduled.

A message written on a device without the network waits at the top of the list marked {t:mail.queuedWaiting} and leaves through the same queue as soon as the network is back ([Working offline](help:account/offline)).

## Limits

- A message that did not leave stays among those waiting, with the reason under its row, and you get a [notification](help:account/notifications) if you turned them on. It is not tried again by itself. Once the cause is gone, choose {t:mail.laterNow}.
- If the server refuses only some recipients, the others got the message, it is in your sent mail, and the notification says some did not get it.
- {t:error.mail_interrupted}
- {t:error.mail_account_gone} Open the message, choose another account and send it.
- {t:error.mail_sending} Such a message can no longer be changed or discarded.
- A reply or forward stays unsent if you deleted the original for good in the meantime.

## Related

- [Writing a message](help:mail/composing)
- [Mail overview](help:mail/overview)
- [Working offline](help:account/offline)
