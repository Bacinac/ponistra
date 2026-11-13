# Comments

A comment is tied to the marked text, and the conversation about it runs in a side panel until someone resolves it.

## How to use it

### A new comment

1. Mark the text.
2. On the toolbar or with a right click choose {t:command.comment} ({k:Mod-Alt-m}).
3. In the {t:comment.list} panel, under {t:comment.new}, write the comment and send it.

### Replying and resolving

1. In the document's header press {t:comment.list}. Beside the button stands the number of unresolved comments on the open tab.
2. Press a comment to jump to the text it is tied to.
3. Write a reply and press {t:comment.reply}.
4. Press {t:comment.resolve} once the question is settled, and {t:comment.reopen} to open it again.

### Changing and deleting

1. In the menu of your own comment choose {t:comment.edit} or {t:comment.delete}.
2. Confirm the deletion in the {t:comment.deleteTitle} dialog.

### A task from a line

1. Stand in a line or mark some words.
2. On the toolbar choose {t:command.task} and save the task.

## How it works

The panel shows the open tab's comments in the order they stand in the text. Resolved comments are hidden, and {t:comment.showResolved} shows them with their number; beside each it says {t:comment.resolved}, who resolved it and when. A comment changed after it was sent carries the mark {t:comment.edited}, and a comment from an imported file the mark {t:comment.imported} with the author's name from the file. An author whose account was deleted shows as {t:comment.formerUser}. When the text a comment is tied to is deleted, the comment stays and says so.

On a PDF a comment is tied to marked text or a point on the page, so {t:pdf.page} with its number stands beside it.

A task from a line takes the marked words, or the whole line, and a link back to that place in the document.

## Limits

- Anyone who can open the document can comment, but only those who may edit it resolve and reopen.
- Only its author changes and deletes a comment. A conversation is gone when its last comment is deleted.
- A resolved comment cannot be replied to until it is reopened.

## Related

- [Suggested changes](help:text/proposals)
- [PDF notes](help:pdf/notes)
- [Sharing](help:documents/sharing)
