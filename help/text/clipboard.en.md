# Clipboard

Cutting, copying and pasting in text, within Ponistra and between Ponistra and other programs.

## How to use it

1. Select the text.
2. Open the menu with a right click. The {t:commandGroup.clipboard} group holds {t:command.cut} ({k:Mod-x}), {t:command.copy} ({k:Mod-c}), {t:command.paste} ({k:Mod-v}) and {t:command.pasteText} ({k:Shift-Mod-v}).
3. {t:command.pasteText} pastes only the text, without formatting.
4. {t:command.blockLink} copies the address of the paragraph you stand in.

## How it works

What you copy carries both the formatting and the plain text, so other programs paste it as suits them. Tables travel as rows of cells, colours as they are on paper, lists as lists, and notes the way Word writes them: a number in the text and the note at the end of the copy. In plain text a note is a number in square brackets, with its text listed at the end.

Footnotes and endnotes pasted from Word or LibreOffice become notes again in their place in the text.

## Limits

- The menu's commands need the browser to allow access to the clipboard. When it does not, {t:command.failed} is reported with the advice to use the keyboard shortcuts, which work even then.
- {t:command.cut}, {t:command.paste} and {t:command.pasteText} are not available when you only read the document.

## Related

- [Links](help:text/links)
- [Notes](help:text/notes)
- [Shortcuts](help:text/shortcuts)
