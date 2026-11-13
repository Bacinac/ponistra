# Notes

Footnotes and endnotes add to the text without interrupting it: a number stands in the text, and the note is listed under the tab's text.

## How to use it

### A new note

1. Stand after the word the note refers to.
2. In the {t:editor.insert} menu choose {t:command.footnote} or {t:command.endnote}.
3. Type the note's text. {t:command.noteBack} ({k:Escape}) takes you back to the text.

### Commands on a note

1. Stand in a note. The {t:commandGroup.note} menu appears on the toolbar.
2. {t:command.toFootnote} and {t:command.toEndnote} change the note's kind.
3. {t:command.notesRestart} and {t:command.notesContinue} decide the numbers of the notes in the tab.
4. {t:command.deleteNote} deletes the note and its number in the text.

## How it works

Footnotes are numbered 1, 2, 3, and endnotes i, ii, iii, each kind separately, in the order they are read. Under the tab's text the footnotes are listed first, then the endnotes. Screen readers announce each note as {t:note.foot} or {t:note.end} with its number.

The numbers carry on from the tabs before, except in a tab where you chose that they start from 1.

## Limits

- A note holds only text in one paragraph: content pasted into it becomes plain text.
- In the first tab the numbers always start from 1.

## Related

- [Inserting](help:text/insert)
- [Tabs](help:text/tabs)
- [Import report](help:documents/import)
