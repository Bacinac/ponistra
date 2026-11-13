# Searching by a sentence

Claude turns a sentence typed into the search into its words and filters, so you need not remember how filters are written.

## How to use it

1. In the search box or the field on the {t:search.title} page type a sentence of at least 3 words, for example "quotes from Ana last month", and press {k:Enter}.
2. The first time, the question {t:ai.consent.heading} opens. Choose {t:ai.consent.once} for this sentence, {t:search.consent.always} not to be asked again, or {t:search.consent.words} to search the sentence as typed.
3. While Claude reads the sentence, it says: {t:search.ai.translating}
4. The results page opens with the words and filters Claude read. Change and remove the filters as you do those you add yourself.

## How it works

The sentence goes to the Claude model of Anthropic in the USA only when artificial intelligence is turned on for the installation and you agreed to it. Only the sentence goes, not your documents or mail. Claude takes from it the words to look for and the kind, person, account, folder, period and attachment, and works out a period such as "last month" from today.

Text is sent to Claude only when it has at least 3 words and none of them is a filter, that is a word with a colon. Shorter text and text with a filter are searched as typed.

The answer for all searches is kept with your account. Change it in the [settings](/settings/ai), under {t:consents.title}. With {t:search.consent.words} sentences go nowhere any more and the question is not asked again.

## Limits

- If artificial intelligence is not turned on for the installation, a sentence is searched as plain words.
- If Claude cannot read the sentence, the reason shows below the box with a {t:search.ai.literal} button, which searches the words as typed.
- Claude may read a sentence wrongly. Check the filters on the results page and correct them.

## Related

- [Search results and filters](help:start/results)
- [The search box](help:start/search)
