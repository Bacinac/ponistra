# Consents

Under Consents you decide what of your work may go out to models outside the installation: sentences from the search box, what you say aloud and messages in other languages.

## How to use it

1. Open {t:settings.title} and choose {t:consents.title}.
2. Under {t:consents.search} choose {t:consents.search.ask}, {t:consents.search.always} or {t:consents.search.words}.
3. Turn {t:consents.speech} on or off.
4. Turn the automatic translation of messages in a language you do not read on or off.

## How it works

Claude can turn a sentence typed into the search box into search filters. With {t:consents.search.ask} Ponistra asks before each sending, and with {t:consents.search.words} it sends nothing and searches by the words typed.

What you say aloud is sent to OpenAI, which returns it as text. Each user gives that consent themselves, at the first recording or here.

With automatic translation on, messages in a language you do not read are sent to Claude to be translated as soon as you open them, and your replies to them without asking. The choice {t:translation.consent.always} at a message's first translation gives the same consent.

## Limits

- While AI is not turned on for the installation, the consents for Claude are disabled and it says: {t:consents.aiOff}
- While speech to text is not turned on for the installation, the consent for speech is disabled and it says: {t:speech.off}
- Consent for actions on a document is given in the document itself, not here.

## Related

- [Actions and Claude](help:ai/actions)
- [Translation](help:ai/translation)
