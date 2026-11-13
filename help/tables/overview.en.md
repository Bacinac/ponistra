# Tables

A table in a document works as a spreadsheet sheet: cells hold text, numbers and formulas, and the server calculates the formulas' values.

## How to use it

![A table with the name box on the toolbar](shot:tables-table)

### Writing in cells

1. You insert a new table from the {t:editor.insert} menu with {t:command.table}.
2. Click a cell and write. {k:Tab} takes you to the next cell, {k:Shift-Tab} to the one before, and the arrows to the neighbouring one when the cursor is at the edge of the text.
3. {k:Shift-ArrowDown} and the other arrows with {k:Shift} extend the selection over several cells. Typing over selected cells empties them and writes in the first, and {k:Delete} empties them.

### Formulas

1. In an empty cell type `=` and go on with the formula, for example `=SUM(B2:B5)`.
2. While you write a formula, clicking another cell writes in its address. A cell of another table is written with the table's name, as `Costs!B4`.
3. {k:Enter} keeps the formula and takes you to the cell below, {k:Tab} to the right, and {k:Escape} gives it up.

### Name box

1. When the cursor is in a table, the toolbar holds the {t:nameBox.label} with the address of the selected cells.
2. Type an address (`B4` or `B4:D9`), a table's name with an address or a defined name and press {k:Enter}.
3. On a narrow screen {t:command.goTo} ({k:Mod-g}) opens the {t:nameBox.title} dialog with the same field and the {t:nameBox.go} button.

## How it works

A cell with a formula shows the calculated value, and the formula when you open it. A number sits at the cell's right edge, typed or calculated, unless you give it another alignment. A formula that cannot be read stays open, with an explanation under the cell. A formula's arguments are separated by semicolons when the document's language writes a decimal comma, as Croatian does, and by commas when it writes a decimal point, as English does.

When the table is selected, when cells are selected or while a formula is being written, the column letters and row numbers show beside the table. Screen readers announce a cell as {t:table.cell} with its address, and the formula field as {t:table.formula} with its address.

{k:Tab} in the last cell adds a new row.

## Limits

- The name box also leads to a table in another tab, but reports an error when the table or name does not exist or the address is outside the table.
- With the right to read, formulas can be opened but not changed.

## Related

- [Rows and columns](help:tables/rows-columns)
- [Data in a table](help:tables/data)
- [Table name](help:tables/names)
- [Document language](help:text/language)
