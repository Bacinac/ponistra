# Files

The {t:rail.files} page gathers every source of files you reach in one tree: My documents, Company, Shared, Favourites and Boards in Ponistra, the locations on the network and, for its owner, the projects of the workspace, in one or two panes and in tabs.

## How to use it

### Opening a source

1. On the module bar, press {t:rail.files}.
2. With no folder open, the page shows every source by group: {t:files.bookmarks}, {t:rail.documents} ({t:tree.root}, {t:tree.company}, {t:tree.shared}, {t:favourites.title}, {t:boards.title}), {t:locations.title}, {t:files.computers} ([guests of computers](help:files/guests)) and {t:files.workspace}. Press a source.
3. In the left column, the arrow ({t:frame.expand}) beside a source opens its folders, beside a folder its subfolders, and pressing it again ({t:frame.collapse}) hides them. Pressing a name opens the folder in the pane; the row of the open folder is marked.
4. On a phone, the {t:frame.folders} button opens the tree.

While there is no network location, {t:locations.title} reads {t:locations.none} with the link {t:locations.settings}.

### Address bar

1. Above the list stands the path from the source's top to the open folder; each part goes back to its folder.
2. On a network location and in the workspace, pressing the empty part of the bar, or {t:files.typePath} from the keyboard, turns the path into the {t:files.address} field. Type a path from the source's top and press {k:Enter}; {k:Escape} cancels.
3. {t:files.refresh} reads the folder again.

### List and grid

1. {t:files.grid} at the top of the page shows the items as tiles with thumbnails of pictures and PDFs; {t:files.list} returns to the list with columns.
2. In the list, a column's heading sorts by it, pressing it again reverses the order.
3. {t:files.hidden} shows or hides items whose name starts with a dot and those a folder on the network marks hidden or system.
4. With {t:preview.title} on a wide screen, and always in the grid, the first press shows an item and a double press opens it.

### Two panes and tabs

1. {t:files.twin} at the top of the page splits the space into two panes; the second starts in the same folder. Pressing it again keeps only the pane you work in.
2. The pane you work in is framed; the page's address and the tree follow it. Pressing into the other pane moves the work there.
3. {t:files.newTab} opens a new tab with the open folder. Pressing a tab brings back its panes, and {t:files.closeTab} closes it.

### Searching by name

1. In the {t:files.search} field beside the address bar, type part of a name.
2. Below appears {t:files.found} with the count and the items below the open folder, each with its folder. Pressing an item opens it, pressing a folder enters it.
3. When the search stopped before the end, the count reads {t:files.partial}.

The field stands only beside sources that search by name.

### Copy, cut and paste

1. Choose items: press with Ctrl, long press, or the first press with the preview on.
2. {k:Mod-c} or {t:files.copy} in an item's menu keeps them for copying; {k:Mod-x} or {t:files.cut} for moving. Cut items stay faded until you paste them.
3. Open the destination folder, in the same source or any other, in the same pane or the other.
4. {k:Mod-v}, or {t:files.paste} in the menu of the list's empty part, pastes into the open folder. {t:files.pasteInto} in a folder's menu pastes into it.

Dragging works the same way: items dragged onto the empty part of a list or onto a folder in it go into that folder. Within one source dragging moves, with Ctrl or Alt it copies; between sources it always copies.

If the destination already holds items of the same names, Ponistra asks once, {t:files.conflict}, and shows them. {t:files.conflict.skip} leaves them alone, {t:files.conflict.replace} replaces them, and {t:files.conflict.keep} keeps both, adding a number to the copy's name (plan (2).docx). The choice holds for everything transferred, in subfolders too.

Between sources the server transfers, not the browser, so a transfer goes on when you close the page. Below the panes, under {t:transfers.title}, each transfer shows {t:transfers.copy} or {t:transfers.move}, the number of items, the source and the destination, a progress bar, how many files of how many have been transferred and the size transferred, and, when the choice was to skip, how many were skipped. {t:tree.cancel} stops a transfer: {t:transfers.cancelled} An ended transfer stays in the list until {t:transfers.dismiss} removes it.

