# The vault's password, code and passkeys

In the vault's settings you change its password, show or renew the recovery code and turn on unlocking with a passkey.

## How to use it

### The vault's settings

1. In the unlocked vault press {t:vault.settings} at the foot of the left column.
2. Under {t:vault.password.change} type the {t:vault.password.new} and repeat it, then press {t:vault.password.change}. When done, it says: {t:vault.password.changed}
3. Under {t:vault.code} press {t:vault.codeShow} to see the current code, or {t:vault.codeRenew} for a new one.
4. Under {t:vault.passkeys} press {t:vault.passkeyAdd} and confirm with one of your passkeys. Beside each passkey in the list is {t:vault.passkeyRemove}.
5. Under {t:vault.recovery} it says whether the company can recover your vault and, if it already has, {t:vault.recoveredBy}.

### A forgotten password

1. On the locked vault press {t:vault.forgot}.
2. Type the {t:vault.code} and press {t:vault.unlock}.
3. The vault asks for a new password: type it twice and press {t:vault.password.set}.
4. To go back to the password, press {t:vault.withPassword}.

### A code from an administrator

1. When an administrator has prepared a recovery code for you, the locked vault asks for the {t:vault.code} straight away.
2. Type the code you received from them and press {t:vault.unlock}.
3. Set a new vault password and press {t:vault.password.set}.

### Starting from scratch

1. If you have neither the password nor the code, press {t:vault.forgot}.
2. Press {t:vault.restart} and confirm in the dialog {t:vault.restartTitle}

## How it works

The recovery code is made with the vault and opens it as the password does. A new code cancels the previous one. After opening with the code the vault does not let you go on until you set a new password, and it says: {t:vault.password.afterCode}

Unlocking with a passkey uses the passkeys you sign in to Ponistra with. The vault unlocks only with a passkey that, besides signing in, also gives a secret for encryption, which Android, iPhone, Mac and Windows 11 with a recent browser support.

When the company has turned on vault recovery, the vault is also locked with the company's key at its next unlocking. Then it says: {t:vault.recoverable} If that fails, it says: {t:vault.enrolFailed} Each recovery an administrator makes shows under {t:vault.recoveredBy}, both on the locked vault and in the settings.

Starting from scratch deletes My vault with all its items, the password, the code and the unlocking by passkey. Shared collections stay with the other members, and you return to them once an owner confirms you again.

## Limits

- When the code is wrong, it says: {t:vault.wrongCode}
- {t:vault.noPrf}
- Changing the password, unlocking by passkey and starting from scratch may ask you to confirm that it is you.
- Starting from scratch cannot be undone.
- An administrator who alone holds the vault recovery key cannot start from scratch until they hand it to another administrator.

## Related

- [Vault](help:vault/overview)
- [Passkeys](help:account/passkeys)
- [Confirming it is you](help:account/confirm)
