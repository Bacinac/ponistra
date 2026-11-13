# Spoken commands

The microphone beside the search box turns what you say into text, then runs a command, opens a place or proposes an event, a task or a note.

## How to use it

### Recording

1. Press the microphone beside the search box ({t:speech.say}) or press {k:Alt-m}.
2. The first time, the question {t:speech.consent.heading} opens. Press {t:speech.consent.agree} if you agree.
3. While the microphone turns on, it says {t:speech.starting} then {t:speech.listening} with the time recorded. Speak.
4. Press {t:speech.done}. While the sound is turned into text, it says: {t:speech.writing}

### What happens with what you said

1. If you said the exact name of a command of the search box or of one of your links, for example "New note", it runs or opens at once.
2. Otherwise, when artificial intelligence is on, it says {t:speech.reading} and Claude decides what you want: to open a part of the application or the calendar on a given day, to open a link or a contact, to search for something, to start a new document or message, to add an event or a task, or to answer a question about Ponistra with articles of the help.
3. A message opens in the form for writing, with the recipients found among the contacts.
4. For an event, a task and a question about Ponistra, and when Claude recognises no command, the {t:speech.heard} window opens.

### The window with what you said

1. In the {t:speech.text} field correct the recognised text if needed.
2. Below it is {t:speech.proposed} with the event's or task's name and time. Press {t:speech.toEvent} or {t:speech.toTask} to check and save it.
3. {t:speech.toNote} saves the text as a new note.
4. Under {t:speech.commands} are the articles of the help that answer a question and the commands that hold the words said. Press one to run it.

## How it works

What you say is sent as sound to the speech-to-text model of OpenAI in the USA, with your installation's key. The sound is not kept in Ponistra. Text that is not a command's name, up to 2000 characters, is read by Claude of Anthropic when artificial intelligence is turned on for the installation; otherwise the window with what you said opens at once.

A proposed event opens the event form with the name, day, time and place Claude read, and the spoken text becomes its description. A message goes from the account you named, otherwise from the default one. When what you said fits several links or people, all are offered and you choose. A question about Ponistra is offered the articles of the help holding its key words, and where there is none, it says: {t:speech.noHelp}

The microphone beside a text field, such as a new round on the [Projects](help:agents/projects) page, takes the same consent and only writes what was said into that field, running nothing.

Recording lasts at most 10 minutes and then stops by itself. The consent is kept with your account, and you withdraw it in the [settings](/settings/ai), under {t:consents.title}.

## Limits

- If the administrator has not turned on speech to text, the microphone is disabled and beside it it says: {t:speech.off}
- If the browser does not allow the microphone, it says: {t:speech.microphone}
- If the recording holds no speech, it says: {t:speech.nothing}
- If the person you named is not among the contacts, the window says so and offers the other commands.
- If you have no mail account, it says: {t:speech.noAccount}
- If you have no calendar that can be written to, the button for an event is disabled: {t:speech.noCalendar}

## Related

- [The search box](help:start/search)
- [Notes](help:notes/overview)
- [Writing a message](help:mail/composing)
