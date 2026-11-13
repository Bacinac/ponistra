# Groups

Groups gather users who are given company folders, vault collections and shared items together.

## How to use it

1. On the {t:users.title} page press {t:users.newGroup}, type the name and press {t:tree.create}.
2. You add users to a group in their account, under {t:users.edit}, with the tick beside the group's name.
3. In the {t:access.groups} section open the menu beside a group and choose {t:tree.rename} or {t:users.deleteGroup}.
4. Confirm the deletion in the dialog {t:users.deleteGroupTitle}

## How it works

Beside each group stands how many members it has ({t:users.members}). When you delete a group, its members lose the access the group gave them, and their own access stays.

Adding, renaming and removing a group are written to the [journal](help:admin/journal).

## Limits

- Two groups cannot have the same name.
- A group that comes from a provider or a directory cannot be renamed or deleted, and the source decides its members; its name has the source's name beside it. See [Outside sign-in and directories](help:admin/sources).
- A group cannot be deleted if an item at the top would be left without an owner or a vault collection without an owner.
- While there is no group, it says: {t:users.noGroups}

## Related

- [Users](help:admin/users)
- [Company folders and collections](help:admin/company)
