# Data in a table

You sort a table's rows by a column, fill cells with a series or copies, and duplicate a table with values instead of formulas.

## How to use it

### Sorting

1. Stand in the column you sort by. For only some rows, select cells in those rows.
2. With a right click or in the {t:commandGroup.table} menu on the toolbar choose {t:command.sortAscending} or {t:command.sortDescending}.

### Filling

1. Select cells and drag the small square at the bottom right corner of the selection over the cells you want to fill.
2. To copy without a series, select the cells and press {t:command.fillDown} ({k:Mod-d}) or {t:command.fillRight} ({k:Mod-r}).

### Duplicating

1. Stand in the table and choose {t:command.duplicateValues}.
2. The copy appears right under the table and is selected.

## How it works

Sorting takes in all rows below the header, except the totals row, or only the selected rows. Numbers come before text, text in the alphabetical order of the document's language, then logical values and errors; descending is the reverse. Empty cells always come last, and rows with equal values keep their order. Upper and lower case count as the same. A cell merged within one row moves with its row.

The server sorts, by the values calculated and saved, over every row of the table, also those the browser has not loaded yet. A sort is one change that {t:command.undo} takes back. While your [filter](help:tables/filter) is on, sorting and filling reach only the rows shown.

Dragging the square carries on a series where the selected cells make one, and otherwise repeats them, with their look and number format. A formula moves with each copy as cells are filled. {t:command.fillDown} copies the first row of the selection over the rest, and when one row is selected, copies the row above it; {t:command.fillRight} does the same with columns.

{t:command.duplicateValues} writes into the copy the values the formulas show, so the copy no longer depends on the original table.

## Limits

- Rows that a cell merged over several rows joins cannot be sorted, as they would be parted. Sort only the rows above or below it.
- Merged cells can neither be filled nor be the source of a fill.

## Related

- [Tables](help:tables/overview)
- [Rows and columns](help:tables/rows-columns)
- [Actions on a table](help:ai/tables)
