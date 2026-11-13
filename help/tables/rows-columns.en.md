# Rows and columns

You add, delete, hide and freeze a table's rows and columns, and merge and split cells.

## How to use it

### Adding and deleting

1. Stand in a cell or select several cells.
2. Open the {t:commandGroup.table} menu on the toolbar or with a right click.
3. Choose {t:command.rowAbove}, {t:command.rowBelow}, {t:command.columnLeft} or {t:command.columnRight}.
4. {t:command.deleteRow} and {t:command.deleteColumn} delete all rows or columns of the selected cells, and {t:command.deleteTable} the whole table.

### Hiding

1. Select cells in the rows or columns you want to hide.
2. Choose {t:command.hideRows} or {t:command.hideColumns}.
3. To show them again, select cells on both sides of the hidden ones and choose {t:command.showRows} or {t:command.showColumns}.

### Merging cells

1. Select at least two cells and choose {t:command.mergeCells}.
2. You turn a merged cell back into single ones with {t:command.splitCell}.

### Freezing rows

1. Stand in the row below those that should stay at the top.
2. Choose {t:command.freezeRows}. {t:command.unfreezeRows} ends the freezing.

## How it works

Frozen rows stay at the top of the view while the table scrolls. In the Pages view they repeat at the top of each page the table runs on to.

A new row or column comes beside the first or last row or column of the selected cells.

Hidden rows and columns are hidden for every user of the document. Row numbers skip the hidden rows, and a bar in the heading marks where they are. When the selection reaches the first or last row of the table, {t:command.showRows} shows the hidden rows before or after it too.

## Limits

- Not all rows or all columns of a table can be deleted: {t:command.deleteTable} is for that.
- {t:command.freezeRows} is not available in the first row.

## Related

- [Tables](help:tables/overview)
- [Data in a table](help:tables/data)
