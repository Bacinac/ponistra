# Writing the time worked

Ponistra writes the time measured on the workspace's projects into Clockify or into TaskStreamer's time sheets, and removes the transcripts of archived chats once they are no longer needed.

## How to use it

### A destination

1. Open the Settings and, under {t:settings.workspace}, choose {t:workspace.view.hours}.
2. Under {t:workspace.sheets.heading}, at {t:workspace.sheets.clockify} or {t:workspace.sheets.taskstreamer}, press {t:workspace.sheets.setUp}
3. Enter the {t:workspace.sheets.key}; for TaskStreamer also the {t:workspace.sheets.address} and the {t:workspace.sheets.person}.
4. Keep or change the {t:workspace.sheets.label} (by default {t:workspace.sheets.labelDefault}) and {t:workspace.sheets.since}, then press {t:tree.save}.
5. Press {t:workspace.sheets.edit} and, under {t:workspace.sheets.projects}, choose for each of our projects ({t:workspace.sheets.project}) the destination's project in the column {t:workspace.sheets.target}, or leave it at {t:workspace.sheets.notWritten}. Mark a project that is never written as {t:workspace.sheets.excluded}. Once you add a project in Clockify, press {t:workspace.sheets.refresh}.
6. Turn on {t:workspace.sheets.nightly} for writing to happen by itself; while it is off, time is written only when you press {t:workspace.sheets.write}.

### Writing and comparing

1. A destination's card shows {t:workspace.sheets.mode} ({t:workspace.sheets.nightly} or {t:workspace.sheets.byHand}), {t:workspace.sheets.since}, {t:workspace.sheets.due} and {t:workspace.sheets.writtenAt}.
2. {t:workspace.sheets.write} writes every day waiting at once; afterwards {t:workspace.sheets.wrote} is shown.
3. {t:workspace.sheets.compare} opens the month by day: for each of the destination's projects the time {t:workspace.sheets.measured}, {t:workspace.sheets.own} (entries carrying the entry description) and {t:workspace.sheets.others} (other entries on the same project), with the day's state: {t:workspace.sheets.state.same}, {t:workspace.sheets.state.differs}, {t:workspace.sheets.state.open} or {t:workspace.sheets.state.before}. The month changes in the field {t:workspace.hours.month}.
4. {t:workspace.sheets.remove}, confirmed at {t:workspace.sheets.removeHeading} stops writing to that destination.

### Transcripts of archived chats

1. In the same settings, under {t:workspace.removal.heading}, choose {t:workspace.removal.never}, {t:workspace.removal.now} or {t:workspace.removal.after} in the field {t:workspace.removal.label}.
2. For {t:workspace.removal.after}, enter the {t:workspace.removal.days}; the default is 30.

## How it works

What is written is the time [Projects](help:agents/projects) shows under {t:workspace.view.hours}: blocks of work by project, the day by Croatian time. Our projects written to the same project of the destination are joined into the same blocks, not added up. A day is written only once it is over and none of its blocks can still grow, so at the earliest 17 minutes after the last work; a day before {t:workspace.sheets.since} never. A day written is remembered in Ponistra. If what was measured of it changes later, for instance when the workspace reads transcripts it fell behind on, the day is written again; otherwise the destination is not asked anything more.

Clockify gets one entry for each project and day, beginning with the first block and lasting as long as all the blocks together. Its description is the {t:workspace.sheets.label} followed by our projects. Entries carrying that description on the projects written to are taken as written from Ponistra: an identical one stays, a different one is deleted and a new one written. Entries made by hand and projects not written to are never touched. A free Clockify key takes 30 requests an hour; Ponistra spends at most 28, and the rest waits for the next pass. TaskStreamer gets each block as an entry of its own in the time sheet of the user in {t:workspace.sheets.person}. On the days written only the entries the tool made are replaced, and days whose time sheet is no longer a draft are skipped. The key is kept sealed in the database and never shown; the field stays {t:workspace.sheets.keyKept} until you enter a new one.

With {t:workspace.sheets.nightly} on, Ponistra writes every 15 minutes the days that have ended or changed since, so the day before is written a few minutes past midnight.

The workspace removes an archived chat's transcript, with the folder the chat keeps beside it, only once Ponistra confirms it read the time from it to its last line. It never removes a chat that is running or one in a round not yet closed. A chat missing from the list of the archived counts as archived since its transcript last changed, and is removed an hour after that at the earliest. The time measured stays in Ponistra after the removal, but such a chat can no longer be resumed.

## Limits

The settings exist only for the owner of the code workspace. TaskStreamer has to take time sheets through an API key; until it does, the card says {t:error.sheet_missing} {t:error.sheet_refused} means the key is not valid, so enter a new one. {t:error.sheet_busy} means Clockify's hour is used up and writing goes on by itself. {t:error.sheet_unreachable} and {t:error.sheet_failed} leave the days waiting for the next attempt. There is one destination of each kind.

## Related

- [Projects](help:agents/projects)
