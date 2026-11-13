# The application frame

Every page of Ponistra has the same frame: the bar of modules, the header with the search and the account menu, and the left column beside the content.

## How to use it

![The frame with the bar of modules, the header and the column](shot:start-frame)

### Modules

1. On the bar of modules ({t:rail.label}) choose {t:rail.today}, {t:rail.calendar}, {t:rail.mail}, {t:rail.chat} or {t:rail.documents}. On a wide screen the bar is along the left edge, on a phone along the bottom.
2. The Ponistra logo at the top of the bar leads to {t:rail.today}.
3. A page that belongs to a module, as {t:rail.contacts} belongs to {t:rail.chat}, has the module's name before its title in the header, which takes you back to it.
4. If you own a code workspace, the bar also holds {t:rail.projects}, [a page of projects and chats](help:agents/projects).

### The left column

1. The left column holds what belongs to the page: the folders of documents, the calendars, the list of conversations or the contents of the help.
2. Beside the documents the column offers {t:favourites.title}, {t:tree.root}, {t:tree.shared}, {t:notes.title}, {t:links.title}, {t:boards.title}, {t:vault.title} and {t:trash.title}. {t:tree.company} shows when the company has shared folders.
3. Open a folder with subfolders by the arrow before its name ({t:frame.expand}), and close it by the same arrow ({t:frame.collapse}).
4. Change the column's width by dragging its right edge ({t:frame.width}). A double click on the edge brings back the default width.
5. With the edge chosen by {k:Tab}, the {k:ArrowLeft} and {k:ArrowRight} keys change the width, and {k:Home} and {k:End} give the narrowest and the widest.
6. On a phone, and on pages that hold something of their own in the column, the {t:frame.folders} button in the header opens the folders of documents.

### The account menu

1. Press the circle with your initials in the right corner of the header ({t:frame.account}).
2. Under {t:frame.language} and {t:frame.theme} choose the language and look of the interface.
3. {t:settings.title} opens the settings of your account, and {t:auth.signOut} signs you out.
4. {t:about.title} opens the facts about the application.

### Help

The question mark in the header ({t:help.title}), like {k:F1}, opens the article about the page you are on.

### Shortcuts

- {k:Alt-/} or {k:Mod-k} puts the cursor into the search box.
- {k:Alt-m} turns on the microphone for spoken commands.
- {k:Alt-n} opens a new note.
- {k:F1} opens the help about the page you are on.

## How it works

The frame stays in place while pages change, so what you typed into the search box stays while the new page loads. A page refreshes by itself as soon as its data changes, whether you changed it on another device or on the phone or a sync brought it, so it never needs reloading.

The number beside {t:rail.mail} shows the unread messages in the inboxes of your accounts, and the number beside {t:rail.chat} the others' messages in conversations you have not read yet; in channels only mentions and replies in threads you follow are counted.

At the foot of the bar of modules the next event of today shows: {t:today.next}, its start time and how long until it, or {t:today.now} once it has begun. Pressing it opens that day in the calendar, and if the event has an online meeting, a {t:meeting.join} button is below it.

At the foot of the left column stand the author, the version and the year. Pressing the author's name opens {t:about.title}.

The column's width is remembered in the browser where you set it.

## Limits

- While Ponistra is being updated or the connection is lost, the application is replaced by {t:status.away} It carries on by itself as soon as the server answers.
- If the server reports an error, the application is replaced by {t:status.down} and the reason.
- The next event at the foot of the bar does not show on a phone.
- {t:rail.projects} is seen only by a user who has been given a code workspace.

## Related

- [Today](help:start/today)
- [The search box](help:start/search)
- [Theme and language](help:start/appearance)
