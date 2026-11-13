# Vault recovery

While vault recovery is on, an administrator can prepare a one-time code into the vault for a user who has forgotten both the vault's password and its code.

## How to use it

### Turning it on

1. Make and unlock your own vault.
2. On the {t:users.title} page, in the {t:recovery.title} section, where it says {t:recovery.off} press {t:recovery.turnOn}.
3. Confirm another administrator who has a vault and stands under {t:recovery.waiting} with the {t:vault.confirm} button.

### Recovering a user's vault

1. Unlock your own vault.
2. In the user's row menu choose {t:recovery.recover}.
3. Press {t:recovery.prepare}.
4. Hand the code to the user in person, not by mail or message.

### Turning it off

1. Press {t:recovery.turnOff}.
2. Confirm in the dialog {t:recovery.turnOffTitle}

## How it works

The recovery key is made by the browser of the administrator who turned recovery on and locked to them; each confirmed administrator gets their own copy. Each vault is also locked with the company's key at its next unlocking. The section shows who turned recovery on and when ({t:recovery.on}), the {t:recovery.escrowed} out of all vaults and the {t:recovery.holders}.

The code is made in your browser. The user opens the vault with it and at once sets a new password; the code holds until they do. Whoever can recover a vault can also read it, so the user sees in their vault who last recovered it and when.

Turning it off deletes the company's key with everything locked with it. A user who then forgets the password and the code can no longer open the vault, and turning it on again makes a new key.

## Limits

- Recovery does not help until the user has unlocked their vault since recovery was turned on.
- Only an administrator who holds the recovery key prepares codes and confirms administrators.
- When the user has no vault, it says: {t:recovery.noVault}
- Turning it on, turning it off and preparing a code may ask you to confirm that it is you.

## Related

- [Users](help:admin/users)
- [The vault's password, code and passkeys](help:vault/recovery)
