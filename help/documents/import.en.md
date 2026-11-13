# Import report

A document imported from an Office or LibreOffice file keeps the original file and reports what the import did not carry, and you can import the file again or add one to an existing document.

## How to use it

### The report

1. Open the imported document. Above its content stands the {t:import.report} box, saying whether everything was carried.
2. If it was not, press {t:import.details} for a list of what is missing.
3. Once you have looked through the report, press {t:import.dismiss} (the cross in the box).

### The original file

1. In the report's box or in the document's menu, press {t:import.original} for the file as it was uploaded.
2. Press {t:import.again} when you want the document read from the original file anew, then confirm the question {t:import.againTitle}

### Importing into an existing document

1. In the document's menu, behind the title in the path, choose {t:import.into}
2. Pick a file on your computer. While the import runs, {t:import.importing} stands above the document.
3. When the import ends, the {t:import.report} dialog says whether everything was carried, and if not, lists what is missing.

## How it works

The report's details fall into groups. Under {t:import.lost} stands what Ponistra does not show or shows differently, for example charts of an unsupported kind, conditional formatting, macros, hidden text or transitions between slides, with the number of occurrences when there are several. For cells whose calculated value differs from the original, their addresses are listed. Under {t:import.fonts} it says which font was replaced by which, or {t:import.fontDefault} when the document's font took over. Then follow the names of functions that are not calculated, the macros' source code, read-only, and the number of tracked changes accepted ({t:import.accepted}).

Only those who may edit the document see the report. When one of them closes it, it is gone for everyone.

Importing again first saves the current state as a version, then replaces the tabs' content with what the import now reads from the original file. Comments from the file are read anew, and comments added in Ponistra stay. Open editing sessions are closed, so other users open them again.

Importing into an existing document adds the file's tabs after the document's last tab. Styles and list formats the document already has keep their look, and a table named like one in the document is given a copy's name.

## Limits

- {t:import.again} and {t:import.into} are available only with the right to edit.
- {t:import.original} is not available in a document inside a {t:confined.label} folder.
- Macros never run; their code is only shown.

## Related

- [Uploading files](help:documents/upload)
- [Versions](help:documents/versions)
- [Saving in another format](help:text/export)
