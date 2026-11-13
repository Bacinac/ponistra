# Company folders and collections

An administrator sets up company folders and company vault collections and gives them to groups.

## How to use it

### A company folder

1. On the {t:users.title} page, in the {t:company.title} section, press {t:company.new}.
2. Type the {t:tree.name}.
3. Under {t:access.here} choose for {t:access.everyone} and for each group {t:company.noRole}, {t:access.role.read}, {t:access.role.edit} or {t:access.role.own}.
4. If needed tick {t:confined.label}, then press {t:tree.create}.
5. You change an existing folder in its row's menu with {t:company.edit}, and delete it with {t:company.delete} and confirmation in the dialog {t:company.deleteTitle}

### A company vault collection

1. In the {t:vault.company.title} section press {t:vault.company.new}.
2. Type the name and give groups roles as for a company folder.
3. You change a collection with {t:vault.company.edit}, and delete it with {t:vault.company.delete} and confirmation in the dialog {t:vault.company.deleteTitle}

## How it works

A company folder appears under {t:tree.company} for the users you gave it to. You set it up and give it out, and only those with a role in it see its content. In a folder marked {t:confined.label}, whoever is not an owner reads and edits documents only in Ponistra. Beside each folder in the list stands who has which role, and beside a folder without downloads a lock icon.

An administrator arranges a company vault collection but cannot read it: the collection's key is made by the first owner who opens it in their vault.

## Limits

- A folder or collection is saved only once at least one group or {t:access.everyone} has the role {t:access.role.own}.
- Only an empty company folder and only an empty collection can be deleted, and a folder under a legal hold cannot be deleted.
- While there are none, it says: {t:company.none} or {t:vault.company.none}

## Related

- [Groups](help:admin/groups)
- [A folder on a file server](help:admin/file-server)
- [Company folders](help:documents/company)
