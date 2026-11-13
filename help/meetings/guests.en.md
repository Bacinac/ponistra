# Guests

A person outside the installation joins a meeting as a guest, by its link, without an account; someone in the meeting lets them in.

## How to use it

### Joining as a guest

1. Open the meeting's link. You see the meeting's name, your camera's picture and who is in.
2. Type {t:meeting.yourName} and press {t:meeting.join}.
3. Until someone lets you in, it says {t:meeting.waiting}
4. If you have an account in the installation, press {t:meeting.signIn}; {t:meeting.asGuest} takes you back to joining as a guest.

### Letting guests in

1. When a guest waits, their name appears in the meeting under {t:lobby.title}.
2. Press {t:lobby.admit} or {t:lobby.refuse}.

## How it works

Anyone of the installation who is in the meeting's conversation can let a guest in, even before joining the call themselves, while the meeting is open in front of them. A person whose link came by email from Ponistra has a link of their own with the name already filled in and joins without waiting.

A guest in the meeting sees and hears everything, shares the screen and writes in the meeting's conversation, and carries the mark {t:meeting.guest} beside the name. They cannot invite others or let guests in. If they reload the page in the same tab, they do not wait at the door again.

A guest joins the same way as members: when the installation has an external meetings relay, the guest's picture and sound go through it, so they join even from a network that does not reach the installation directly.

## Limits

- A guest sees only that meeting and its conversation, nothing else of the installation.
- A refused guest does not get into the meeting.
- At most 20 guests who came by the meeting's link in the last 10 minutes can wait at one meeting at a time. The next one sees: {t:error.door_full} Guests invited by email are not limited by this.

## Related

- [Meetings](help:meetings/overview)
- [Inviting to a meeting](help:meetings/inviting)
