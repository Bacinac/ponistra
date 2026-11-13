# Recording a meeting

A meeting is recorded into a folder in your documents, each participant as a file of their own, and what is said becomes minutes with tasks.

## How to use it

### Recording

1. In the meeting, press {t:recording.start}. Everyone in the meeting, guests too, sees {t:recording.on} beside the meeting's name.
2. To end it, press {t:recording.stop}. Anyone from the installation who is in the call stops the recording.
3. Once everyone has left the meeting, the recording ends by itself after one minute.

### Consent to the transcript

1. When the recording starts, a participant who has not yet given consent sees the question {t:recording.ask}
2. Press {t:recording.agree} or {t:recording.refuse}. The answer holds for that recording.

### The meeting's recordings

1. Open the meeting. Below the participants, before joining or after leaving, {t:recording.list} lists each recording by the time it started.
2. {t:recording.folder} opens the recording's folder and {t:recording.minutes} its minutes.
3. {t:recording.play} plays the participants' recordings together, each from the moment it was turned on. The slider moves the whole recording at once.
4. While a recording is being saved, {t:recording.saving} stands beside its time. If saving fails, the reason stands there instead, and the person who started the recording saves it again with {t:recording.again}.

## How it works

The recorder joins the meeting as an invisible participant and writes each participant's sound and picture as they were sent, without encoding them again: microphone, camera, screen and screen sound, each into a WebM file of its own. If someone turns their camera on twice, there are two files.

Once it ends, a job in the background saves the recording into a new folder at the top of the documents of the person who started it, named after the meeting and the time it started. The files carry the participant's name and the source, for example "Ana Horvat – camera". Colleagues from the installation who were in the meeting can read the folder.

The minutes are written when speech to text is turned on in the installation. Only the speech of those who agreed is transcribed: colleagues who gave their consent in [Consents](help:ai/consents), unless they answered {t:recording.refuse} in the meeting, and participants, guests too, who answered {t:recording.agree}. Each utterance is transcribed on its own, so the transcript knows who said what and when. When the model is turned on too, it writes from the transcript the summary, the decisions and the tasks. It gives each task to the person the transcript names for it, otherwise to the person who started the recording, with a due date where one was said. The minutes are a document in the recording's folder. It holds the tasks as a checklist, the people present and the whole transcript, and the tasks are also in [Tasks](help:tasks/overview), linked to the minutes. Without the model, the minutes hold only the people present and the transcript.

The recorder keeps the files until they are saved into the tree and the minutes are written, so saving again goes on from where it stopped.

## Limits

- Pictures sent as VP8 and sound as Opus are recorded, as browsers send them. Anything else is skipped.
- A guest does not start or stop a recording and does not see the recordings.
- A meeting has one recording at a time. If someone else starts one at the same moment: {t:error.already_recording}
- Only someone in the call starts and stops the recording. Anyone else gets the message {t:error.not_in_call}
- When the recorder or the meetings server does not answer, the message is {t:error.recording_unavailable} Ask your administrator.
- {t:error.not_started} Such a recording has nothing to save.
- {t:error.recorder_unavailable} Try again with {t:recording.again} once the recorder works again.
- {t:error.unsaved} Try again with {t:recording.again}.
- {t:error.no_owner}
- When speech to text fails, the reason stands beside the recording, for example that the key was refused. The folder is already saved by then, and {t:recording.again} writes only the minutes.

## Related

- [Meetings](help:meetings/overview)
- [Consents](help:ai/consents)
- [Tasks](help:tasks/overview)
