# AI in the installation

An administrator turns on Claude and speech to text for the whole installation, enters the keys and follows the spending.

## How to use it

### Claude

1. In {t:settings.title}, under {t:settings.installation}, choose {t:ai.title}.
2. Type the {t:ai.key} and tick {t:ai.enabled}.
3. Press {t:ai.save}.

### Speech to text

1. In the {t:speech.heading} section type the {t:speech.key}.
2. Tick {t:speech.enabled} and press {t:ai.save}.

### Monthly limit

1. Type an amount into {t:ai.monthly} and press {t:ai.save}.
2. To work without a limit, leave the field empty ({t:ai.monthlyNone}) and save.

### Spending and free instructions

1. Under {t:ai.usage.heading} review the {t:ai.usage.month}, {t:ai.usage.action}, {t:ai.usage.runs}, {t:ai.usage.input}, {t:ai.usage.output} and {t:ai.usage.cost}.
2. Under {t:ai.requests.heading} review the {t:ai.requests.request}, {t:ai.requests.times} and {t:ai.requests.last}.

## How it works

Actions with Claude send text to the model Claude by Anthropic in the USA, with this installation's API key. While AI is off, those actions are visible but disabled. The key is checked when saved, kept locked and no longer shown; it says only {t:ai.keyKept} and the last four characters. A new key typed into the same field replaces the previous one. Beside the setting also stands {t:ai.changed}.

Speech to text sends what is said to a model by OpenAI, and while Claude is on, Claude turns the text it returns into an event, a task or a note. Each user gives their own consent before the first recording.

The limit applies equally to every user and is counted by calendar month, in the installation's time. It is checked each time before the model is called: an action already under way finishes, and a user who has reached the limit gets the message {t:error.limit_reached} until the next month begins. A batch job over a folder stops at the first item after the limit is reached. A changed limit applies from the next call to the model.

Spending shows tokens and cost in US dollars by month and action, for the last twelve months. Besides actions in documents, the list also shows {t:action.documentTidy}, {t:action.searchTranslate}, {t:action.mailTranslate}, {t:action.mailTranslateReply}, {t:action.fileTranslate}, {t:action.speechUnderstand} and {t:action.vaultSort}. Model runs without a price count as {t:ai.usage.unpriced}. Free instructions from the {t:action.textAsk.ask} menu are grouped by their text, without user or document.

Every change is written to the [journal](help:admin/journal), never the key itself.

## Limits

- Claude cannot be turned on without a key that works.
- There is one limit for all users; a single user's spending is not shown.
- If the installation's secret changes, the kept key can no longer be opened and must be entered again.
- While the models have run no action, it says: {t:ai.usage.none}
- While there are no free instructions, it says: {t:ai.requests.none}

## Related

- [Actions and Claude](help:ai/actions)
- [Consents](help:ai/consents)
