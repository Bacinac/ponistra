# Vault

The vault keeps your passwords, one-time codes and notes encrypted in the browser, so that neither the server nor an administrator can read them.

## How to use it

![An unlocked vault with an item open](shot:vault-open)

### Making the vault

1. In the left column of Documents choose {t:vault.title}, or type its name into the search box. The first time, the page shows {t:vault.setup}.
2. Type {t:vault.password.new}, at least 12 characters, and repeat it under {t:vault.password.again}.
3. Press {t:vault.make}.
4. The {t:vault.code} opens. Press {t:health.kit.copy} or {t:health.kit.download} and keep the code outside Ponistra.
5. Press {t:vault.codeKept}.

### Unlocking and locking

1. A locked vault shows {t:vault.locked}.
2. Type the {t:vault.password.vault} and press {t:vault.unlock}, or press {t:vault.withPasskey} if you turned it on.
3. To lock it, press {t:vault.lock} at the foot of the left column.
4. The time after which the vault locks by itself is chosen in {t:vault.settings}, under {t:vault.idle}: {t:vault.idle.5}, {t:vault.idle.15} or {t:vault.idle.60}.

### Moving around the vault

1. In the left column {t:vault.mine} holds the items only you see.
2. Under {t:vault.shared} are the collections you share with others, and under {t:tree.company} those the company gave you.
3. The open collection's folders show below it, with the number of items.
4. Deleted items are under {t:trash.title}.
5. Type a word into {t:vault.search}. The search covers the name, username, addresses and notes of the whole collection, not only the open folder.

## How it works

Everything in the vault is encrypted in your browser before it goes to the server, and opened only in the browser after unlocking. The vault's key is derived from the vault's password, which is not the sign-in password and is not sent to the server.

An unlocked vault stays open while you work anywhere in Ponistra. It locks when you press {t:vault.lock}, when you sign out, when you reload the page and when you press no key and click nothing for the chosen time. The default is 15 minutes, and the choice is remembered in that browser.

The recovery code opens the vault if you forget the password. Later you can show it again or replace it with a new one in [the vault's settings](help:vault/recovery).

An empty collection says: {t:vault.empty} An empty folder says: {t:vault.folderEmpty} When a search finds nothing, it says: {t:vault.noMatch}

## Limits

- No one can bring back the vault's password. Without it, the recovery code and a passkey the vault cannot be opened, unless the company turned on vault recovery.
- When the passwords are not the same, it says: {t:vault.password.differs}
- When the password is wrong, it says: {t:vault.wrongPassword}
- {t:vault.noPrf} A passkey from another device or another manager may support it.

## Related

- [Vault items](help:vault/items)
- [Shared collections](help:vault/collections)
- [The vault's password, code and passkeys](help:vault/recovery)
