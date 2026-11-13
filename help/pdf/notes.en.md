# Notes and comments in a PDF

You can highlight text in a PDF, draw on its pages and leave comments, without the original file changing.

## How to use it

### Highlighting text

1. Select text on the page. The highlight colours, {t:pdf.redact} and {t:command.comment} appear beside the selection.
2. Press a colour. The button's tooltip reads {t:pdf.highlight} with the colour's name.

### Drawing

1. Press {t:pdf.draw} on the toolbar.
2. On the tool bar, choose the pen's colour and its width: {t:pdf.width.1}, {t:pdf.width.2} or {t:pdf.width.4}.
3. Draw on the page by dragging.
4. {t:pdf.tool.close} or {k:Escape} ends drawing.

### Comment

1. Select text and press {t:command.comment}, or press {t:pdf.pin} on the toolbar and then a place on the page.
2. Write the comment in the comments panel.
3. A comment's mark on the page opens its thread in the panel.

### Removing

1. Press a highlight or a drawing on the page.
2. Press {t:pdf.remove} or {k:Delete}.
3. {k:Mod-z} and {k:Mod-y} undo and redo your steps.

## How it works

Highlights, drawings, comments and form values are kept beside the file, not in it, so everyone who has the file open sees them at once. A downloaded file, and one opened in a new tab, carry them as the notes every PDF reader knows: highlights and the text a comment is about as highlights, drawings as ink, and comments with their replies as text notes.

The comments button at the top of the page shows the number of unresolved comments.

## Limits

- Highlighting and drawing are offered only to someone who may edit the file.
- Notes are not written into a password-protected PDF: the download is the file without them.

## Related

- [Comments](help:text/comments)
- [PDF files](help:pdf/viewer)
- [Redaction](help:pdf/redaction)
