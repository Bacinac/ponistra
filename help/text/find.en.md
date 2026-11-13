# Find and replace

Finds a word or phrase across the whole tab, in its text, notes and every row of its tables, and replaces it in one place or everywhere at once.

## How to use it

### Finding

1. In a document, press {k:Mod-f} or type {t:command.find} in the search box.
2. Type what you are looking for. If you had selected text first, it is already filled in.
3. Every result in the text is highlighted and the current one is outlined. Beside the field you see which result it is of how many.
4. {k:Enter} or {t:find.next} goes to the next result, {k:Shift-Enter} or {t:find.previous} to the previous one.
5. {t:find.case} finds only the same upper and lower case, {t:find.words} only words that stand alone, not as part of a longer word.
6. {k:Escape} or the close button takes you back into the text, at the last result.

### Replacing

1. Press {k:Ctrl-h} or type {t:command.replace} in the search box. From finding, the arrow {t:find.showReplace} at the start of the bar opens replacing.
2. Type what you are looking for and, in the field {t:find.by}, what replaces it.
3. {t:find.replace} (or {k:Enter} in the field {t:find.by}) replaces the current result and moves to the next.
4. {t:find.replaceAll} replaces every result in the tab.

## How it works

The server searches, over the whole tab as it is saved, so rows of a table the browser has not loaded yet are found too. When a result is in such a row, the table scrolls to its cell and selects it.

A cell is searched by what it shows: a calculated cell by its calculated value, a number in its format. The apostrophe that keeps a value as text is not searched and stays after a replacement. A cell with a single paragraph is replaced by typing its shown text again with the replacement made; the formatting of text in paragraphs stays as it was at the replaced place.

Replacing one result and replacing all results are each one change: {t:command.undo} ({k:Mod-z}) takes back everything that replacement changed. The results are refreshed as soon as the tab changes, also when someone else changes it.

The first result is the one at the cursor or after it.

## Limits

- Only the open tab is searched, not its headers and footers, image descriptions or the document's other tabs. To search all documents, use the search box.
- Rows you have hidden are not searched, and a replacement does not change them.
- A cell whose value a formula calculates is found but not replaced: {t:find.replace} is then disabled and {t:find.replaceAll} skips it. Change the formula instead.
- At most 1000 results are shown. When there are more, a + follows the count.
- A replacement cannot contain a new line.
- When you only read the document, replacing is not offered.
- {t:find.none} means the tab holds no such text under the chosen options.

## Related

- [Shortcuts](help:text/shortcuts)
- [Table data](help:tables/data)
- [Search](help:start/search)
