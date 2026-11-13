# Meetings

A meeting is a video call inside Ponistra: colleagues join by its link, and people outside the installation as guests.

## How to use it

### Joining a meeting

1. You open a meeting with the {t:meeting.join} button in an event, on the Today page or in a conversation, and a new meeting with the {t:meeting.now} button in conversations.
2. Before joining you see your camera's picture and who is already in ({t:meeting.present}), or {t:meeting.nobody}
3. With the switches {t:meeting.micOff} and {t:meeting.cameraOff} you join with the microphone or camera off; {t:meeting.devices} chooses the {t:meeting.camera}, the {t:meeting.microphone} and the {t:meeting.speaker}, which the device keeps for the next meeting, and the background and the sound's processing ([The camera's picture and sound in a meeting](help:meetings/camera)).
4. Press {t:meeting.join}, or {t:tree.cancel} to give up.

### In the meeting

- {t:meeting.micOff} and {t:meeting.micOn}, {t:meeting.cameraOff} and {t:meeting.cameraOn} turn the microphone and camera off and on.
- {t:meeting.share} shares your screen, a window or a tab with everyone; {t:meeting.stopSharing} ends the sharing.
- {t:chat.messages} opens the meeting's conversation beside the picture; the number on the button says how many messages you have not read.
- {t:meeting.nextScreen} moves the meeting's window to another screen, when the computer has one.
- {t:recording.start} records the meeting, and what is said becomes its minutes ([Recording a meeting](help:meetings/recording)).
- The number beside the title says how many people are in ({t:meeting.people}).
- {t:meeting.leave} leaves the meeting; after that {t:meeting.rejoin} takes you back in, and {t:meeting.back} leads back.

## How it works

A Ponistra meeting opens in a window of its own beside your work. If the browser does not allow a window of its own, the meeting opens in the same tab with a warning above it to allow pop-ups for the site.

A new meeting is made only when you join it or invite someone; if you close it before that, nothing stays. Every meeting has its own conversation, which stays after the call. While you share your screen it is not shown to you, so that it does not repeat inside itself; it says {t:meeting.presenting}

Guests, those invited from outside included, carry the mark {t:meeting.guest}, and you {t:meeting.you}. A muted microphone is marked beside the name ({t:meeting.muted}). If the connection breaks, it says {t:meeting.reconnecting} and Ponistra reconnects by itself; if that fails, it says {t:meeting.dropped}

## Limits

- If the browser allows neither the camera nor the microphone, you can join only once you allow them in the site's settings.
- Without a network you cannot join a meeting: {t:meeting.join} and {t:meeting.rejoin} are then turned off ({t:offline.needed}). A meeting you are already in is not cut off by it.
- If the browser does not play sound by itself, press {t:meeting.playAudio}.
- When the installation has an external meetings relay that cannot be reached at the moment, joining is refused with {t:error.relay_unreachable} Tell the installation's administrator.
- Moving to another screen needs permission to manage windows in the site's settings.

## Related

- [The camera's picture and sound in a meeting](help:meetings/camera)
- [Inviting to a meeting](help:meetings/inviting)
- [Guests](help:meetings/guests)
- [Recording a meeting](help:meetings/recording)
- [Events](help:calendar/events)
- [Conversations](help:chat/overview)
