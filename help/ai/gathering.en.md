# Extracting data from documents

Claude extracts the same data from several documents and PDF files into one table, one row for each document, in a new document beside them.

## How to use it

1. In a folder choose documents, PDF files or folders.
2. With the right mouse button or under the three dots on the selection bar choose {t:action.nodesExtract.ask}
3. In the dialog {t:action.nodesExtract} type the {t:tree.name} of the new document; the chosen item's or folder's name with {t:gather.name} is suggested.
4. Under {t:gather.columns} type the names of the columns or leave the field empty.
5. Press {t:gather.run}.
6. On the action's bar press {t:run.open} to open the new document.

## How it works

Claude reads each chosen document and PDF and those directly in the chosen folders, tab by tab or page by page, and gives one row from each. Without given columns Claude chooses them from the first document, and the rest follow them. A row's first cell is the document's name, linked to it.

The new document is made in the folder of the chosen items and, if they are not in one folder, at the top of your documents. The action's bar shows {t:run.through} and how many documents are done; once it ends, {t:run.missed} lists the documents that were not done and why.

{t:run.undo} moves the new document to the trash.

## Limits

- Pressing {t:gather.run} is also your consent to sending the chosen documents' content to Claude, for that one run.
- At most 30 columns and 500 chosen items.
- The action is disabled while AI is not turned on for the installation and for items in a folder without downloads.

## Related

- [Actions and Claude](help:ai/actions)
- [Actions on a table](help:ai/tables)
- [Working with items](help:documents/organising)
