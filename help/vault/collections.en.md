# Shared vault collections

A collection is a part of the vault you share with users or groups, so that all members see the same passwords.

## How to use it

### A new collection

1. In the vault's left column, beside {t:vault.shared}, press {t:vault.newCollection}.
2. Type a name and press {t:tree.create}.

### Members

1. Open the collection and choose {t:vault.members} in the menu of other actions. The same menu opens on a right click or a long press on a collection or a folder in the left column.
2. Under {t:access.who} choose {t:access.everyone}, a person from {t:access.people} or a group from {t:access.groups}.
3. Choose the {t:access.role}: {t:access.role.read}, {t:access.role.edit} or {t:access.role.own}, then press {t:access.add}.
4. A member's role is changed in their row, and {t:access.remove} removes them.
5. Under {t:vault.waiting} press {t:vault.confirm} beside a member, or {t:vault.confirmAll}.
6. You leave a collection of someone else's with {t:vault.leave}.

### The collection and its log

1. An owner chooses {t:log.title} in the menu of other actions: {t:log.when}, {t:log.who} and {t:log.what}.
2. An owner renames the collection with {t:tree.rename}.
3. Or deletes it with {t:vault.deleteCollection}, confirming in the dialog {t:vault.deleteCollectionTitle}

## How it works

Each collection has a key of its own, with which its items are encrypted. A member sees the items only once an owner confirms them: in confirming, the owner's browser encrypts the collection's key for that member. When you add a person who already has a vault, they are confirmed at once. Whoever has no vault yet is listed as {t:vault.unset} and waits for confirmation once they make one. The number of members waiting stands beside the collection in the left column, and a collection whose key you do not hold yet is marked {t:vault.pending}.

{t:access.role.read} allows looking and copying, {t:access.role.edit} also adding, changing and moving items, and {t:access.role.own} also the members, the log, exporting, deleting from the trash for good, and renaming and deleting the collection.

The log notes {t:vault.log.opened}, {t:vault.log.password}, {t:vault.log.totp}, {t:log.kind.shared}, {t:log.unshared}, {t:vault.log.confirmed} and {t:vault.log.exported}. Opening and showing the same password by the same user again are not noted again within an hour. A deleted item stands in the log as {t:vault.log.gone}, and a deleted user as {t:log.formerUser}. While there is no entry, it says: {t:vault.log.none}

The collections the company gave stand under {t:tree.company}. Their members are set by an administrator and confirmed by the owners. A company collection no one has opened yet is opened by its owner with {t:vault.firstKey}, who then confirms the others. An administrator who is not a member cannot read it.

A deleted collection goes with all its items, for all members.

## Limits

- A collection must always have at least one owner, so you cannot remove the last one or change their role.
- You cannot leave or rename a company collection; an administrator does that.
- A member who makes a new vault from scratch must be confirmed again.

## Related

- [Vault items](help:vault/items)
- [Import and export of the vault](help:vault/transfer)
- [Vault](help:vault/overview)
