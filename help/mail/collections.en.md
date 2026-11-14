# Collections

A collection gathers the messages you choose, such as bills, files their attachments in a folder by month and sends them once a month with a table of the amounts.

## How to use it

### A new collection

1. Open Settings and choose {t:collections.title}.
2. Press {t:collections.new}.
3. Enter the {t:collections.name}. The collection's folder and the message's subject are named after it.
4. Under {t:collections.takes}, set which messages the collection takes:
   - {t:collections.accounts}: the mail accounts it takes from, if you have several;
   - {t:collections.senders}: addresses or domains separated by commas;
   - {t:collections.words}: words separated by commas;
   - {t:collections.attached};
   - {t:collections.recognise}, if you want the collection to keep bills only;
   - {t:collections.since}: the day from which the collection also takes mail received earlier.
5. Under {t:collections.goes}, enter the {t:collections.to} and, if you have several accounts, the account it {t:collections.from}. With none chosen, the message goes from the {t:collections.fromDefault}.
6. Choose the {t:collections.day} and the {t:collections.hour} at which the collection sends the month before, and under {t:collections.currency} the code of the currency the table also gives each amount in, such as EUR. Without a code, amounts are not converted.
7. Under {t:collections.sends}, choose {t:collections.draft} or {t:collections.send}.
8. If you wish, enter the {t:collections.text}.
9. Press {t:tree.save}. If you turned recognition on, Ponistra first asks for your consent: {t:collections.consent} You give it with {t:collections.consentGive}, and it holds until you turn recognition off.

### The months

Below each collection stand its last 13 months. Beside a month stands how many messages were {t:collections.kept}, how many are {t:collections.waiting} to be read, how many were {t:collections.passed} and how many were {t:collections.missed}, and when the month was sent or will be.

1. Press the folder icon beside a month to open its files, or {t:collections.openFolder} beside the collection's name for the whole collection.
2. Press {t:collections.sendNow} for a month that is {t:collections.notSent}.
3. Press {t:collections.sendAgain} and confirm to send a month already sent once more, with all that is now in its folder. While the message is being made, the month shows {t:collections.sending}.
4. Press a month to see its items: the date, the supplier, the amount and the amount in the collection's currency. A bill without a file shows {t:collections.unfiled}, and pressing it opens the message.
5. If your bank charged a different amount, enter it in the {t:collections.converted} field beside the item and press Enter. The amount then shows {t:collections.byHand}. Clear it to go back to the amount by the rate.

### Adding a file by hand

1. Press the folder icon beside the month.
2. Upload the bill's PDF into that folder, for instance a bill downloaded from the web.
3. Within a minute the collection takes it and joins it to the item it belongs to, or makes a new item of it.

### Adding a message by hand

1. Open the message in your own mailbox.
2. In the message's menu, choose {t:collections.add}
3. Choose the {t:collections.into} and press {t:collections.addConfirm}. If you have no collection yet, the dialog says {t:collections.none} and leads to {t:collections.new}.

### Changing, turning off and deleting

1. Press {t:collections.edit} beside the collection, change what you need and press {t:tree.save}, or {t:tree.cancel} to leave it as it was.
2. Turn off {t:collections.active} for the collection to neither take nor send for a while. Beside its name then stands {t:collections.paused}.
3. Press {t:collections.remove} and confirm. {t:collections.removeKeeps}

## How it works

The collection works on the server, so it gathers and sends even when all your devices are off. It looks at new mail every minute, and when you save it or change what it takes, it at once looks through the mail from the day in {t:collections.since} as well.

When the collection keeps a bill without a file, it sends a notification to the devices on which you allowed notifications. Pressing it opens the message, which usually says where the bill can be downloaded.

The collection reads a file you put in a month's folder as a bill. If there is a kept item of the same amount and currency dated within 3 days of it, the file joins that item, an item without a file first. This way a bill and its receipt join the same item. Otherwise the file becomes an item of its own. Without recognition, the new item carries the file's name and no amount.

The amount in the collection's currency is worked out by the European Central Bank's reference rate published on the last day before the bill's date. This is the rate the Croatian National Bank applies on that day. The collection never changes an amount you entered by hand. When you change the collection's currency, the amounts by the rate are worked out again.

A message must meet every condition you entered. Within one condition, one is enough: any of the senders and any of the words in the subject. A domain takes its subdomains too. Sent mail, drafts, trash and junk are never taken.

Each message belongs to the month it came in, by the installation's time. The collection's folder stands at the top of your documents, and in it a folder for each month named by its year and month. A message's attachments go into the month's folder with the date before their name, and the same file from several messages only once. A folder that was deleted is made again.

Without recognition, the collection keeps every message it takes: as the supplier it writes the sender's name or domain, as the date the day it came. With recognition, an AI model reads the message's text and the text of its attachments, decides whether it is a bill and reads the supplier, date, amount and currency. A message that is not a bill is marked {t:collections.passed} and its attachments do not go into the folder. The collection waits up to 30 minutes for Ponistra to read the text of a PDF attachment. Each reading counts in the AI spending. A message you add by hand is always kept; the model only reads its details.

A month goes on the chosen day and hour of the following month, once every message waiting has been read, and 6 hours later at the latest. The message's subject holds the collection's name, the month and the year. Its body holds your text, a table of supplier, date, amount, currency, amount in the collection's currency and files, a total for each currency, the total in the collection's currency and the account's signature. The attachments are all the files in the month's folder at that moment, those you added yourself among them, and the same table as a workbook. The table also stays as a document in the month's folder, and sending again refreshes it.

With {t:collections.draft}, the message waits among your drafts for you to look it over and send it. With {t:collections.send}, it leaves by itself and stays in your sent mail.

Months whose sending day passed before you made the collection are not sent by themselves. They show {t:collections.notSent} until you send them with the button. A month without a single message or file is not sent.

The page refreshes by itself when the collection takes or sends something, on each of your devices.

## Limits

- A collection takes only your own mail. {t:collections.add} is not offered in a shared mailbox.
- The sending day can be from the 1st to the 28th of the month.
- {t:collections.recognise} needs AI turned on at the installation and your consent. If the model cannot be reached or the monthly amount is spent, the collection shows why, and the messages wait to be read once the model can be reached again. Examples of the reasons:
  - {t:error.ai_off}
  - {t:error.limit_reached}
- A message the model cannot read, for instance because it is too long, stays {t:collections.missed} and does not enter the table. Add it by hand if it is a bill.
- {t:error.collecting_no_recipients}
- {t:error.collecting_invalid_senders}
- {t:error.collecting_invalid_since}
- {t:error.collecting_invalid_currency}
- {t:error.collecting_unrated}
- {t:error.mail_account_gone} The month shows this message. Connect the account or choose another, then press {t:collections.sendNow}.

## Related

- [Blocked senders and images by domain](help:mail/senders)
- [Writing a message](help:mail/composing)
- [Mail accounts](help:mail/accounts)
- [What an agent can do](help:agents/tools)
