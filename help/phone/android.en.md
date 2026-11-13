# Android app

On an Android phone, Ponistra runs as an app of its own, which keeps your contacts and calendars in the phone and updates itself from the installation.

## How to use it

### Connecting from a computer

1. In Settings open {t:appPasswords.title} and under {t:phoneApp.title} press {t:phoneApp.connect}.
2. The {t:phoneApp.qr} appears on the screen. Scan it with the camera of an Android phone.
3. On the phone press {t:phoneApp.download} if you do not have the app yet and install it, then {t:phoneApp.open}.
4. The app asks for access to the contacts, the calendar and notifications, and opens. On the computer it says {t:phoneApp.connected} and the phone's name.

### Connecting on the phone itself

1. On the phone open Ponistra in the browser, then in Settings under {t:appPasswords.title} press {t:phoneApp.connect}.
2. Press {t:phoneApp.download} if you do not have the app yet, then {t:phoneApp.open}.

## How it works

The app opens Ponistra in Chrome as an app of its own and adds what a web page cannot do. Your contacts stand in the phone's address book and your calendars in the phone's calendar; a change on the phone goes to Ponistra and back, and an organisation's calendars are only read on the phone. When the same contact or event changed on both sides meanwhile, the change from Ponistra holds.

The phone signs in with an app password it received when it was connected; it stands among your [app passwords](help:account/app-passwords), where you can also remove it. If you close the dialog before the phone has connected, the password waiting for it is removed. The app shares content into Ponistra, as [sharing with Ponistra](help:phone/share) describes.

The app fetches a new version from the installation by itself when it opens, after a sync and twice a day. Where Android allows it, it installs it without asking; otherwise it waits in a notification you tap.

The installation's administrator sees in its journal when a phone was paired and when it was signed out.

## Limits

- The app exists only for Android; a code scanned with another phone does not connect it.
- The connection code is valid for ten minutes, and only once.
- Before connecting, Ponistra may ask you to [confirm it is you](help:account/confirm).
- {t:phoneApp.connect} exists only when the installation offers the app.

## Related

- [Sharing with Ponistra](help:phone/share)
- [App passwords](help:account/app-passwords)
- [Contacts](help:contacts/overview)
