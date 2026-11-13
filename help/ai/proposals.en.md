# Proposals

Text that Claude or an outside agent writes into a document stands as a proposal until you accept or reject it.

## How to use it

### One proposal

1. Put the cursor in the proposed text.
2. Above the line appear the kind of proposal, who proposed it and when.
3. Press {t:action.proposalAccept} or {t:action.proposalReject}.

### All proposals in the tab

1. While the tab has proposals, the toolbar shows {t:action.documentAccept} and {t:action.documentReject}.
2. Press one of them.

## How it works

A proposal is one of the kinds {t:proposal.insertion}, {t:proposal.deletion}, {t:proposal.replacement} or {t:proposal.formatting}. An accepted proposal becomes ordinary text of the document, and a rejected one disappears. A proposal carries the name of the person who started the action; if an outside agent wrote it, it reads agent {t:run.via} person.

Accepting and rejecting are actions themselves, so you take them back with {t:run.undo}.

## Limits

- Only someone who may edit the document accepts and rejects.
- {t:action.documentAccept} and {t:action.documentReject} apply to the proposals of the open tab, not to the document's other tabs.

## Related

- [Writing with Claude](help:ai/writing)
- [Actions and Claude](help:ai/actions)
- [Outside agents](help:agents/connecting)
