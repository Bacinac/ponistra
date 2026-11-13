# Comparison with a file

Compares the tab with a Word file or another document and writes each difference as a proposed change, for example when a partner returns a contract without tracked changes.

## How to use it

1. Open the tab you are comparing.
2. Right-click to open the menu and choose {t:action.fileCompare.ask}
3. In the {t:action.fileCompare} dialog choose a document or a Word file from the folders, starting in the folder that holds the document.
4. For a file that is only on the computer, press {t:file.fromComputer} and choose it.
5. The differences appear in the tab as proposals. Accept or reject each one on its own, or all at once.

## How it works

The file is read as an import reads it, but no new document is made of it. A file chosen from the computer is saved as it is in the folder that holds the document, so it stays beside it. DOCX, DOCM, DOTX, DOTM, ODT, DOC and RTF files and Ponistra's text documents can be compared; of another document the tab with the same name is taken, or its first tab where there is none.

The differences are found by code, without artificial intelligence, so the text does not leave the installation. The text of paragraphs, headings and tables is compared; spaces and empty paragraphs do not count as a difference. A paragraph whose words changed becomes one proposal in which only the words that differ are deleted and inserted. A paragraph the file lacks is proposed for deletion. Paragraphs only the file has are proposed for insertion where they stand in the file, each run of them as one proposal, with the file's paragraph kind, list and bold, italic, underlined or struck-through text, and this document's look. A table that differs is proposed for deletion, and the file's table for insertion after it.

The author of every proposal is the file's name, and the date is the time of the comparison. A comparison can be undone like other actions.

## Limits

- Anyone who may edit the document and read the file can run a comparison.
- Images, charts and PDFs in the tab are not compared, and a moved paragraph shows as a deletion where it was and an insertion where it now is.
- If the tab already has proposals, {t:error.proposed} is shown.
- If the texts are the same, {t:error.same_as_file} is shown.
- If the file is neither a text document nor a Word file, {t:error.not_comparable} is shown.
- If the file is damaged, {t:error.unreadable} is shown.

## Related

- [Suggested changes](help:text/proposals)
- [Writing with Claude](help:ai/writing)
- [Versions](help:documents/versions)
