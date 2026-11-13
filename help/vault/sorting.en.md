# Sorting into folders

Claude proposes folders for the collection's items that are not in any folder yet, and you edit the proposal and apply it.

## How to use it

1. Open the collection and choose {t:vault.sort} in the menu of other actions.
2. The dialog {t:vault.sortHeading} shows what is sent and the {t:vault.sortCount}. Press {t:vault.sortDo}. Meanwhile it says: {t:vault.sorting}
3. In the proposal change each folder's {t:vault.sortName} if you wish.
4. Press {t:vault.sortItems} beside a folder to see its items, and move any of them to another folder or to {t:vault.sortNone}.
5. Press {t:vault.sortApply}.

## How it works

Only the name of each item outside folders and the domain of its first address, and the names of the existing folders at the top of the collection, are sent to Anthropic in the USA. Usernames, passwords, one-time codes, notes and attachments do not leave. The proposal comes back to the browser, which encrypts the new folders and moves the items into them only once it is applied. The server keeps not the proposal but only a record of the run, as for other actions of artificial intelligence.

Folders of the same name are merged, also with an existing folder of that name. Items under {t:vault.sortNone} stay outside folders.

In the list of artificial intelligence's use this action stands as {t:action.vaultSort}.

## Limits

- The action is not available when artificial intelligence is not turned on for the installation; then beside it it says: {t:ai.off}
- When all items are already in folders, beside it it says: {t:vault.sortNothing}
- It needs the right to edit in the collection.
- When Claude returns no proposal, it says: {t:vault.sortNoAnswer}

## Related

- [Folders and moving](help:vault/folders)
- [Actions of artificial intelligence](help:ai/actions)
