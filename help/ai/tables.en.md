# Actions on a table

Actions on a table total columns, calculate a new column, clean and group data and draw a chart, without sending data outside the installation.

## How to use it

### Totals

1. Put the cursor in the table and open the {t:commandGroup.table} menu on the toolbar or by right-clicking.
2. Choose {t:action.tableTotals} to total every column of numbers.
3. For one column, put the cursor in it and under {t:action.tableTotal} choose {t:action.tableTotal.sum}, {t:action.tableTotal.average}, {t:action.tableTotal.count}, {t:action.tableTotal.counta}, {t:action.tableTotal.min}, {t:action.tableTotal.max} or {t:action.tableTotal.none}.

### A calculated column

1. Put the cursor in an empty column and choose {t:action.tableCalculate.ask}
2. In the {t:action.tableCalculate} dialog, under {t:calculate.operation}, choose {t:action.tableCalculate.sum}, {t:action.tableCalculate.difference}, {t:action.tableCalculate.product}, {t:action.tableCalculate.quotient}, {t:action.tableCalculate.average}, {t:action.tableCalculate.min} or {t:action.tableCalculate.max}.
3. Under {t:calculate.columns} choose the columns in the order they enter the calculation; the formula shows above.
4. Press {t:calculate.run}.

### Cleaning, grouping and a chart

1. {t:action.tableClean} tidies the data of the whole table.
2. {t:action.tableGroup} groups by the column the cursor is in.
3. {t:action.tableChart} draws a chart from the selected cells or from the whole table.

## How it works

{t:action.tableTotals} adds a row below the data that totals each column of numbers, in the number format most of the column shows. Run again, it covers the rows the data has by then. {t:action.tableTotal} puts the chosen function in the totals row under the column and makes that row if there is none; a column that holds more than numbers is offered only {t:action.tableTotal.counta}.

A calculated column writes a formula into every row of the data, as Excel's calculated column does, and a new row takes it over. {t:action.tableCalculate.difference} and {t:action.tableCalculate.quotient} take exactly two columns, the other operations two or more.

{t:action.tableClean} removes the spaces around text and repeated spaces within it, turns numbers written as text into numbers and deletes empty rows and columns. {t:action.tableGroup} sorts the data by the column and below each group adds a row subtotalling the other columns of numbers, and below everything a totals row. Grouping again, by any column, first removes the earlier groups. {t:action.tableChart} adds a column chart just after the table.

## Limits

- A calculated column is written only into an empty or already calculated column and calculates only with columns that hold numbers.
- A column cannot be calculated from itself.
- Each of these actions is taken back with {t:run.undo}.

## Related

- [Actions and Claude](help:ai/actions)
- [The agent beside the document](help:ai/agent)
- [Extracting data from documents](help:ai/gathering)
