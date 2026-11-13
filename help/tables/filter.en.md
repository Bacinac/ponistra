# Table filter

A filter shows only the rows of a table whose cells hold the values chosen or meet a condition, and shows them so to you alone.

## How to use it

### By a cell's value

1. Stand in the cell whose value you want to keep.
2. Right-click, or in the {t:commandGroup.table} menu on the toolbar, choose {t:command.filterByValue}.

### By a column's values

1. Choose {t:command.filter} in the column you filter.
2. Under {t:filter.values}, leave ticked the values whose rows you want to see. {t:filter.search} narrows the list, and {t:filter.all} ticks or unticks every value shown. Empty cells are listed as {t:filter.empty}.
3. Press {t:filter.apply}.

### By a condition

1. Choose {t:command.filter} in the column you filter, and then {t:filter.condition}.
2. In {t:filter.op}, choose the comparison: {t:filter.equals}, {t:filter.notEquals}, {t:filter.begins}, {t:filter.ends}, {t:filter.contains}, {t:filter.notContains}, {t:filter.greater}, {t:filter.greaterEqual}, {t:filter.less} or {t:filter.lessEqual}.
3. Enter the {t:filter.value} and press {t:filter.apply}.

### Changing and clearing

1. The filter's conditions stand above the table, one for each column. Pressing a condition ({t:filter.edit}) opens it to change, and pressing × takes it off.
2. In the filter window, {t:filter.clear} takes off that column's condition.
3. {t:command.unfilter} takes off every condition of the table.

## How it works

The filter is saved for your user and for that table, so it holds on each of your devices and when you open the document again. Other users of the document see every row. A user who can only read the document can filter it too.

A row is shown when it is not hidden and meets the conditions of every column. Values are compared as the cell shows them, upper and lower case alike. The greater and less comparisons take only cells holding a number, the number written as in the document's language. Beside each value in the list stands the number of rows showing it among the rows the other columns' conditions let through.

Row numbers keep their place in the table and, while a filter is on, show in the accent colour. Addresses in formulas and in the name box always refer to the real rows.

Sorting, filling, deleting and hiding the selected rows change only the rows shown. When an edit of a cell changes whether its row meets a condition, the row appears or goes at once. Formulas calculate over every row, those the filter does not show too, and printing and export do not apply your filter.

## Limits

- Each column has one condition: either the values chosen or one comparison.
- An address of a row the filter does not show reports {t:filter.notShown}
- The list shows at most 1000 different values. For the rest, use a condition.
- The message {t:filter.refused} appears when a greater or less comparison has no number in {t:filter.value}.

## Related

- [Rows and columns](help:tables/rows-columns)
- [Data in a table](help:tables/data)
- [Tables](help:tables/overview)
