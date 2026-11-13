# App passwords

An app password lets an app on a device that cannot sign in with a passkey, such as contacts and calendar on an iPhone, read your contacts and calendars from Ponistra.

## How to use it

### A password for another app

1. In Settings open {t:appPasswords.title}.
2. Press {t:appPasswords.otherOpen} The dialog {t:appPasswords.other} opens.
3. Type {t:appPasswords.newName} and press {t:appPasswords.add}. Meanwhile the button shows: {t:appPasswords.adding}
4. The dialog shows the {t:appPasswords.password}. Press {t:appPasswords.copy} or copy it by hand.
5. On the device add a CardDAV or CalDAV account and type the {t:appPasswords.server} and {t:appPasswords.user} the dialog shows, with that password. For an iPhone the dialog also gives the way through its settings.

### Removing a password

1. In the device's row open the menu of actions.
2. Choose {t:appPasswords.delete} and confirm in the dialog {t:appPasswords.deleteTitle}

## How it works

The password is made at random, of 16 letters and digits in groups of 4. Ponistra keeps only a digest of it, so it cannot show it again later. The list shows each {t:appPasswords.device}, when its password was made and {t:appPasswords.used}. Use is noted at most every 10 minutes. While there is no password, it says: {t:appPasswords.none}

This list also holds the passwords the Ponistra Android app received when the phone was connected. When you make a new password, the browsers where you turned notifications on get a notification of it.

Once a password is removed, the device using it can no longer reach your contacts and calendars.

The installation's administrator sees in its journal when an app password was added or removed, with its name, never the password itself.

## Limits

- The password shows only once, right after it is made. If you lose it, remove it and make a new one.
- An app password does not sign you in to Ponistra in a browser.
- The password stops working when the account is deactivated.
- To make a password, Ponistra may ask you to confirm that it is you.

## Related

- [Confirming it is you](help:account/confirm)
- [Signed-in devices](help:account/devices)
- [Android app](help:phone/android)
