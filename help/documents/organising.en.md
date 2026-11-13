# Working with items

You open, rename, copy, move and put items of a folder in the trash, one at a time or several at once.

## How to use it

### Actions on one item

1. Right-click an item in the list, or press the button with three dots at the end of its row. A folder in the tree of the left column offers {t:tree.rename} and {t:tree.toTrash} on a right click or a long press.
2. Choose {t:tree.open}, {t:tree.rename}, {t:tree.move} or {t:tree.toTrash}.
3. For a document choose {t:copy.make}. Type the copy's name and press {t:tree.create}.
4. For a file choose {t:file.download}.
5. {t:access.share} opens the panel of the item's rights.

### Choosing several items

1. Long-press an item or press it with {k:Mod}. On a computer you can stand on the row and press {k:Space}.
2. After that a tap or a click adds an item to the choice or takes it out. Hold {k:Shift} for a range. A double click still opens the item.
3. Press {k:Mod-a} or the checkbox on the choice bar for every item in the folder. The bar's menu has {t:explorer.selectAll}, {t:explorer.invert} and {t:explorer.clear}.
4. On the choice bar choose {t:tree.move} or {t:tree.toTrash}. The other actions are under the three dots.
5. Press {k:Escape} to give up the choice, and {k:Delete} to move what is chosen to the trash.

### Moving

1. Choose {t:tree.move}. The {t:tree.moveTitle} box opens.
2. At the top of the box choose {t:tree.root}, {t:tree.company} or {t:tree.shared}, then go into a folder by pressing it.
3. Press {t:tree.moveHere} or {t:tree.cancel}.
4. You can also drag an item with the mouse onto a folder in the list, a folder in the left column, a step of the path, or {t:trash.title}.

## How it works

A document's copy is made beside the original, and its name starts with "Copy of". If you may not add to the original's folder, the copy is made in {t:tree.root}. While a long copy is being made, the lower right corner shows {t:job.copy}.

An item moved into a folder takes that folder's rights and keeps the rights it had of its own. Everyone with access sees moving and deleting at once. When you drag several items at once, all those chosen move. A file dragged from the list onto the desktop is saved by the browser as a file.

An item in the trash is not deleted at once: it comes back from the [trash](help:documents/trash). The moving box does not offer the folder you are moving. When a folder has no subfolders, it says: {t:tree.noSubfolders}

## Limits

- Renaming, moving and putting in the trash need the right to edit. Only the administrator changes the company's folders.
- Into {t:tree.root} you can move only items you own.
- An item cannot be moved out of a folder {t:confined.label}, downloaded or copied outside it. The action is then disabled with the note {t:confined.hint}.
- {t:copy.make} exists only for documents, not for folders and files.
- Without the network renaming, moving and moving to the trash are disabled ([Working offline](help:account/offline)).

## Related

- [Documents overview](help:documents/overview)
- [Trash](help:documents/trash)
- [Sharing](help:documents/sharing)
