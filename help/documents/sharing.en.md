# Sharing

The owner of a document or folder decides who besides them may read, edit or own it, and for folders also whether the documents in them may be downloaded.

## How to use it

### Giving access

1. In the item's menu, or in the header of an open document, press {t:access.share}.
2. Under {t:access.who} choose {t:access.everyone}, a person from the {t:access.people} group or a group from {t:access.groups}.
3. Under {t:access.role} choose {t:access.role.read}, {t:access.role.edit} or {t:access.role.own} and press {t:access.add}.

### Changing and removing

1. In the {t:access.here} list, change the role in the menu beside the person.
2. With the cross, {t:access.remove}, take the access away.
3. Under {t:access.filter} choose a person to see only the access that concerns them. {t:access.anyone} brings back the whole list.

### A folder without downloads

1. Open {t:access.share} for the folder.
2. Tick {t:confined.label}.

### Access log

1. In the panel press {t:log.title}.
2. The table has the columns {t:log.when}, {t:log.who} and {t:log.what}, newest first.

## How it works

Access is inherited: what you get for a folder holds for everything in it. Beside each access it says where it comes from: {t:access.direct}, {t:access.fromAbove} or {t:access.from} with a link to the folder. Inheritance only adds rights, so access that comes from a folder is changed or removed on that folder. Under {t:access.below} stand the items in the folder that have rights of their own, each with its path. In the document list such items carry the mark {t:access.wider}.

{t:access.role.read} allows opening and commenting, {t:access.role.edit} changes as well, and {t:access.role.own} also sharing and deleting for good. An item at the top must keep at least one owner.

In a {t:confined.label} folder, those who are not owners read and edit the documents only in Ponistra: they do not download, export or print them, nor copy them out of the folder. Such actions are disabled, with the note {t:confined.hint}

People outside the installation stand in the list as {t:access.outside} beside their address, with the role {t:access.role.read} or {t:access.role.edit}, and with the {t:outside.download} box beside the person the owner allows or withholds downloading. They are added in the {t:outside.title} section of the same panel, as [Sharing with someone outside](help:documents/outside-people) describes, or by a message ([Documents in mail as links](help:mail/shared-links)).

The log records {t:log.kind.opened}, {t:log.openedThroughLink}, {t:log.kind.downloaded} with the file's format, {t:log.kind.shared} and {t:log.unshared}, {t:log.linkMade}, {t:log.uploadLinkMade} and {t:log.linkEnded}, and {t:log.kind.uploaded} with the name the sender typed. The same person opening the same item is recorded once an hour. For a folder the log covers the items in it too. A person whose account was deleted shows as {t:log.formerUser}, a visitor through a link to read as {t:log.outsider}, and someone outside who came in under their name or address by that name or address.

## Limits

- Only owners give, change and remove access, and only access given directly.
- The administrator lays out the rights of company folders, so access is not given in them from this panel.
- Only owners see the log, and it shows at most the 200 newest entries.

## Related

- [Shared](help:documents/shared)
- [A link outside the installation](help:documents/outside)
- [Sharing with someone outside](help:documents/outside-people)
- [Files asked for](help:documents/asked-files)
- [Company folders](help:documents/company)
- [Documents overview](help:documents/overview)