### Properties

1. In an item's menu, press {t:files.properties}.
2. The window shows {t:files.where}, for a symbolic link {t:files.link} and where it leads, the size, the date changed, {t:files.owner}, {t:files.mode} and, on a shared folder, {t:files.attributes}.
3. For a folder, {t:files.folderSize} adds up all it holds; while it runs it reads {t:files.counting} then the size and the number of files and folders.
4. For a file, {t:files.checksum} computes its SHA-256 as a job in the background, {t:job.checksum}; while it runs it reads {t:files.summing}
5. Where the source allows, the boxes for {t:files.mode.owner}, {t:files.mode.group} and {t:files.mode.others} under {t:files.mode.read}, {t:files.mode.write} and {t:files.mode.run} change the permissions; {t:tree.save} writes them. UID and GID with {t:files.changeOwner} change the owner and group.

### Bookmarks

1. In a folder's menu, or the menu of the list's empty part for the open folder, press {t:files.bookmark}.
2. The bookmark appears under {t:files.bookmarks} in the tree and at the start of the page, and leads straight to that folder.
3. A right or long press on a bookmark in the tree offers {t:files.unbookmark}

### Other actions

Folders are made, files uploaded, opened, edited, renamed, moved, deleted and downloaded as [files on the network](help:files/network) are. In My documents, Company and Shared a document opens in its editor and a file on its page, and the menus also offer what Ponistra does beside files ([Documents overview](help:documents/overview)): sharing, a copy of a document, extraction into a table, joining PDFs, favourites and working offline.

## How it works

Each source stays where it is: the page reads a source's folder when you open it, and a change someone makes in My documents, Company or Shared shows at once in your list too. The projects of the workspace are visible to its owner alone.

Moving within one source is a rename on the source itself. Moving between My documents, Company and Shared moves the document or folder itself: it keeps its sharing and history. Copying, and every move between two sources, is done by Ponistra's server as a job: it reads from one source and writes into the other, never through the browser, so it does not stop when you close the page. The queue of transfers below the panes shows the progress.

- A copy within Ponistra makes each item anew: a document with its tabs and versions, a file with the same content, a link with its address. You own the copy.
- From Ponistra to the network or the workspace a document is written in its Office format (DOCX, XLSX, PPTX, with macros if it had them), a PDF with its notes, and a link as a .url file. A move sends the original to {t:trash.title}.
- Into Ponistra a file comes in as on upload: it becomes a document where Ponistra imports that kind, with the date it was changed on the server. The same name means the same title without the extension, whatever the case.
- {t:files.conflict.replace} of a folder onto a folder of the same name merges them: the content goes into the folder already there.

Bookmarks belong to the account and show on every device you sign in on. Tabs, panes, the list or grid view and hidden files are kept in this browser only.

## Limits

- Where a source does not support something, it is not offered: search, folder size, checksum, permissions and owner exist only on sources that know them. A shared folder (SMB) has no Unix permissions or owner, but attributes.
- Permissions and owner are changed only by an account the server lets do so; otherwise the server's error shows.
- Nothing can be pasted into the top of Company or Shared, nor into a source you only read.
- An item cannot be copied or moved into itself or its subfolder.
- A folder a symbolic link leads to is not transferred but counted as skipped; special files (devices, pipes) are not transferred.
- Nothing from a folder that allows no downloads goes to the network or the workspace; instead it reads {t:error.confined} A copy within Ponistra may, where that folder still holds.
- Two panes exist only on a wide screen.
- The message {t:error.not_found} in a pane means the source no longer exists or is no longer available to you.

## Related

- [Files on the network](help:files/network)
- [Network locations](help:documents/locations)
- [Documents overview](help:documents/overview)
- [Projects](help:agents/projects)
