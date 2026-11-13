# Translation

Claude translates messages and PDF files in a language you do not read into the interface's language, and a reply to such a message into the message's language.

## How to use it

### The languages you read

1. Open {t:settings.title} and choose {t:translation.title}.
2. Under {t:translation.reads} add a language from the list {t:translation.add}
3. You remove a language with the {t:translation.remove} button beside its name.

### A message in another language

1. Above a message in a language you do not read stands a bar with the message's language.
2. Press {t:translation.translate}. While it runs, it says: {t:translation.translating}
3. Press {t:translation.original} to go back to the original.
4. When Ponistra cannot tell the message's language, {t:translation.translate} is in the message's menu.

### A reply in another language

1. Write the reply in your language.
2. Press {t:translation.reply}.
3. Beside your text the translation appears, which you can correct before sending.
4. Press {t:translation.edit} to go back to your own text.

### A PDF in another language

1. In the menu of the open PDF file choose {t:action.fileTranslate.ask}
2. In the dialog {t:translation.file} press {t:translation.translate}.

## How it works

Ponistra tells the language of a message or PDF itself and offers a translation only when that language is not among the languages you read. Until you choose languages, you read the interface's language. Claude translates a message paragraph by paragraph, so its layout, images and links stay. A translated message is kept, so it is not translated again the next time you open it.

At a message's first translation the dialog {t:ai.consent.heading} opens with the choice {t:ai.consent.once} or {t:translation.consent.always}. With the second choice, messages in a language you do not read are translated as soon as you open them, and replies without asking; you change that in the settings, under {t:consents.title}.

When you send a translated reply, the translation goes out, and the sent message also keeps what you wrote in your language. A PDF is translated page by page into a new document beside the file; the action's bar shows {t:action.fileTranslate}, and {t:run.missed} lists the pages that were not translated.

## Limits

- Translation is offered only while AI is turned on for the installation.
- At least one language you read must always remain.
- A PDF is translated only into the interface's language, and pressing {t:translation.translate} in the dialog is also your consent for that one sending.

## Related

- [Consents](help:ai/consents)
- [Reading a message](help:mail/reading)
- [Writing a message](help:mail/composing)
