# Folders and moving in the vault

Folders arrange the items within a collection, and moving puts an item in another folder or another collection.

## How to use it

### Folders

1. In an open collection choose {t:create.folder} in the menu of other actions, type a name and press {t:tree.create}. The new folder is made in the folder that is open.
2. Open a folder in the left column, below its collection.
3. For the open folder choose {t:vault.renameFolder} or {t:vault.deleteFolder} in the menu of other actions.
4. Confirm deleting in the dialog {t:vault.deleteFolderTitle}

### Moving an item

1. In an open item choose {t:tree.move} in the menu of actions.
2. Under {t:vault.moveTo} choose a collection or a folder in it.
3. Press {t:tree.moveHere}.

### Several items at once

1. Long-press an item in the list. After that, pressing another item adds it to the choice or takes it out, and with {k:Shift} a whole range.
2. {k:Mod-a} chooses all items in the list, and {k:Escape} clears the choice.
3. Above the list press {t:tree.move} or {t:tree.toTrash}. A right click on an item offers the same.

## How it works

Folder names are encrypted like the items. A folder may hold other folders. A deleted folder goes together with the folders in it, and its items stay in the collection, outside folders.

An item moved to another collection becomes visible to that collection's members and leaves the previous one. Meanwhile the item's key is locked in the browser with the new collection's key.

## Limits

- Folders and moving need the right to edit in the collection, and moving to another collection also in that one.
- While a search is typed, the list shows items from all folders, with the path to their folder, and the folders are not shown.

## Related

- [Sorting into folders](help:vault/sorting)
- [Vault items](help:vault/items)
- [The vault's trash](help:vault/trash)
