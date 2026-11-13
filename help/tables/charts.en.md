# Charts

A chart shows cells of a table in the same tab and changes along with them.

## How to use it

### A new chart

1. In the {t:editor.insert} menu choose {t:command.chart} The {t:chart.insert} dialog opens.
2. Choose the kind: {t:chart.column}, {t:chart.bar}, {t:chart.line}, {t:chart.area}, {t:chart.pie}, {t:chart.doughnut} or {t:chart.scatter}.
3. Check the {t:chart.table} and the {t:chart.range}, for example `A1:C5`.
4. Under {t:chart.seriesIn} choose {t:chart.byColumns} or {t:chart.byRows}.
5. Under {t:chart.names} and {t:chart.labels} choose {t:chart.automatic}, {t:chart.firstRow} or {t:chart.firstColumn}, or {t:chart.none}. A scatter chart has {t:chart.xValues} instead of categories.
6. If you like, type a {t:chart.title}, turn on {t:chart.stacked} and {t:chart.legend}, then press {t:chart.insertButton}.

### Editing

1. Double-click the chart, or select it and in the {t:commandGroup.chart} menu on the toolbar choose {t:command.editChart} The {t:chart.edit} dialog opens.
2. {t:command.deleteChart} removes the chart.

## How it works

A chart inserted from selected cells or from the table the cursor is in comes after the table. When the cursor is outside a table, the chart shows the nearest table above the cursor and is inserted where the cursor is.

A series without a name is called {t:chart.series} with a number in the legend. {t:chart.stacked} exists for column, bar, line and area charts. When the chart's table or cells no longer exist, when the table cannot be calculated or the cells hold no numbers, the chart shows an explanation instead of the drawing.

## Limits

- A chart shows only a table in the same tab, so it cannot be inserted in a tab without a table.
- The range must be inside the table.

## Related

- [Tables](help:tables/overview)
- [Inserting](help:text/insert)
- [Actions on a table](help:ai/tables)
