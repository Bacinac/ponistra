# The search box

The box in the header of every page searches through documents, mail, events, tasks, people, the vault and the help, and offers the application's commands and places.

## How to use it

![The search box with commands and the first hits](shot:start-search)

### Searching

1. Press the {t:search.placeholder} box in the header or press {k:Alt-/}. The {k:Mod-k} shortcut works wherever the page does not use it for something else. On a phone the box is a magnifier icon that widens when pressed.
2. Type at least two characters. Below the box commands and the first hits appear, in groups: {t:search.documents}, {t:search.mail}, {t:search.conversations}, {t:search.events}, {t:search.tasks}, {t:search.people}, {t:search.vault}, {t:search.versions} and {t:search.help}.
3. With {k:ArrowDown} and {k:ArrowUp} choose a hit or a command and press {k:Enter}, or press it with the mouse.
4. For all hits press {t:search.all}. {k:Enter} does the same when nothing is chosen.
5. When you are in a folder of documents, the {t:search.in} button with the folder's name searches in it alone.
6. {k:Escape} closes the list.

### Commands and places

1. Type part of the name of what you want: a module, a place, a setting, a theme or a language.
2. Choose {t:places.open} with the place's name, for example {t:rail.contacts}, {t:tasks.title} or {t:settings.title}.
3. Make something new with {t:notes.new}, {t:mail.compose} or {t:tree.newDocument}.
4. Change the theme and language with the commands starting with {t:frame.theme} and {t:frame.language}, and sign out with {t:auth.signOut}.

## How it works

Each group is ordered by how well a hit matches the words. The box shows at most 8 hits, shared among the groups as evenly as possible, and at most 5 commands. The commands of the page you are on, for example a document's commands with their shortcuts, come before the general ones. Titles are found even when a word in them is spelt a little differently.

Beside a hit in a document it says where in it the hit is: {t:search.tab}, {t:search.section}, {t:search.paragraph}, {t:search.table}, {t:search.cell}, {t:search.image}, {t:search.chart}, {t:search.pdf}, {t:search.page}, {t:search.footnote}, {t:search.endnote}, {t:search.comment}, {t:search.data} or {t:kind.link}. A hit in a message's attachment is marked {t:search.attachment} with the file's name. Mail takes in the shared mailboxes you read too; a message from a mailbox carries its name before the sender and opens in that mailbox. A person is marked {t:search.person.contact}, {t:search.person.colleague} or {t:search.person.directory}, and a task {t:tasks.done} or by its due date ({t:tasks.due}).

The vault is searched in your browser while it is unlocked, so the server never sees what you look for in it. While it is locked, below the hits it says: {t:search.vaultLocked} Hits in the vault are marked {t:vault.mine} or with the collection's name, and {t:vault.unlock} opens the vault. Help articles show only while the search has no filters. Earlier versions of documents are searched only when you ask for them by the kind filter, and a hit in a version carries {t:version.number} with its number, with {t:version.automatic} or {t:version.restoredFrom}.

On a new page the box is empty, unless you typed into it while the page was loading.

## Limits

- With fewer than two characters it says: {t:search.hint}
- When nothing matches, it says {t:search.none} and what you typed.
- Mail in the {t:mail.role.junk} and {t:mail.role.trash} folders is searched only when you ask for it by the folder filter.
- The page of search results has no box in the header, as it has its own.
- Without the network the box is disabled and reads {t:offline.needed} ([Working offline](help:account/offline)).

## Related

- [Search results and filters](help:start/results)
- [Searching by a sentence](help:start/sentence)
- [The application frame](help:start/overview)
