# Actions and Claude

Actions are ready-made operations on text, a table or the whole document, some of which the model Claude by Anthropic carries out.

## How to use it

### Running an action

1. Select text or put the cursor in the table the action is for.
2. Right-click or long-press to open the menu and choose the action. Actions on a table are also in the {t:commandGroup.table} menu on the toolbar.
3. You can also find an action by its name in the search box while the document is open.

### Sending to Claude the first time

1. When an action needs Claude and the document has not allowed it yet, the dialog {t:ai.consent.heading} opens.
2. Choose {t:ai.consent.once} or {t:ai.consent.always}.
3. You withdraw the document's permission in the document's menu: {t:ai.consent.withdraw}

### Progress and undoing

1. While an action runs, its name stands at the foot of the page, and while Claude writes also {t:run.writing}
2. Press {t:run.stop} for Claude to stop after the step it is on. Until then the button shows: {t:run.stopping}
3. When the action ends, it says {t:run.done} or {t:run.stopped} with the action's name.
4. Press {t:run.undo} to take back everything the action changed.

## How it works

Actions without a model, such as totalling columns, run at once on the server. Actions with a model send Claude the text they apply to, and Claude writes in the background, so you can keep working. Everyone in the document sees the action, with the name of the person who started it; if an outside agent started it, the name reads agent {t:run.via} person.

The permission {t:ai.consent.always} stays with the document and holds for anyone who may edit it, until someone withdraws it. The permission {t:ai.consent.once} holds for that action alone.

If an action fails, everything it wrote until then is taken back. A stopped action keeps what it wrote until it stopped. {t:run.undo} takes back the action's changes, and what others wrote meanwhile stays; an action is undone only once.

## Limits

- Only someone who may edit the document runs actions.
- While AI is not turned on for the installation, actions with a model are disabled and beside them it says: {t:ai.off}
- Only actions with a model can be stopped.
- Without the network the actions are disabled ([Working offline](help:account/offline)).

## Related

- [Writing with Claude](help:ai/writing)
- [Proposals](help:ai/proposals)
- [Actions on a table](help:ai/tables)
- [Consents](help:ai/consents)
