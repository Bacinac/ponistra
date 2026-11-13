# Ruler and tab stops

A paragraph's alignment, indents and tab stops, and the page's margins, are changed with commands or by dragging the marks on the ruler in the pages view.

## How to use it

### Alignment and indent

1. Stand in a paragraph or choose several.
2. In the {t:editor.align} menu choose {t:command.alignLeft} ({k:Shift-Mod-l}), {t:command.alignCenter} ({k:Shift-Mod-e}), {t:command.alignRight} ({k:Shift-Mod-r}) or {t:command.alignJustify} ({k:Shift-Mod-j}).
3. {t:command.indentMore} ({k:Mod-m}) and {t:command.indentLess} ({k:Shift-Mod-m}) move the paragraph right or left.

### The ruler

1. Switch to the {t:view.pages} view. The horizontal ruler stands above the page, the vertical one beside it.
2. On the horizontal ruler drag the {t:ruler.left} or {t:ruler.right}, the {t:ruler.indent}, {t:ruler.hanging}, {t:ruler.first} or {t:ruler.indentRight}.
3. On the vertical ruler drag the {t:ruler.top}, {t:ruler.bottom}, {t:ruler.header} or {t:ruler.footer}.

### Tab stops on the ruler

1. With the button beside the horizontal ruler choose the {t:ruler.tabKind}: {t:ruler.tab.left}, {t:ruler.tab.center}, {t:ruler.tab.right} or {t:ruler.tab.decimal}.
2. Press the ruler where you want the tab stop.
3. Drag the tab stop to a new place. A right click on it changes its kind, its {t:ruler.leader} ({t:ruler.leader.none}, {t:ruler.leader.dot}, {t:ruler.leader.hyphen} or {t:ruler.leader.underscore}), or removes it with {t:ruler.tab.remove}.

### The tab stops dialog

1. In the right-click menu in the text, or in a tab stop's menu on the ruler, choose {t:command.tabStops} The {t:tabStops.title} dialog opens.
2. Type the {t:tabStops.position}, choose the kind and the leader, and press {t:tabStops.set}.
3. Under {t:tabStops.list} you remove a tab stop with {t:tabStops.clear}, and all at once with {t:tabStops.clearAll}.
4. Press {t:styles.apply}.

## How it works

Indents and tab stops hold for the chosen paragraphs. Margins, header and footer hold for the whole section, as in the [page setup](help:text/page). The {k:Tab} key in the text inserts a {t:command.tab} up to the next tab stop, and a leader fills the gap up to it with dots, hyphens or an underscore.

A tab stop's position is measured from the left margin, in centimetres, and cannot lie beyond the text's width.

## Limits

- The ruler exists only in the pages view.
- With the right to read, the ruler's marks cannot be moved.

## Related

- [Page setup](help:text/page)
- [Lists](help:text/lists)
- [The document editor](help:text/overview)
