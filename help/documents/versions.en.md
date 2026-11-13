# Versions

Ponistra saves versions of a document by itself while you edit it, and you can save a named version of your own, look at each one and bring the document back to it.

## How to use it

### Looking at versions

1. In the document's header press the {t:version.list} button, or choose it in the document's menu.
2. In the side list press a version. It opens as it was, marked {t:version.readOnly}
3. You open a version's tabs as you open a document's.

### Saving and naming

1. In the list of versions press {t:version.save}, type a name and press {t:tree.save}.
2. To give an automatic version a name, open its menu with a right click or a long press and choose {t:version.name}. A named version's name you change with {t:tree.rename}.

### Restoring

1. Open the version, or open its menu in the list.
2. Press {t:version.restore} and confirm in the {t:version.restoreTitle} dialog.

### Comparing with a version

1. The {t:action.documentCompare} command opens a dialog where you pick the version under {t:compare.version}.
2. Press {t:compare.run}. The differences arrive in the document as suggested changes.

## How it works

An automatic version is made when edits pause for ten minutes, and at the latest an hour after the first unsaved edit. In the list it is called {t:version.automatic}, a named one carries its name, and a version made by restoring is called after the number of the version it was restored from. Under the name stand the version's number, its time and the names of those who edited it.

Named versions are kept for good. Of the automatic ones, all from the last day are kept, the latest of each day for the last thirty days, and the latest of each week before that.

Restoring first saves the current state as a new version, so you lose nothing. The document then gets its tabs as they were in the version: those that were missing come back, and those added later are removed. Open editing sessions are closed.

## Limits

- Saving, naming and restoring need the right to edit. With the right to read you can only look at versions.
- A version cannot be changed, only looked at or restored.
- While a document has no version at all, the list says so: the first is made by itself when edits pause.

## Related

- [Suggested changes](help:text/proposals)
- [Import report](help:documents/import)
- [Documents overview](help:documents/overview)
