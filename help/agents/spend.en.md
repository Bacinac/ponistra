# Token spend

How many tokens the workspace's chats took, by project, model, round, chat and day, beside the plan's limits and what Ponistra's own AI cost.

## How to use it

1. On the {t:rail.projects} page press {t:workspace.view.spend}, far right in the row with {t:workspace.view.chat} (on a phone with {t:workspace.view.overview}).
2. The latest month stands on top: {t:workspace.spend.input}, {t:workspace.spend.output}, {t:workspace.spend.cacheRead} and {t:workspace.spend.cacheWrite} in tokens, {t:workspace.spend.worth} and {t:workspace.spend.api}.
3. Below are the same columns {t:workspace.spend.projects} (column {t:workspace.spend.project}), {t:workspace.spend.models} ({t:workspace.spend.model}), {t:workspace.spend.rounds} ({t:workspace.spend.round}) and {t:workspace.spend.chats} ({t:workspace.spend.chat}), each row with a {t:workspace.spend.week} column. Hold the pointer on a chat to see its session id.
4. Under {t:workspace.hours.days} each day shows {t:workspace.spend.turns}, {t:workspace.spend.worth}, {t:workspace.spend.session} and {t:workspace.limits.week} as measured that day, and {t:workspace.spend.api}.
5. At the bottom, under {t:workspace.spend.actions}, stands each Ponistra action that used AI in the month, with its number of runs and its cost.
6. For another month choose it in the {t:workspace.hours.month} field.

While nothing has been measured, it says {t:workspace.spend.none}

## How it works

The workspace counts the tokens from the same chat transcripts it measures the [time worked](help:agents/projects) from, every minute: for each answer of the model how much it read as new input, how much it wrote, how much it read from the cache and how much it wrote into it. Claude Code writes one answer in several lines carrying the same numbers, so each counts once; an answer the transcript cut in half counts once too. Helper agents a chat started count under that chat. A chat in a round counts under that round as well, from the moment it is in it. Ponistra keeps the tokens in its database by hour and model, with a mark of how far each transcript was read, so reading again counts nothing twice, and what was counted stays when the transcript is deleted. The first time, the workspace reads every transcript it still has from the start, so the spend shows for earlier chats too.

A plan is not paid by the token, so {t:workspace.spend.worth} says what the same tokens would cost at the API's prices in dollars: cache writes at 1.25 times the input price, cache reads at their own price. That weight roughly follows how the plan's limits count them, so it is a measure to compare by, not a bill. Models Ponistra has no price for stay out of the amount; the amount then carries an asterisk, and below the month it says which models they are. {t:workspace.spend.week} divides the row's amount by what has been spent since the current weekly window began and says roughly what share of the weekly limit it is.

The workspace reports the limits to Ponistra on every change of the five-hour or the weekly window, and Ponistra keeps every measure; a day shows the highest five-hour window measured and the weekly one measured last. {t:workspace.spend.api} and {t:workspace.spend.actions} are what Ponistra paid with its own AI key, from the cost of each action. At most 50 chats stand, those with the largest amount. The page refreshes by itself when new tokens or a new measure arrive.

## Limits

Only the workspace's owner sees the page ({t:error.not_the_owner}). Only chats whose transcripts are in the workspace count, in it and in the editor; chats of the same plan on other computers use up the limits but do not show here. The tokens of a chat whose transcript was deleted before the workspace read it are not counted. Days are in Croatian time.

## Related

- [Projects](help:agents/projects)
- [Writing the time worked](help:agents/hours)
