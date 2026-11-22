# Text recognition

Pages of a PDF that carry no text, such as scanned documents, and the pages of a TIFF picture Ponistra reads by itself and gives them text, so they can be searched and the text selected and copied.

## How to use it

1. Upload the PDF or TIFF to a folder. Recognition starts by itself, with nothing to do.
2. While it runs, {t:ocr.waiting} is shown beside the page number.
3. When it is done, the PDF is shown with the recognised text.
4. If it reports {t:ocr.failed} press {t:ocr.retry} beside the message.

## How it works

Only the pages without text are read, in Croatian and English. The recognised text is laid into a copy of the file, which is what is shown, searched and downloaded. The original file stays as it was uploaded: the page's menu gives it with {t:file.original}.

A TIFF first becomes a PDF of all its pages, and all of them are read. While the reading runs, its first page is shown, with where the reading stands below it and, when it fails, {t:ocr.retry}. Once it is over, the PDF is shown. The {t:file.download} button always saves the original TIFF.

## Limits

- An encrypted or digitally signed file is not read, as that would break its protection. The reason is then shown beside the page number.

## Related

- [PDF files](help:pdf/viewer)
- [Files](help:files/overview)
- [File content by kind](help:files/held)
