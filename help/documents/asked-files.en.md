# Files asked for

The owner of a folder makes a link with which people without an account in the installation send them files into that folder, without seeing anything in it.

## How to use it

### Making the link

1. In the folder's menu or the header of the open folder press {t:access.share}.
2. In the {t:outside.title} section press {t:outside.make}.
3. Under {t:outside.kind} choose {t:outside.kind.upload}.
4. If you like, choose a date under {t:outside.until}.
5. Press {t:outside.make} or {t:tree.cancel}.
6. Beside the link press {t:outside.copy} and send it to those you ask for files.

{t:outside.end} beside the link stops taking files at once.

### Sending files

1. The person opens the link in a browser, without signing in. The folder's name stands at the top.
2. They type {t:outside.sender}.
3. Under {t:outside.files} they choose one or more files.
4. They press {t:outside.send}. While it sends, it says how many files of all have been sent.
5. The names of the files sent appear under {t:outside.delivered}. The person can send more at once.

## How it works

Each file arrives in the folder as yours, with its own name and the date it was last changed, and is read and searched like any other.

The file's [access log](help:documents/sharing) says {t:log.kind.uploaded} with the name the sender typed, and the folder's log records making the link as {t:log.uploadLinkMade}. Nobody checks the name; it is what the sender wrote. Whoever made the link gets a [notification](help:account/notifications) of each file that arrives, which opens the file itself.

The sender gets no access at all: they see neither the folder, nor what is in it already, nor the files they sent themselves.

## Limits

- A link for sending files exists only for a folder, and has no password and no choice of download.
- Only the folder's owner makes it, where the installation's policy lets them. Otherwise it says {t:error.links_not_allowed}
- A file larger than allowed is not sent: {t:error.too_large} When the server runs out of room: {t:error.no_room}
- A file lost between sending and saving says {t:error.unknown_file} Choose it again.
- A link that is no longer valid says {t:error.no_link} It is valid until the end of the chosen day, until the owner ends it, while the folder is out of the trash and until an administrator forbids sharing outside the installation.

## Related

- [A link outside the installation](help:documents/outside)
- [Sharing](help:documents/sharing)
- [Notifications](help:account/notifications)
- [Uploading files](help:documents/upload)
