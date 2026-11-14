# Users

On the {t:users.title} page an administrator opens accounts, changes them, signs users out of devices, deactivates and deletes accounts, and exports a user's data.

## How to use it

### A new user

1. Open {t:admin.title} and choose {t:users.title}.
2. Press {t:users.new}.
3. Type the {t:users.firstName}, {t:users.lastName}, {t:auth.email} and {t:auth.password}.
4. If needed, tick {t:users.admin} and the user's groups, then press {t:tree.create}.

### Changing an account

1. In the user's row open the menu and choose {t:users.edit}.
2. Change the details; leave the {t:password.new} field empty to keep the password.
3. Press {t:tree.save}.

### Devices and deactivation

1. In the row's menu choose {t:devices.title} for the list of browsers the user is signed in to.
2. Press {t:devices.end} beside one browser or {t:devices.endAll}.
3. For an account that may no longer sign in choose {t:users.deactivate} and confirm in the dialog {t:users.deactivateTitle}
4. You bring a deactivated account back with {t:users.activate}.

### Exporting data

1. In the row's menu choose {t:users.export}.
2. Confirm that it is you, if Ponistra asks.
3. Wait while the file is prepared; the browser then saves it under the user's email address.

### Deleting a user

1. In the row's menu choose {t:users.erase}.
2. In the dialog {t:users.eraseTitle} under {t:users.heir} choose the user who takes over the documents and shared mailboxes.
3. Press {t:users.erase} and confirm that it is you, if Ponistra asks.

## How it works

The list shows the name, email address, groups and {t:users.lastLogin}, and beside the name the badges {t:users.admin} and {t:users.inactive}. A user who has never signed in shows {t:users.never}.

A deactivated user cannot sign in and is signed out of every device. Their documents stay on the account and come back when you activate it again.

Beside the name of a user who signs in at a provider or comes from a directory stands that source's name. A directory's user has their email address, name, password and active state changed only in the directory, so in the {t:users.edit} dialog those fields and {t:users.deactivate} are disabled, as are the groups that come from the source. See [Outside sign-in and directories](help:admin/sources).

A password an administrator sets for another user is their way back after a lost device. If the installation requires that user to have a passkey, their passkeys are deleted with it, and they add a new one at their next sign-in.

The export is one zip file with everything the installation holds about the user: the account's details, every record that names them as JSON by kind of data (mail, calendars, contacts, tasks, conversations, comments, devices, access to documents and more), every mail message as an .eml file, the photos of their contacts, their own background for meetings, and their documents as Ponistra files and their files as they are, by the folders they stand in. The list of parts is in the file manifest.json. Passwords, keys and tokens are not exported, nor are the installation's settings. The vault's contents are locked in the browser, so the user exports them from the vault themselves. The prepared file stays on the server for 1 hour.

Deleting is final. The account goes with everything that belongs to it alone: the copies of mail in Ponistra (the messages on the mail server stay), calendars, contacts, tasks, the personal vault, passkeys, app passwords and the sign-ins on every device. Messages in conversations and comments they wrote to others stay, without the author's name. Documents and folders they were the only owner of, those in the trash included, move into one folder at the top of the chosen user's documents, named after the deleted user; their notes, links and boards become plain folders there. Company folders they were the only owner of stay where they are, and the chosen user becomes their owner. So do the [shared mailboxes](help:mail/mailboxes) they were the only owner of: the mailbox stays as it is, and the chosen user becomes its owner. Whatever has another owner stays with that owner, and shares with others stay as they are. Names in proposed changes inside documents are part of the document's content and stay.

Adding, changing and erasing a user are written to the [journal](help:admin/journal), as is ending the sessions on their devices.

## Limits

- You cannot take administrator rights from your own account, deactivate it or delete it.
- Only another active user can take over the documents and mailboxes; otherwise you see: {t:error.invalid_heir}
- A user who is the only owner of a shared or company vault collection cannot be deleted until the collection has another owner, as its key is locked for its members alone: {t:error.collection_owner}
- A user on legal hold cannot be erased ({t:error.held}), nor can a user whose mail is still within its retention period ({t:error.retained}); see [Data retention](help:admin/retention).
- Only an administrator can export and delete.
- The email address must be unique in the installation.
- Opening, changing and deleting accounts and exporting data may ask you to confirm that it is you.

## Related

- [Groups](help:admin/groups)
- [Sign-in rules](help:admin/policy)
- [Outside sign-in and directories](help:admin/sources)
- [Vault recovery](help:admin/recovery)
