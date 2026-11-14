# Notifications

Ponistra announces new mail, a message that did not leave at its set time, a message no one answered by the date you set, an automatic answer that was not sent, messages in conversations and calls into a meeting even when it is not open, in the browser or in the installed app.

## How to use it

### Notifications in this browser

1. In Settings open {t:notifications.title}.
2. Under {t:notifications.thisBrowser} press {t:notifications.enable}.
3. The browser asks whether it may show notifications. Allow them.
4. The state is written below the heading: {t:notifications.on} or {t:notifications.off}
5. To stop, press {t:notifications.disable}.

### The installed app

1. Under {t:notifications.installTitle} press {t:notifications.install} if the browser offers it.
2. If it does not, install the app from the browser's menu, as the page describes.
3. Once the app is installed, it says: {t:notifications.installed}

### Other browsers

1. Under {t:notifications.browsers} are all the browsers where you turned notifications on: {t:notifications.browser}, {t:notifications.since} and {t:notifications.last}.
2. Beside a browser you no longer use press {t:notifications.remove}.

## How it works

A notification travels encrypted through the browser's push service and only that browser can read it. Pressing the notification opens the message, conversation or meeting. While some window of Ponistra on that device is visible, the notification is not shown. Notifications also come of a new sign-in to your account, a new passkey and a new app password, to an administrator of a problem of the installation, which opens the system health page, and to a folder's owner of a file sent into it through a link for sending files, a notification that opens the file itself. The owner of a [collection](help:mail/collections) is notified when it keeps a bill without a file, a notification that opens that bill's message. The owner of the code workspace is notified when a chat of a round waits for their decision, when every chat of a round has finished, when a round is consolidated and waits for its push, when the round's coordinator finished a step with a message or waits for their input, when the browser check or the night check failed, and when the plan's weekly limit or a model's limit passes 80% or a model starts spending credits; that notification opens the Projects page, in its own window when that is open. The notification of a chat or coordinator waiting for a decision carries the buttons {t:workspace.yes} and {t:workspace.no}, which answer without opening Ponistra. The owner is also notified of a new proposal for the [agent's memory](help:agents/memory); the notification of a single proposal carries the same buttons, which accept or reject it, and the notification of several says how many there are. When the analysis of the proposals has sorted them into groups, a notification says how many groups there are. All three open the {t:workspace.view.memory} tab on the Projects page.

Turning them on applies only to the browser you do it in. A browser that has never received a notification is marked {t:notifications.never}, and the one you are looking at the list in {t:notifications.this}. That one you do not remove from the list but by turning notifications off.

On an iPhone and iPad notifications work only from the app added to the home screen, and until then the page says so.

An administrator also sees {t:notifications.setting} on this page: with the switch {t:notifications.settingOn} they turn notifications on or off for the whole installation, and below it says {t:notifications.settingChanged} with a name and time. Turning it off deletes the notifications waiting to be sent, and while it is off nothing goes to the push services.

## Limits

- {t:notifications.unsupported}
- When an administrator has turned notifications off for the installation, the button to turn them on is not offered, and it says: {t:notifications.offInstallation}
- When the browser has blocked notifications, the button is not offered, and it says: {t:notifications.blocked}
- While no browser receives notifications, it says: {t:notifications.none}

## Related

- [Signed-in devices](help:account/devices)
- [Settings](help:account/settings)
