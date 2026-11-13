# Printing

A document is printed through the browser's print dialog, page by page as its page setup lays them out.

## How to use it

1. Click the document's title in the path and in the menu choose {t:print.open}
2. While the pages are being laid out, {t:print.preparing} stands above the document.
3. When the pages are ready, the browser's print dialog opens. In it you choose a printer or saving as PDF.

## How it works

All the document's tabs are printed, one after another. Each section of a tab is printed on the paper of its page setup, with its header and footer. Page numbers run on through all the tabs, except from a section that starts numbers of its own. Endnotes are printed after the tab's last section.

The pages are laid out on a separate print page, without the app's frame. The server uses the same page when it makes a PDF or PowerPoint file.

## Limits

- {t:print.open} is not available in a {t:confined.label} folder to those who are not its owners.

## Related

- [Page setup](help:text/page)
- [Saving to a file](help:text/export)
