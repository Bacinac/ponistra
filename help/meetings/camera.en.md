# The camera's picture and sound in a meeting

The background behind you, following your face, fixing poor light and processing the microphone's sound are chosen beside the devices, before joining a meeting and in it.

## How to use it

### Background

1. Before joining or in the meeting press {t:meeting.devices}, then {t:meeting.background}.
2. Choose {t:meeting.background.none}, {t:meeting.background.soft}, {t:meeting.background.strong} or one of the built-in pictures: {t:meeting.background.petrol}, {t:meeting.background.sage}, {t:meeting.background.paper} and {t:meeting.background.evening}.
3. For a picture of your own press {t:meeting.backdropUpload} and choose a photo. It becomes the background at once and appears in the list as {t:meeting.background.own}.
4. {t:meeting.backdropRemove} deletes your picture, and the background returns to {t:meeting.background.none}.

### Face and light

1. Press {t:meeting.devices}.
2. {t:meeting.framing} turns on and off the framing that follows your face.
3. {t:meeting.light} turns on and off brightening the picture when the room is dark.

### Sound

1. Press {t:meeting.devices}, then {t:meeting.sound}.
2. {t:meeting.noise}, {t:meeting.echo} and {t:meeting.gain} are each turned on and off by themselves. All three are on by default.

## How it works

Your browser processes the picture and sound, on your device, before sending them. The other participants and the meeting's recording get the picture already processed. The model that tells a person from the background and the model that looks for a face come from your Ponistra installation, not from outside servers.

Your account keeps the processing you choose, so it holds on every device you sign in on. The camera, microphone and speaker you choose are kept by each device for itself, as another device has others. A guest has no account, so the browser they joined in keeps their choice.

The browser shrinks a picture of your own to at most 1920 × 1080 pixels before sending it and keeps it with your account. Only you see it, and others see it only behind you in a call. It is part of the export of your data.

{t:meeting.framing} looks for faces in the picture several times a second and moves the crop slowly so that the face stands in the upper part of the picture. With several people in the picture, the crop takes in them all. When no face is seen for more than 3 seconds, the picture returns to the whole frame. {t:meeting.light} measures the picture's brightness twice a second and brightens a dark picture at most twofold. A bright picture stays as it is.

The browser itself processes the sound. A changed switch holds at once for the microphone in the meeting. A muted microphone stays muted.

If the device cannot process a picture in the time between two pictures of the camera, Ponistra first turns the background off and says {t:meeting.strainedBackground} If that is not enough, it turns all processing off and says {t:meeting.strainedAll} The picture then goes unprocessed, and your choice stays kept.

## Limits

- A guest cannot upload a picture of their own.
- A picture of your own can be PNG, JPEG, WebP, GIF or AVIF. A file that is not a picture is refused ({t:error.not_a_photo}).
- A browser that cannot process the camera's picture offers the background, the face and the light turned off, with the note {t:meeting.unshapeable} Sound is chosen even then.
- When processing fails, below the picture it says {t:meeting.shapingFailed} and the reason. {t:meeting.retry} tries again, as it does after processing was turned off for the load.
- Processing the picture uses the processor and the graphics card. On a weaker device choose {t:meeting.background.soft} instead of a picture, or turn off {t:meeting.framing}.

## Related

- [Meetings](help:meetings/overview)
- [Recording a meeting](help:meetings/recording)
- [Guests](help:meetings/guests)
