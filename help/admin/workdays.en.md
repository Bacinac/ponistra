# Days off

An administrator decides the country and region whose holidays hold in the installation, the working hours and the days the company does not work.

## How to use it

### Country and holidays

1. Open {t:admin.title} and choose {t:workdays.title}.
2. Choose the {t:workdays.country} and, where holidays differ by region, the {t:workdays.subdivision} or {t:workdays.wholeCountry}.
3. Under {t:workdays.holidays} check the holidays that follow from it.

### Working hours

1. Under {t:workdays.hours} enter {t:workdays.opens} and {t:workdays.closes}.
2. Leave the field. The change is saved at once.

### Company days off

1. Press {t:workdays.new}.
2. Type the {t:workdays.name} and the dates {t:workdays.first} and {t:workdays.last}, then press {t:tree.create}.
3. For several days at once choose {t:workdays.import} and a calendar file.
4. Tick the events that are days off and press {t:workdays.importChosen}.
5. In a day off's row press {t:workdays.edit} or {t:workdays.delete}; confirm the deletion in the dialog {t:workdays.deleteTitle}

## How it works

The weekend and the holidays of the chosen country, and where they differ of the region, are the installation's days off. Under {t:workdays.closures} you enter days the company does not work although they are not holidays, such as a company-wide holiday; the list shows the {t:workdays.name} and {t:workdays.days} of each. Repetitions of series that mind days off move or are skipped by all these days.

{t:workdays.hours} hold on the installation's working days, on the installation's clock, and are 8 to 16 by default. The calendar offers free times by them when someone invited is not free; they do not move the repetitions of series.

From a calendar file only days not entered yet are offered, all ticked in advance. A deleted day off becomes a working day again.

## Limits

- When the file has no new days, it says: {t:workdays.importNone}
- While there is no company day off, it says: {t:workdays.none}
- Working hours that do not end after they begin are not saved, and it says: {t:error.invalid_hours}

## Related

- [Recurring events](help:calendar/recurring)
- [Rooms and resources](help:admin/resources)
