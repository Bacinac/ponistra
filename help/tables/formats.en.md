# Number format and fill

The number format decides how a cell shows its value, and the fill gives it a background colour.

## How to use it

### Number format

1. Select the cells.
2. With a right click or in the {t:commandGroup.table} menu on the toolbar open {t:command.cellFormat}.
3. Choose {t:cellFormat.general}, {t:cellFormat.number}, {t:cellFormat.integer}, {t:cellFormat.currency}, {t:cellFormat.percent}, {t:cellFormat.scientific}, {t:cellFormat.date}, {t:cellFormat.time} or {t:cellFormat.dateTime}.

### A format of your own

1. In the same menu choose {t:cellFormat.custom} The {t:cellFormat.title} dialog opens.
2. In the {t:cellFormat.code} field type a format code, as Excel writes it. Under the field, after {t:cellFormat.examples} stand example codes.
3. Press {t:tree.save}. An empty code gives back {t:cellFormat.general}.

### Cell fill

1. Select the cells and open {t:command.fill}.
2. Choose a colour or {t:color.none}.

## How it works

A format changes only what is shown: the cell's value and the formulas that read it stay the same. {t:cellFormat.general} shows the value as it is.

{t:cellFormat.number} has two decimals and a thousands separator, and {t:cellFormat.integer} has no decimals. {t:cellFormat.currency} writes the euro for Croatian, German, French, Italian and Spanish, the dollar for English and the pound for British English. The signs for thousands and decimals and the way a date is written follow the document's language, in the code of your own format too.

The fill offers the same colours as text highlighting.

## Limits

- A format code of your own has at most 255 characters.

## Related

- [Tables](help:tables/overview)
- [Table design](help:tables/design)
- [Document language](help:text/language)
