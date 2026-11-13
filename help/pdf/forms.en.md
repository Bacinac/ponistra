# Forms in a PDF

A PDF with a form is filled in right on the page, and the values entered come with the downloaded file.

## How to use it

1. Open the PDF with the form. The fields are shown on its pages.
2. Type into the fields, choose from lists and tick boxes.
3. When a field does not accept what you entered, a notice appears above the pages. The {t:form.notice.close} button closes it.
4. Press {t:file.download}. The downloaded file carries the values entered, and its fields stay form fields.

## How it works

The values entered are kept beside the file, so everyone who has the file open sees them at once, while the original file stays empty. The form's scripts run as you type: they compute fields and check what was entered. Their messages about a field's format, a date and the allowed range are shown in the interface's language, and the others as the file words them.

## Limits

- Only someone who may edit the file can change the fields. Others see the values entered but cannot change them.
- A form made only in the XFA format cannot be filled in.
- An electronic signature field is shown, but Ponistra does not sign documents.
- Form actions that do not lead to a place, such as printing or saving asked for by a script, Ponistra does not carry out, and it says so.
- When a form's script fails, a notice warns that the computed values may not be correct.
- Values entered are not written into a password-protected PDF.

## Related

- [PDF files](help:pdf/viewer)
- [Notes and comments in a PDF](help:pdf/notes)
