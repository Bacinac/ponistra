# Files on the network

The network locations in {t:rail.files} open folders on the organisation's servers, shared folders (SMB) and SSH servers (SFTP), and their files are worked on where they are, without copying them into Ponistra.

## How to use it

### Opening a location

1. On the module bar, press {t:rail.files}.
2. In the left column, open {t:locations.title}; below it are the locations you added and those shared with you. The same list stands on the {t:rail.files} page while no folder is open.
3. Press a location, and a folder by pressing its row; the [address bar](help:files/manager) leads back.
4. {t:files.refresh} reads the folder from the server again.

### Opening and editing a file

1. Press a file. A text file opens in the editor in place of the list, and a PDF, a picture, sound and video in a new browser tab. An archive (ZIP, 7z, RAR, TAR and others), an email message (EML, MSG), contacts (VCF), a calendar (ICS) and a picture the browser does not show (BMP, ICO, TIFF, PSD) open in place of the list with what they hold, as in Documents, beside {t:file.download}.
2. After changing the text press {t:workspace.files.save} or {k:Mod-s}. Beside the name it says {t:workspace.files.unsaved} until the changes are saved, and then {t:workspace.files.saved}
3. {t:workspace.files.back} returns to the folder. If changes are not saved, it asks {t:workspace.files.discard}
4. Other files offer only {t:file.download}.

With {t:preview.title} on and a wide screen, the first press shows the item in the panel at the side, and a double press opens it. The panel also shows what an archive, a message, contacts, a calendar and such a picture hold, and Markdown formatted.

### New items

1. Press {t:create.new}.
2. {t:create.folder} makes a folder in the one that is open.
3. {t:create.upload} sends files from the device into the open folder, and {t:create.uploadFolder} a whole folder with all it holds. Dragging files or folders onto the list does the same.

### Actions on items

The menu opens with a right press or a long press on a row. Several items are selected with a long press or a press with Ctrl, and the actions are then in the bar above the list.

- {t:tree.open} opens the item.
- {t:file.download} downloads a file to the device.
- {t:zip.download} downloads the folders and files chosen as one ZIP file, a folder with everything in it. A right or long press on an empty part of the list offers {t:zip.folder} for the folder that is open.
- {t:tree.rename} changes the name of one item.
- {t:tree.move} opens the location's folders; press {t:tree.moveHere} in the destination.
- {t:files.delete} deletes what is selected from the server, after asking {t:files.deleteHeading}
- {t:files.copy}, {t:files.cut} and {t:files.paste} transfer items into Ponistra, to another location or into the workspace ([Files](help:files/manager)).

## How it works

Ponistra signs in to the server with the account entered in the location, so on it you may do what that account may, not your own. The files stay on the server: Ponistra does not index them, search them or keep their versions, and reads a folder's list each time you open it.

The folder tree reads a location's folders only once you open its branch, and only folders, not files. The tree and the list on the right share one reading, so a new, renamed or deleted folder shows in the tree at once. A location whose server cannot be reached shows the error below its branch, and the other locations go on working.

Saving text checks that the file on the server is the same as when you opened it. If someone changed it in the meantime, it says {t:workspace.files.changed} and you choose {t:workspace.files.reload} or {t:workspace.files.overwrite}.

Copying into Ponistra runs in the background as the job {t:job.copy}: files Ponistra can read (Word, Excel, PowerPoint, PDF, text) become documents, the others files, and a folder is copied with everything in it. The copy has no tie to the original afterwards.

A ZIP is put together as it is sent: Ponistra reads one file after another from the server and passes it on at once, so the download starts at once and nothing is stored in Ponistra. Links and special files on the server do not go into the ZIP. Ponistra reads what a file holds from a temporary copy it deletes as soon as it has read it; the file on the server stays as it was.

Deleting on the server is permanent: Ponistra's trash does not keep it. A folder is deleted with everything in it.

The first change on a location may ask you to [confirm that it is you](help:account/confirm).

## Limits

- Whoever only reads a location has {t:create.new}, {t:tree.rename}, {t:tree.move} and {t:files.delete} disabled.
- The editor opens text up to 1 MB; for a larger one it says {t:workspace.files.large} A file that is not text reports {t:workspace.files.binary}
- One copy carries at most 1,000 items, and one ZIP at most 1,000 chosen items (a folder with everything in it is one item).
- What a file holds is shown for files up to 512 MB; for a larger one it says {t:error.too_large}
- Links on the server that lead out of the location's folder do not open.
- {t:error.location_unreachable} and {t:error.location_closed} mean the server does not answer; try again or check the network to it.
- {t:error.location_login} and {t:error.location_secret_lost} are solved by the location's owner entering the sign-in again in the [settings](help:documents/locations).
- {t:error.location_host_key_changed} The owner does so only after checking that the server really is the right one.
- {t:error.location_denied} means the location's account has no such right on the server.
- The messages {t:error.file_exists} {t:error.file_missing} {t:error.file_busy} describe the state on the server; refresh the list.

## Related

- [Network locations](help:documents/locations)
- [Organising documents](help:documents/organising)
- [Uploading files](help:documents/upload)
