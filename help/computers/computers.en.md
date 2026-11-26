# Computers

The Ponistra OS computers you manage are run from Ponistra: their pages, alerts, managers, disk recovery key and backup password.

## How to use it

### Opening a computer

1. On the module bar, press {t:rail.computers}. On a phone it is in the account menu. An administrator also reaches it through {t:admin.title}, {t:computers.title}.
2. The left column lists the computers you manage. Beside each name is {t:computers.connected} or {t:computers.offline} and the number of alerts that last.
3. Press a computer. Below its name are the computer's pages, the same as on its own page, and {t:computers.manage}.
4. While you manage no computer, the page says: {t:computers.none}

### Management

1. Open the computer and press {t:computers.manage}.
2. {t:computers.alerts} lists the alerts that last, with their level {t:computers.severity.info}, {t:computers.severity.warning} or {t:computers.severity.critical} and when they arose.
3. Under {t:computers.managers}, choose a person in {t:computers.manager.add} and press {t:computers.manager.addButton}. A manager is removed with {t:computers.manager.remove} beside their name.
4. Under {t:computers.secret.recovery_key} and {t:computers.secret.backup_password} stands {t:computers.secret.kept} with the time the computer handed them over. Press {t:computers.secret.show} and confirm it is you.
5. {t:computers.openings} lists who opened which secret, when and from which address.
6. Under {t:computers.remove}, press {t:computers.remove.button} and confirm.

### Codes and computers without a manager

1. {t:computers.codes} lists the one-time codes you made that no computer has used yet: the code's end and its deadline. {t:computers.code.delete} cancels a code.
2. An administrator sees under {t:computers.orphaned} the computers nobody manages any more and becomes their manager by pressing {t:computers.takeOver}.

## How it works

A computer stays connected to Ponistra over a link it opens itself, so it needs no public address or open port. The computer's pages in Ponistra send each request over that link, and the computer runs it as your account, by your email address, and records it among its tasks. What only the computer's own page may do, enrolling in Ponistra and leaving it, is not offered here. An ISO file for a guest is first uploaded to Ponistra in pieces, and Ponistra then sends it to the computer.

While a computer is not connected, its name shows {t:computers.offline} and when it was last connected, and its pages show an error rather than old data.

Only a manager sees the list. The first manager is the administrator who made the code the computer enrolled with; any manager adds other users of the installation. A computer always keeps at least one manager, so the last cannot be removed. When no manager is active any more, for example because their account was deleted, the computer appears to administrators under {t:computers.orphaned}. A person who is not a manager but owns a guest on the computer opens only that guest's console and snapshot files; the computer checks the ownership.

An alert that arises, changes its level or clears is sent to every active manager as a [notification](help:account/notifications) that opens the computer. An alert of level {t:computers.severity.critical} is sent with the highest urgency. Alerts are not sent by email.

The computer hands over its recovery key and backup password by itself, and Ponistra keeps them encrypted. Every opening asks you to [confirm it is you](help:account/confirm) and is recorded on the computer with the person, time and address; the list shows the latest 100. A deleted person stands as {t:computers.someone}. An opened secret stays on the screen until you leave the page.

Removing deletes the computer from Ponistra with its key and password and ends its link; the computer can then enroll again only with a new code. A computer that left Ponistra from its own page stays on the list with its key and password, but its pages no longer open.

The list and the state are read again as soon as they change, without reloading the page.

## Limits

- Only an administrator adds new computers, with {t:computers.add}.
- {t:computers.secret.none} The computer hands the secret over after its installation; until then there is nothing to open.
- {t:computers.error.computer_offline} The computer is off or has no network; wait until it connects again.
- {t:computers.error.computer_timeout} and {t:computers.error.stream_not_opened} The computer is busy or the link breaks; try again.
- {t:computers.error.request_too_large} The request does not fit the link; a file goes through an upload.
- {t:computers.error.forbidden} You neither manage that computer nor own the guest.
- {t:computers.error.not_found} The computer was removed or you no longer manage it.
- {t:computers.error.last_manager} Add another manager first.
- {t:computers.error.invalid_user} A manager can only be an active user of the installation, not a visitor or a shared mailbox.
- {t:computers.error.not_kept} The computer has not handed that secret over yet.
- {t:computers.error.secret_unreadable} The key the secret was encrypted with no longer exists on the installation; tell the administrator.
- {t:computers.error.invalid_upload} The file's upload did not finish; upload it again.

## Related

- [Files of guests on computers](help:files/guests)
- [Notifications](help:account/notifications)
- [Confirming it is you](help:account/confirm)
