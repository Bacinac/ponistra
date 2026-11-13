# PDF files

A PDF is read in Ponistra page by page, with text search and the file's own contents, without the file itself changing.

## How to use it

### Moving through pages

1. Open the PDF from a folder. The pages follow one below the other.
2. Type a page number in the {t:pdf.page} field and press {k:Enter}. Beside the field is the total number of pages.
3. Under {t:zoom.label} you choose {t:zoom.page} or {t:zoom.width}.
4. When the PDF has contents of its own, they are shown in the left column, and pressing a heading goes to its page.

### Finding in the file

1. Press {t:pdf.find} on the toolbar, or {k:Mod-f}.
2. Type the text. Matches are highlighted on the pages, and beside the field is which match of how many, or {t:pdf.find.none}.
3. {t:pdf.find.next} or {k:Enter} goes to the next match, and {t:pdf.find.previous} or {k:Shift-Enter} to the previous one.
4. {t:pdf.find.close} or {k:Escape} closes the search.

### A password-protected file

1. When a PDF asks for a password, the {t:pdf.locked} dialog opens.
2. Type the {t:pdf.password} and press {t:pdf.unlock}. For a wrong password the dialog reports: {t:pdf.wrongPassword}
3. If you cancel, the file is not shown, and the {t:pdf.unlock} button asks for the password again.

## How it works

The search ignores case and diacritics. Links in a PDF go to a place in the file or open an outside address in a new tab. Notes and comments the PDF brought from other programs are shown on its pages.

The toolbar also holds the tools for notes, comments and redaction, and forms are filled in right on the page. All of this is kept beside the file, while the original file stays as it was uploaded.

## Limits

- Neither notes nor form values are written into a password-protected PDF, and its pages cannot be rearranged.
- When a file forbids changes to its content, it cannot be redacted.

## Related

- [Notes and comments in a PDF](help:pdf/notes)
- [Forms in a PDF](help:pdf/forms)
- [Redaction](help:pdf/redaction)
- [Arranging pages](help:pdf/pages)
- [Text recognition](help:pdf/ocr)
- [Files](help:files/overview)
