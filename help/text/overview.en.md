# The document editor

You write and format a document in one window: the tabs are on the left, the toolbar at the top, and changes save themselves and show at once to everyone who has the document open.

## How to use it

![An open document with the toolbar](shot:text-editor)

### Writing

1. Open a document from the list and write straight into it. An empty document reminds you that “/” opens inserting.
2. The toolbar holds {t:command.undo} ({k:Mod-z}) and {t:command.redo} ({k:Mod-y}), the paragraph style, formatting, colours, lists, alignment, {t:editor.insert} and comments. What does not fit in the bar is under {t:editor.more}.
3. A right click in the text opens a menu with the commands for the place you are at.
4. Type “/” at the start of a line or after a space for a list of what {t:editor.insert} offers. Further letters narrow the list, and {k:Enter} inserts the chosen item.
5. {k:Mod-f} opens [find and replace](help:text/find) in the tab.

### View

1. On the right of the toolbar choose the {t:view.label}: {t:view.text}, {t:view.pages} or {t:view.slides}.
2. In the pages and slides views, under {t:zoom.label} you choose {t:zoom.page} or {t:zoom.width}.

### The document's header

1. Press the document's title in the path for the document's menu: copy, rename, move, import, save in another format, print, page setup, styles and language.
2. The buttons on the right open {t:agent.title}, {t:comment.list}, {t:access.share} and {t:version.list} in a side panel.

## How it works

Every change goes to the server at once, so there is no save button. The right of the toolbar shows the connection's state: {t:collab.connected}, then {t:collab.connecting} while the connection is made, or {t:collab.disconnected} when it breaks, and Ponistra then reconnects by itself.

When someone else is editing the document, you see their cursor in a colour with their name. Your own cursor from another device or window is marked {t:presence.you}. {t:command.undo} takes back only your own changes, not those of others.

{t:view.text} shows the text in one column, {t:view.pages} as it will print, with rulers beside the page, and {t:view.slides} slide by slide. The chosen view is remembered for each document in that browser. A document imported from Word first opens in the pages view, and one from PowerPoint in the slides view. The zoom holds for all documents.

## Limits

- With the right to read, the toolbar does not show: you can read and comment on the document.
- {t:zoom.label} exists only in the pages and slides views.
- When a command cannot run, {t:command.failed} is reported.
- Without the network a document opens only on a device marked for [working offline](help:account/offline).

## Related

- [Tabs](help:text/tabs)
- [The agent beside the document](help:ai/agent)
- [Formatting text](help:text/formatting)
- [Keyboard shortcuts](help:text/shortcuts)
- [Find and replace](help:text/find)
- [Versions](help:documents/versions)
