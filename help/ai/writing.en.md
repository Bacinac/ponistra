# Writing with Claude

Claude summarises, rewrites, translates and compares a document's text and the text it writes comes as a proposal.

## How to use it

### Summary, rewriting and a table

1. Select text or, for the whole tab, select nothing.
2. Right-click to open the menu.
3. Choose {t:action.textSummarise} or {t:action.textExtract}.
4. For {t:action.textRewrite} choose the way: {t:action.textRewrite.formal}, {t:action.textRewrite.simple}, {t:action.textRewrite.short} or {t:action.textRewrite.correct}.

### Translation and comparison

1. For {t:action.documentTranslate} choose the language in the submenu.
2. To compare, choose {t:action.documentCompare.ask}
3. Choose the {t:compare.version} and press {t:compare.run}.

## How it works

An action applies to the paragraphs the selection reaches, and without a selection to the whole tab. A summary and a data table are written after the selected text, and for the whole tab at its start, after the title. Rewritten text stands in place of the original, each paragraph in its own.

Translation copies the tab into a new tab beside it, named after the original in the chosen language, and translates the text, the text in cells, chart titles and image descriptions. Comparison describes what changed in the tab since the chosen version, at the tab's start after the title.

## Limits

- A summary, rewritten text, a data table, and a comparison come as proposals you accept or reject.
- A translation is written at once, into a new tab, not as a proposal.
- While the document has no version, a comparison cannot be run.

## Related

- [Actions and Claude](help:ai/actions)
- [The agent beside the document](help:ai/agent)
- [Proposals](help:ai/proposals)
- [Versions](help:documents/versions)
- [Comparison with a file](help:text/compare)
