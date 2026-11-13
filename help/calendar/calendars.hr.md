# Kalendari

Događaje držite u više kalendara, svakom s vlastitim nazivom i bojom; uz vaše vlastite tu su i kalendari povezanih računa e-pošte.

## Kako se koristi

### Novi kalendar i promjena

1. U lijevom stupcu uz {t:calendar.calendars} pritisnite {t:calendar.settings}.
2. Pritisnite {t:calendar.newCalendar}, ili postojeći kalendar pritisnite desnom tipkom ili dugo i odaberite {t:calendar.editCalendar}.
3. Upišite {t:calendar.field.name} i odaberite {t:calendar.field.color}.
4. Pritisnite {t:tree.save}.

### Brisanje i praćenje

1. U prozoru kalendara pritisnite {t:calendar.deleteCalendar} i potvrdite s {t:calendar.delete}.
2. Kalendar koji pripada povezanom računu ne briše se nego se prestaje pratiti: pritisnite {t:calendar.unfollow} i potvrdite istim gumbom.
3. Kalendari koje ne pratite stoje u popisu pod {t:calendar.unfollowed}; gumb {t:calendar.follow} ponovno ih uključuje.

## Kako radi

Vaši vlastiti kalendari žive u Ponistri, a novi dobiva sljedeću boju po redu. Kalendar osobnog računa e-pošte preuzima svaki događaj s računa jednom, i odonda je taj događaj vaš u Ponistri. Kalendar organizacije, koji stiže s poslužitelja tvrtke, samo se čita: označen je lokotom {t:calendar.readOnly}, ne može mu se promijeniti naziv ni obrisati ga, a mijenja mu se samo boja.

Obrisani kalendar nestaje sa svim svojim događajima. Kad prestanete pratiti kalendar računa, Ponistra uklanja svoju kopiju njegovih događaja, a kod pružatelja oni ostaju; ponovno praćenje vraća kalendar odmah, a događaje s idućim preuzimanjem.

Ako se račun ne može dohvatiti, ispod popisa piše račun i razlog.

## Ograničenja

- Brisanje kalendara je trajno.
- Kalendar organizacije ne briše se i ne prestaje pratiti u Ponistri.

## Povezano

- [Kalendar](help:calendar/overview)
- [Događaji](help:calendar/events)
