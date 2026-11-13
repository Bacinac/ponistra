# Tasks

A task is a line you need to get done, with a due date if it has one; it is made from a message, an event or a line of a document and leads back to it.

## How to use it

### A new task

1. On the [tasks](/tasks) page press {t:tasks.new}.
2. In the {t:tasks.text} field type what needs doing, and in the {t:tasks.due} field a due date if you wish.
3. Press {t:tree.create}.

### A task from a message, an event or a document

- In an open message press {t:tasks.fromMail}. The task gets the message's subject.
- In an open event press {t:tasks.fromEvent}. The task gets the event's title and the event's day as its due date.
- In a document the task action takes the selected words or the whole line you are in.

### Finishing and changing

1. The tick beside a task marks it {t:tasks.done}.
2. A click on a task opens {t:tasks.edit}: change the text, the due date or the {t:tasks.done} tick, then press {t:tree.save}.
3. {t:tasks.delete} deletes the task.

## How it works

Tasks are put into the groups {t:tasks.group.overdue}, {t:tasks.group.today}, {t:tasks.group.later}, {t:tasks.group.undated} and {t:tasks.group.done}, and within a group by due date. A due date that has passed shows in red. Finished tasks stay on the list for 30 more days.

A task made from something shows where it came from, for example {t:tasks.from.mail}, {t:tasks.from.event} or {t:tasks.from.document}, with a link back to the message, the day in the calendar or the document's line. Tasks with a due date also stand in the calendar on their due day, and today's and late ones on the Today page.

Tasks are yours alone. There are no subtasks, projects or assigning to others: one list, the day in the calendar and the Today page.

## Limits

- A task's text has at most 1,000 characters.
- Deleting asks for no confirmation.
- While there is no task, it says: {t:tasks.none}

## Related

- [Calendar](help:calendar/overview)
- [Today](help:start/today)
- [Events](help:calendar/events)
