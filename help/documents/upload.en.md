# Uploading files

You upload files and whole folders from your computer among your documents, and files from Office and LibreOffice become documents you edit in Ponistra.

## How to use it

### From the menu

1. Open the folder you are uploading into.
2. Press {t:create.new}, choose {t:create.upload} or {t:create.uploadFolder} and pick the files or the folder in the browser's window.
3. While the transfer runs, the line under the list reads {t:upload.progress} with the number of files and the amount of data transferred.

### By dragging

1. Drag files or folders from your computer onto the list of the open folder.
2. Drop them on an empty place in the list to land them in the open folder, or on a folder in the list or in the left column to land them in it.

## How it works

Word, Excel and PowerPoint files and OpenDocument files (`.docx`, `.doc`, `.rtf`, `.odt`, `.xlsx`, `.xls`, `.ods`, `.pptx`, `.ppt`, `.odp` and related kinds with macros and templates), `.csv` and `.ponx` are imported into a document. In a very large table the first rows show as soon as they arrive, and the rest keep coming while the import runs. All others stay the files they are and open in a preview. Bookmarks a browser exports as HTML become a folder of links. What the import could not carry, the document shows in an [import report](help:documents/import).

An uploaded folder keeps its subfolders. Files and subfolders whose name starts with a dot are skipped. Each item's modified date is taken from the file on your computer, not from the moment of the upload.

When a file cannot be imported because it is unreadable or too large, because a workbook has too many cells or different formulas, or because it was saved by a newer version of its program, it is kept as a plain file, and the line under the list says so with the reason. The other files upload all the same. Files that did not upload at all are listed in the line {t:upload.failed}

Jobs that take longer than a second, such as an import, making a copy or saving in another format, show in a box in the bottom right corner: {t:job.import}, {t:job.copy}, {t:job.saving}, {t:job.compose} or {t:job.redact}, with the name and the state {t:job.waiting} or {t:job.running}. While a job can still be stopped, {t:tree.cancel} stands beside it. An upload goes on when you move to another page.

## Limits

- You can upload only into a folder where you have the right to edit.
- While a file is transferring, the line under the list reads {t:file.uploading}
- Large files are sent in pieces, and the server refuses a file over the installation's limit or when it runs out of room.

## Related

- [Import report](help:documents/import)
- [Documents overview](help:documents/overview)
- [Files](help:files/overview)
