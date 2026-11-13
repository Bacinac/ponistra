# Page setup

Paper size, orientation, margins, header and footer, and page numbers are set for the whole document, for a single tab or for a section.

## How to use it

### Paper and margins

1. In the document's menu choose {t:page.setup} The {t:page.title} dialog opens.
2. Under {t:page.paper} choose a format, or {t:page.ownSize} and type the {t:page.width} and {t:page.height}.
3. Under {t:page.orientation} choose {t:page.portrait} or {t:page.landscape}.
4. Under {t:page.margins} choose {t:page.margins.normal}, {t:page.margins.narrow}, {t:page.margins.wide} or {t:page.margins.own} and type {t:page.top}, {t:page.bottom}, {t:page.left} and {t:page.right}.
5. Type the {t:page.header} and {t:page.footer} distances and press {t:page.apply}.

### Page numbers

1. In the same dialog tick {t:page.restart} and type the {t:page.start}.
2. The page number goes into the header or footer as a field.

### Header and footer

1. In the {t:view.pages} view, in the {t:editor.insert} menu choose {t:command.header} or {t:command.footer}, or double-click the page's top or bottom edge.
2. Write as in the text. The {t:editor.insert} menu offers the fields {t:field.page}, {t:field.pages}, {t:field.date} and {t:field.title}.
3. On the toolbar, under {t:commandGroup.part}, turn on {t:command.firstApart} for a separate first-page header (the {t:page.firstPage} box in the {t:page.title} dialog does the same), and in a section {t:command.partLinked} for the header of the section before.
4. {t:command.closePart} ({k:Escape}) takes you back to the text.

### Breaks

1. {t:command.pageBreak} ({k:Mod-Enter}) from the {t:editor.insert} menu carries the text on to a new page.
2. {t:command.sectionBreak} starts a new section, which can have a page setup of its own.
3. {t:command.columnBreak} ({k:Shift-Mod-Enter}) carries the text on to the next column.

## How it works

The document's setup holds for every tab without one of its own. When the document has several tabs, under {t:page.source} you choose {t:page.fromDocument} or {t:page.own}. A tab that goes back to the document's setup loses its own headers and footers, which the dialog warns of. In a section after a break, under {t:page.sectionSource} you choose {t:page.fromSection} or {t:page.own}.

Without a page setup of their own, a tab's pages carry on the numbering of the tab before. The fields in the header and footer show the number of the page they stand on, the total of pages, the date and the document's title. With {t:command.firstApart} the first page gets the {t:part.headerFirst} and {t:part.footerFirst}, apart from the {t:part.header} and {t:part.footer} of the others.

## Limits

- Header and footer are edited only in the pages view.
- Margins must not leave the page without room for text: the dialog then does not allow applying.
- Only someone who may edit the document changes the setup.

## Related

- [Ruler and tab stops](help:text/ruler)
- [Printing](help:text/print)
- [Tabs](help:text/tabs)
