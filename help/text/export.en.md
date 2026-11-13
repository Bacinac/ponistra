# Saving to a file

A document is saved as a Word, Excel, PowerPoint, PDF or Ponistra file, to send it or work on it in another program.

## How to use it

1. Click the document's title in the path and in the menu choose {t:save.as}.
2. Choose the format: {t:save.docx}, {t:save.pdf}, {t:save.xlsx}, {t:save.csv}, {t:save.pptx}, {t:save.ponx} or {t:save.ponxVersions}.
3. While the file is being made, {t:save.pending} stands above the document. The finished file downloads in the browser.

A document uploaded from an Office file with macros also offers {t:save.docm}, {t:save.xlsm} or {t:save.pptm}, after the format of the original file.

## How it works

The server makes the file. Before it does, the formulas in the tables are calculated.

- {t:save.docx}: each tab and each of its sections start on a new page, with their page setup, headers and footers. Styles, lists, tables, images, charts, notes, the contents, page fields, comments and proposals go over, the proposals as tracked changes in Word. The tabs' titles do not.
- {t:save.pdf}: the pages are laid out as for printing, and the pages of PDF files inserted in the document go in as they are.
- {t:save.xlsx}: each table becomes an Excel sheet, in order through the tabs, with its formulas, number formats, names, design and charts. The text around the tables does not go over. A table longer than an Excel sheet's 1,048,576 rows continues on the sheets after it.
- {t:save.csv}: the document's first table, each cell as it shows. Columns are separated by a semicolon where the document has a decimal comma, otherwise by a comma.
- {t:save.pptx}: the slides of all tabs in order, each tab a section of the presentation. The slide template, speaker notes and hidden slides go over. Proposals do not: the file holds the text as it was before them.
- {t:save.ponx}: Ponistra's own file, with nothing missing: tabs, styles, comments, proposals, images, PDF files and the file the document was uploaded from. {t:save.ponxVersions} also carries all the document's versions.

The original file's macros go into the saved file unchanged. Making a file that takes longer than a second is shown in the bottom right corner, where it can be cancelled. Each save is recorded in the document's access log.

## Limits

- {t:save.as} is not available in a {t:confined.label} folder to those who are not its owners.
- {t:save.xlsx} and {t:save.csv} report an error when the document has no table.
- {t:save.docx} and {t:save.pptx} report an error when the document has a table of more than 200,000 cells. Save such a table as {t:save.xlsx} or {t:save.ponx}.

## Related

- [Printing](help:text/print)
- [Uploading files](help:documents/upload)
- [Sharing](help:documents/sharing)
- [Versions](help:documents/versions)
