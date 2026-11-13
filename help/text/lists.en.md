# Lists

You turn paragraphs into a bulleted list, a numbered list or a checklist with ticks, with levels and markers of your own form.

## How to use it

### Making a list

1. Stand in a paragraph or choose several.
2. On the toolbar press {t:command.bulletList} ({k:Shift-Mod-8}), {t:command.numberList} ({k:Shift-Mod-7}) or {t:command.checkList} ({k:Shift-Mod-9}).
3. Typing at the start of a line does the same: “- ” for bullets, “1. ” for numbers, “[] ” for ticks.
4. {k:Tab} moves an item a level down, and {k:Shift-Tab} brings it back. {t:command.indentMore} ({k:Mod-m}) and {t:command.indentLess} ({k:Shift-Mod-m}) do the same.

### The markers' form

1. Stand in a list and open {t:editor.listForm} on the toolbar.
2. Choose a ready form: {t:command.bulletForm} for a bulleted list, {t:command.numberForm} for a numbered one.
3. In the same menu, {t:command.numberRestart} starts counting anew from that item, and {t:command.numberContinue} carries on the numbers of the list before.

### A form of your own

1. In the {t:editor.listForm} menu choose {t:command.listFormat} The {t:listFormat.title} dialog opens.
2. On the left choose a level ({t:listFormat.level}).
3. Under {t:listFormat.kind} choose {t:listFormat.number} or {t:listFormat.bullet}.
4. For numbers choose the {t:listFormat.numbering}, the text {t:listFormat.prefix} and {t:listFormat.suffix}, and if you wish {t:listFormat.nested}. For bullets type the {t:listFormat.symbol} or choose it among the {t:listFormat.symbols}.
5. Check the {t:listFormat.preview} and press {t:styles.apply}.

## How it works

The form holds for the whole list the item belongs to, for each level separately.

{k:Enter} in an empty item brings it a level up, and on the first level ends the list, and {k:Backspace} at the start of an item removes its marker. You tick a checklist box by pressing it.

## Limits

- Every level with a bullet must have a symbol.
- Heading numbers are not set here but in the [styles](help:text/styles).

## Related

- [Styles and theme](help:text/styles)
- [Ruler and tab stops](help:text/ruler)
- [Formatting text](help:text/formatting)
