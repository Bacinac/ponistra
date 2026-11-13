# The agent beside the document

The agent is a conversation with Claude beside the open document: each instruction is carried out on the tab you are looking at, and each step of the conversation can be undone on its own.

## How to use it

### A conversation

1. On the document's bar press {t:agent.title} or choose {t:action.textAsk.ask} in the menu
2. If the instruction concerns part of the text, select it in the document.
3. Type the instruction and press {k:Enter} or {t:agent.send}. A new line in the instruction comes with {k:Shift-Enter}.
4. While Claude works, press {t:run.stop} for it to stop after the step it is on.
5. When Claude offers answers to how the instruction is meant, press the one that holds.
6. Press {t:agent.undo} under a step to take back everything that step changed. The step then reads {t:agent.undone}.
7. Press {t:agent.new} to start the conversation afresh, without the earlier steps.

### Analysing a table

1. Put the cursor in a table.
2. In the {t:commandGroup.table} menu on the toolbar or by right-clicking, choose {t:action.tableAnalyse}.
3. The analysis opens in a new tab when Claude is done.

## How it works

Claude reads the tab you are looking at, the selected paragraphs and the earlier steps of the same conversation, so an instruction such as "now as a pie chart" changes what the step before made. Text it writes comes as a proposal, while formatting, tables and charts change at once. Where an instruction can be read in ways that lead to different results, Claude changes nothing and asks, offering two to four answers. The conversation is yours: others in the document see the step on the action's bar as {t:action.textAsk}, but not your conversation. When you open the panel again, it shows your latest conversation in that document.

Of a long table Claude reads the first 100 rows, and fetches the other rows and an overview of the whole table by column (kinds of value, distinct and commonest values, least and greatest number) when it needs them. It never computes a number it states itself: it writes a formula, reads what it computed and only then writes about it.

{t:action.tableAnalyse} opens a new tab named {t:agent.analysis} and the source tab's name. Into it Claude writes a heading, tables of formulas over the source table's data (sums, averages, spread, shares by category, the correlation of numeric columns), charts and a short text on what they show. If the source table has no name, it is given one after the tab so that formulas can address it. When the data changes, the formulas in the analysis compute again.

## Limits

- The agent is available only to those who may edit the document, not to visitors from outside.
- An instruction takes at most 4000 characters, and Claude reads at most 20 earlier steps of a conversation.
- The agent and the analysis send content to Claude and ask for the same consent as other actions with a model.
- While one step runs, the next cannot be sent.
- {t:agent.undo} on an analysis closes the new tab and removes the name the table was given.

## Related

- [Actions and Claude](help:ai/actions)
- [Writing with Claude](help:ai/writing)
- [Actions on a table](help:ai/tables)
- [Proposals](help:ai/proposals)
