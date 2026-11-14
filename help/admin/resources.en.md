# Rooms and resources

An administrator keeps the list of rooms, equipment and vehicles that users book by putting them on an event.

## How to use it

1. Open {t:admin.title} and choose {t:resources.title}.
2. Press {t:resources.new}.
3. Type the {t:resources.name}, choose the {t:resources.kind} ({t:resources.kind.room}, {t:resources.kind.equipment}, {t:resources.kind.vehicle} or {t:resources.kind.other}) and if you like the {t:resources.capacity} and {t:resources.place}.
4. Leave {t:resources.active} ticked and press {t:tree.create}.
5. In a resource's row press {t:resources.edit} or {t:resources.delete}; confirm the deletion in the dialog {t:resources.deleteTitle}

## How it works

A room, equipment or vehicle is booked by putting it on an event, and at any one time it can be on only one. Users no longer see a resource without the {t:resources.active} tick and cannot put it on an event; in your list it stands with the mark {t:resources.retired}.

A deleted resource disappears from every event it was booked on.

Adding, changing and removing a room or resource are written to the [journal](help:admin/journal).

## Limits

- While there is no resource, it says: {t:resources.none}
- A resource out of use stays on the events it is already booked on.

## Related

- [Rooms and resources in the calendar](help:calendar/rooms)
- [Days off](help:admin/workdays)
