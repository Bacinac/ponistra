# Search results and filters

The {t:search.title} page shows all hits in groups and narrows them by filters of kind, person, account, folder, date and attachment.

## How to use it

### The results page

1. In the search box press {t:search.all} or {k:Enter}.
2. Change the words in the field at the top of the page and press {t:search.label}.
3. The hits are sorted into the groups {t:search.documents}, {t:search.mail}, {t:search.conversations}, {t:search.events}, {t:search.tasks}, {t:search.people}, {t:search.vault}, {t:search.versions} and {t:search.help}. Press a hit to open it. A message from a shared mailbox opens in that mailbox.
4. If you searched in one folder, {t:search.in} with the folder's name stands above the hits. The cross beside it ({t:search.everywhere}) searches everywhere.

### Adding a filter

1. Press {t:search.filter.add}.
2. Under {t:search.kind} choose {t:search.kind.document}, {t:search.kind.file}, {t:search.kind.link}, {t:search.kind.folder}, {t:search.kind.mail}, {t:search.kind.event}, {t:search.kind.task}, {t:search.kind.person}, {t:search.kind.vault} or {t:search.kind.version}.
3. Under {t:search.filter.date} choose {t:search.last.week}, {t:search.last.month} or {t:search.last.year}.
4. {t:search.filter.has} leaves only mail with an attachment.
5. A filter shows as a tag above the hits. The cross on the tag ({t:search.filter.remove}) removes it.
6. On a date tag press its name to search documents by the date of change instead of creation ({t:search.filter.toChanged}) and back ({t:search.filter.toMade}).

### Typing a filter

1. Type a filter among the words in the box or in the field at the top, as a name, a colon and a value with no space.
2. {t:search.token.kind}:{t:search.value.document} looks for one kind, and the value may be the start of a word where only one kind begins so.
3. {t:search.token.from}:name looks for a message's sender, a document's author, and an event's organiser or one invited.
4. {t:search.token.account}:word looks for the mail of an account whose address or name holds that word.
5. {t:search.token.folder}:name looks in the folder of that name. The words inbox, drafts, sent, archive, junk, spam and trash look in that mail folder of all accounts.
6. {t:search.token.date}:period looks by the date of creation, and {t:search.token.changed}:period by the date of change. A period is a year (2025), a month (2025-02 or 2.2025.), a day (2025-02-03 or 3.2.2025.), {t:search.value.week}, {t:search.value.month} or {t:search.value.year} (the last 7, 30 or 365 days), or a range with two dots (2025-01..2025-03), open at either end.
7. {t:search.token.has} looks for mail with an attachment.
8. Put a value with a space in quotes: {t:search.token.from}:"Ana Kovač".

## How it works

The tag of a filter says what it narrows: {t:search.kind}, {t:search.filter.from}, {t:search.filter.account}, {t:search.filter.folder}, {t:search.filter.date} or {t:search.filter.changed}, and a period as a range of days or with {t:search.filter.since} and {t:search.filter.until}. The names of filters and their values are recognised in Croatian and in English, whatever the interface's language, and letters with and without diacritics count as the same.

A filter leaves only the groups that can meet it. An account, an attachment and a mail folder leave only mail. A folder leaves documents and mail. For an event the period is when it takes place, for a task its due date; people have no date, so a period filter leaves them out. Earlier versions of documents show only with {t:search.token.kind}:{t:search.value.version}. A filter with no words shows everything that meets it.

Each group shows at most 50 hits. Beside a document stand the date of its last change and, when there are several, {t:search.hits} with the number of hits in it. Beside a message stands {t:search.hits}, beside a recurring event {t:search.occurrences}, as the whole series is one hit, and beside a document among the versions {t:search.versionHits} with the number of versions that hold the words.

A search in a folder looks only at the documents in it and its subfolders.

The group {t:search.conversations} can also be asked for by the kind filter {t:search.value.conversation}, shown in the box as {t:search.kind.conversation}.

## Limits

- When a group is full, below it it says: {t:search.limited}
- A filter with no value says: {t:search.error.empty}
- An unknown kind says: {t:search.error.invalid_kind} The other kinds in the list above count too.
- A date that cannot be read says: {t:search.error.invalid_date}
- A wrong value of the attachment filter says: {t:search.error.invalid_has}
- While a filter is wrong, the search shows nothing. Correct it or remove it.

## Related

- [The search box](help:start/search)
- [Searching by a sentence](help:start/sentence)
