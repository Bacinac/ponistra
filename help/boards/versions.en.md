# Board versions

Each time an agent writes a board again, the page before stays as a version you can look at and restore.

## How to use it

### Looking at a version

1. On an open board press {t:version.list}.
2. Press a version in the list. The board shows that version's page; the newest stands at the top marked {t:board.current}.

### Restoring a version

1. A right click or long press on a version opens {t:version.restore}.
2. In the dialog {t:board.restoreTitle} confirm with {t:version.restore}. {t:board.restoreWarning}

## How it works

Beside each version stand its number, its date, who wrote it and through which agent. A restored version becomes a new version named {t:version.restoredFrom} with the number of the one it was restored from.

A version keeps only the board's page; the data the board keeps does not go back with it.

## Limits

- Only someone who may edit the board can restore a version; the current version is not restored.
- While the board has no other versions, it says: {t:board.versionsEmpty}

## Related

- [Boards](help:boards/overview)
