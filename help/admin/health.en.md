# System health

In one place an administrator sees the installation's version, the problems Ponistra found by itself, whether its services answer, the backups, the storage used and what waits in the queues.

## How to use it

1. Open {t:admin.title} and choose {t:health.title}.
2. If {t:health.problems} stands at the top, read what is not working and since when.
3. Under {t:health.services}, see whether each service says {t:health.answers} or {t:health.silent}.
4. Under {t:health.snapshots}, check {t:health.snapshots.newest} and {t:health.snapshots.due}.
5. Under {t:health.storage} and {t:health.queues}, see how much storage is used and what is waiting.

## How it works

The top of the page shows the installation's {t:status.version}. The page reloads itself every 30 seconds.

### Problems

While it runs, Ponistra checks by itself every 5 minutes what this page shows. A problem is raised only once it lasts: a service not answering after 10 minutes, a queue after an hour in which items wait and none is finished, and late backups ({t:health.problem.snapshots}) and late archiving of the database's changes ({t:health.problem.archive}) after an hour, as the first backup after an update may take that long. A [user source](help:admin/sources) that cannot be read ({t:health.problem.source}) is raised after 2 hours, with its name. A late {t:health.offsite} ({t:health.problem.offsite}) and a disk with less than 10% free are raised at once.

A raised problem stands under {t:health.problems} with the time it was first seen ({t:health.problems.since}), is written to the [journal](help:admin/journal) and reaches as a notification the browsers of every administrator who turned notifications on. A stalled queue is described as {t:health.problem.queue}, a disk as {t:health.problem.disk}. When the problem ends, it leaves the page and the journal notes it resolved.

### Services

{t:health.service.database}, {t:health.service.converter}, {t:health.service.printer}, {t:health.service.ocr} and {t:health.service.meetings} are checked on every load. {t:health.service.relay} is shown only on an installation that has one, and {t:health.service.outside} only when an external relay is set in [Meetings relay](help:admin/meetings); it then checks that the provider gives credentials.

### Backups

Backups are made every night and before every update. Beside {t:health.snapshots.newest} and {t:health.snapshots.due} the page shows when the last one was made and when the next is due, and beside {t:health.snapshots.count} how many are kept. When the night's backup is missing, a warning appears here with the command that shows the reason, and while there is no backup yet it says: {t:health.snapshots.none}

Between two backups Ponistra saves the database's changes and the new files every 15 minutes, and beside {t:health.snapshots.archived} the page shows when they were last saved. When they cannot be saved at all it says {t:health.snapshots.archiveError} with the reason, and when they are not saved in time: {t:health.snapshots.archiveLate} So the installation can be restored on its server to any moment of the last 7 days: `ponistra restore "2026-11-10 14:35"`. Without a moment `ponistra restore` brings back the newest state the backups hold, and with a backup's id the state when that backup was made. A file nothing uses any more stays on the disk for 7 more days, as a database restored to an earlier moment may need it.

### Storage and queues

Under {t:health.storage} the page shows how much the {t:health.stored.database} and the {t:health.stored.files} take, beside {t:health.stored.dead} how much the deleted files still waiting take, and for each disk how much of it is free. A disk is named by what it holds: {t:health.disk.files}, {t:health.disk.snapshots} or {t:health.disk.both}.

Under {t:health.queues} the page shows how many items wait in each queue: {t:health.queue.jobs} (waiting or running), {t:health.queue.ocr}, {t:health.queue.text} and {t:health.queue.batches}. The line {t:health.queue.unread} counts the files that were tried but cannot be searched, being damaged or too large.

## Limits

- Only an administrator opens the page.
- Until the off-site copy is set up, losing the server loses the backups too.
- A restore to a moment reaches back 7 days at most; older backups come back only as they were when they were made.
- Ponistra is stopped while a restore runs.
- A problem's notification reaches only an administrator who turned notifications on in some browser, and only while the installation sends notifications.
- While the server is down it does not check itself either: no notification tells of a server that is off.

## Related

- [Off-site copy](help:admin/offsite)
- [Journal](help:admin/journal)
- [Notifications](help:account/notifications)
