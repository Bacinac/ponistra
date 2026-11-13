# Table name

A table's name lets formulas refer to that table from the document's other tables, as to a workbook's sheet.

## How to use it

1. Stand in the table and in the {t:commandGroup.table} menu choose {t:command.tableName} The {t:tableName.title} dialog opens.
2. In the {t:tableName.name} field type the name and press {t:tree.save}.
3. In another table's formula you refer to it by its name, an exclamation mark and an address, for example `Costs!B4`.

## How it works

Under the field the dialog says why a name is not acceptable: when it is too long, holds characters that are not allowed or another table in the document already has it. Capital and small letters count as the same. The name of a table imported from Excel is the sheet's name.

## Limits

- A name has at most 31 characters and holds none of the characters `[ ] : * ? / \`.
- While formulas refer to the table, its name cannot be taken away.

## Related

- [Tables](help:tables/overview)
- [Data in a table](help:tables/data)
