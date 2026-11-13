# Trash

Items you put in the trash stay there until you restore them or delete them for good, together with everything they hold.

## How to use it

### Putting in the trash

1. In the item's menu choose {t:tree.toTrash}, or choose items and press {k:Delete}.
2. You can also drag an item onto {t:trash.title} in the left column.

### Restoring and deleting for good

1. In the left column of the {t:rail.documents} module press {t:trash.title}.
2. Beside an item press {t:trash.restore} to put it back in its place. A right click on the row offers the same.
3. Press {t:trash.purge} and confirm in the {t:trash.purgeTitle} dialog.
4. For several items at once, tick them and start the action on the bar above the list.

## How it works

The trash shows the items you may edit, the latest trashed first, with the date they were trashed. A folder in the trash carries everything it holds, so that is restored and deleted together with it.

A restored item returns to the folder it was trashed from. If that folder is itself in the trash or no longer exists, the item returns to the top level and keeps its owners.

The trash does not empty itself: items stay in it until someone restores them or deletes them for good. An empty trash shows: {t:trash.empty}

## Limits

- Only someone who may edit an item trashes it and restores it.
- Only the item's owner deletes it for good. Deleting for good cannot be undone.
- An item with a lock beside it cannot be deleted for good: {t:retention.kept.held} means it or something in it is on legal hold, and {t:retention.kept.retained} that it is within a retention period an administrator set.
- You cannot trash a company folder.

## Related

- [Working with items](help:documents/organising)
- [Versions](help:documents/versions)
- [Sharing](help:documents/sharing)
