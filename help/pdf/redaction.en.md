# Redaction

Redaction makes a copy of a PDF from which what you marked is removed for good, such as personal data before a document is sent.

## How to use it

### Marking

1. Press {t:pdf.redact} on the toolbar. The redaction tool bar appears.
2. Drag a rectangle over what is to be blacked out. The mark is shown hatched.
3. You can also mark text by selecting it and pressing {t:pdf.redact} beside the selection.
4. For every occurrence of a text, open the search, type the text and press {t:pdf.redact.found}. The {t:pdf.redact.marked} notice gives the number of matches.
5. Press a mark and then {t:pdf.remove} or {k:Delete} to remove it.

### The redacted copy

1. On the redaction tool bar, press {t:pdf.redact.save}
2. In the {t:pdf.redact.save.heading} dialog, keep or change the name. The suggested name is the file's own with "(redacted)" added.
3. The copy is saved beside the original and opens when it is ready.

## How it works

The text, images and drawings under the marks are taken out of the copy, and a black rectangle is drawn in their place. The links, notes and form fields the marks touch are removed too, and from the whole copy its metadata, attachments, scripts, page thumbnails and earlier revisions. Before it is saved, the copy is read again: if a single character is left under a mark, the copy is not saved.

The original file and the marks stay as they are, so you can make the copy again. Notes and form values the marks do not touch are carried into the copy.

## Limits

- Redaction is offered only to someone who may edit the file.
- A password-protected file, and a file that forbids changes to its content, cannot be redacted.
- The file's digital signatures are not carried into the copy.
- When you may not add to the file's folder, the copy is saved among your own documents.

## Related

- [Notes and comments in a PDF](help:pdf/notes)
- [PDF files](help:pdf/viewer)
