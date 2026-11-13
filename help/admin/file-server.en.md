# A folder on a file server

You can connect a company folder to a folder on your network's file server, as a copy until you move it or as an inbox.

## How to use it

### Connecting

1. On the {t:users.title} page, in the menu of a company folder's row, choose {t:fileServer.connect}
2. In the dialog {t:fileServer.connectTitle} type the {t:fileServer.address}, {t:fileServer.username} and {t:fileServer.password}.
3. Choose {t:fileServer.mode.copy} or {t:fileServer.mode.inbox} and press {t:fileServer.connectAction}.

### A copy

1. After connecting, Ponistra reads the list, and beside the folder it says {t:fileServer.reading} and then {t:fileServer.read}.
2. Choose {t:fileServer.inventory} and in the dialog {t:fileServer.inventoryTitle} check the {t:fileServer.files}, {t:fileServer.folders}, {t:fileServer.size} and {t:fileServer.free}.
3. Press {t:fileServer.copy}. While it runs, it says {t:fileServer.copying} and how many files are copied.
4. When you want to work only in Ponistra, choose {t:fileServer.move} and confirm with {t:fileServer.moveAction} in the dialog {t:fileServer.moveTitle} While it runs, the folder shows {t:fileServer.moving}

### Upkeep

1. {t:fileServer.refresh} reads the server's changes at once.
2. {t:fileServer.signIn} opens {t:fileServer.signInTitle} for a new username and password.
3. {t:fileServer.disconnect} disconnects the folder, with {t:fileServer.disconnectAction} in the dialog {t:fileServer.disconnectTitle}

## How it works

In the mode {t:fileServer.mode.copy} the folder on the server stays the original, and the copy in Ponistra is only read. Ponistra reads it again every five minutes, and beside the folder it says {t:fileServer.ready} with the time of the last reading. Moving takes the last changes, after which the folder is edited only in Ponistra and the server is no longer followed.

In the mode {t:fileServer.mode.inbox} Ponistra moves arriving files into the company folder about every thirty seconds and deletes them from the server. Beside the folder it says {t:fileServer.taken} and the number of files taken.

The list from the server names under {t:fileServer.left} what will not be copied: {t:fileServer.why.link}, {t:fileServer.why.narrower}, {t:fileServer.why.too_large}, {t:fileServer.why.too_long} or {t:fileServer.why.unreadable}. Under {t:fileServer.kept} are files that cannot be imported as a document, each with its reason: {t:fileServer.kept.too_large}, {t:fileServer.kept.too_many_cells}, {t:fileServer.kept.too_many_formulas}, {t:fileServer.kept.unreadable} or {t:fileServer.kept.newer_file}.

Disconnecting a copy empties the company folder and deletes the copy from Ponistra, and the folder on the server stays as it is. A disconnected inbox no longer takes files, and those already taken stay.

## Limits

- Only company folders can be connected, not vault collections.
- Copying starts only if at least 1 GB stays free on the installation's disk beside the copy.
- Only a copy that is copying or copied can be moved.
- An inbox has no list and no moving.
- What a retention rule or a legal hold keeps stays in the copy even when it disappears from the server, and such a copy cannot be disconnected.

## Related

- [Company folders and collections](help:admin/company)
- [Data retention](help:admin/retention)
