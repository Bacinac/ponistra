# Arranging pages

The pages of a PDF can be turned, moved, removed and joined by pages of other PDFs, and the result saved as a new file.

## How to use it

### Page order

1. On the PDF's page, press {t:pages.view}. The pages are shown as thumbnails.
2. Press a page to select it. With {k:Shift} you select a range, with {k:Mod} you add a single page, and {k:Mod-a} selects all.
3. The {t:pages.turnLeft} and {t:pages.turnRight} buttons turn the selected pages, and {t:pages.earlier} and {t:pages.later} move them by one place.
4. You can also drag pages to a new place.
5. {t:pages.remove} or {k:Delete} removes the selected pages.
6. {t:pages.undo} and {t:pages.redo} ({k:Mod-z} and {k:Mod-y}) take steps back and forth.

### Pages from another file

1. Press {t:pages.add}.
2. Choose {t:pages.add.tree} for a PDF from the folders or {t:pages.add.computer} for a PDF from your computer. {t:pages.add.tree} opens the {t:pages.add.heading} dialog.
3. The added file's pages go after the last selected page, or at the end. While the file loads, {t:pages.adding} is shown.

### Saving

1. {t:pages.save} saves all the pages in their new order, and {t:pages.extract} only the selected ones.
2. In the {t:pages.save.heading} or {t:pages.extract.heading} dialog, keep or change the name.
3. The new file is saved beside the original and opens when it is ready.

## How it works

Above the thumbnails, {t:pages.total} gives the total number of pages, or, when some are selected, how many are. The new file carries the notes and form values of the pages it holds, while comments stay with the file they were written on. The files the pages are taken from do not change.

A PDF uploaded from your computer to add pages is saved in the same folder as a file of its own. When every page has been removed, the view reports: {t:pages.empty}

While the new order is not saved, leaving the page asks {t:pages.leave} The {t:pages.discard} button discards the changes.

## Limits

- The pages of a password-protected file, and of a file that forbids it, cannot be rearranged or taken into other files. The {t:pages.view} button is then disabled.
- When you may not add to the file's folder, the new file is saved among your own documents.

## Related

- [Joining files](help:pdf/join)
- [PDF files](help:pdf/viewer)
