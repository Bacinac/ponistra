# Događaji

Događaj ima naziv, vrijeme, kalendar u koji pripada i po želji mjesto, opis, podsjetnik i sastanak na mreži.

## Kako se koristi

### Novi događaj

1. Pritisnite {t:calendar.newEvent}, kliknite sat u prikazu tjedna ili dana ili dvaput kliknite dan u prikazu mjeseca.
2. Upišite {t:calendar.field.summary}. Ostalo je već popunjeno: novi događaj počinje u 9 sati i traje sat vremena, a kliknuti sat postavlja svoj početak.
3. Po potrebi promijenite {t:calendar.field.startDay}, {t:calendar.field.startTime}, {t:calendar.field.endDay} i {t:calendar.field.endTime} ili označite {t:calendar.allDay}.
4. U polju {t:calendar.field.calendar} birajte kalendar, a upišite i {t:calendar.field.location} i {t:calendar.field.description} ako ih želite.
5. Pritisnite {t:tree.save}.

### Ostale postavke događaja

- {t:calendar.field.busy}: vrijeme događaja računa se kao zauzeto kad netko u instalaciji provjerava jeste li slobodni. Isključite za događaj koji vam ne zauzima vrijeme.
- Pozvani koji su u to vrijeme odsutni navedeni su uz polje pozvanih, s danom povratka ([Odsutnost](help:mail/away)), a ispod soba nude se termini u kojima su svi slobodni ([Pozvani i odgovori](help:calendar/invitations)).
- {t:calendar.field.private}: drugi u rezervaciji sobe ne vide naziv događaja, a kalendari koji ga primaju dobivaju ga označenog kao privatnog.
- {t:calendar.field.reminder}: {t:calendar.reminder.none} ili vrijeme od trenutka događaja do jednoga dana prije.
- {t:calendar.field.repeat}: događaj koji se ponavlja, opisan u članku [Ponavljajući događaji](help:calendar/recurring).

### Sastanak na mreži

1. U dijelu {t:calendar.field.conference} pritisnite {t:meeting.add}. Ponistra otvara sastanak za taj događaj, a polje pokazuje {t:meeting.ours}.
2. {t:meeting.join} otvara sastanak, a {t:meeting.copyLink} sprema poveznicu za slanje; dok je poveznica kopirana, gumb kaže {t:meeting.copied}
3. Križić {t:meeting.remove} uklanja sastanak iz događaja.

### Postojeći događaj

1. Kliknite događaj u kalendaru i promijenite što treba, zatim pritisnite {t:tree.save}. Naslov prozora je {t:calendar.editEvent}.
2. {t:calendar.delete} odmah briše događaj.
3. {t:tasks.fromEvent} otvara novi zadatak s nazivom događaja i rokom na dan događaja, povezan s tim danom u kalendaru.
4. {t:tree.cancel} zatvara prozor bez promjena.

## Kako radi

Događaj se sprema u odabrani kalendar i odmah se vidi na svim vašim uređajima, a kalendari povezani s Ponistrom, poput onoga na mobitelu, primaju ga s idućim usklađivanjem. Podsjetnik se sprema uz događaj i prenosi se kalendarima na mobitelu i u programima povezanima s Ponistrom, koji vas na njega podsjećaju.

Sastanak u Ponistri otvara se uz vaš rad u zasebnom prozoru, a sastanak druge usluge u novoj kartici. Sastanak može dodati ili ukloniti samo organizator događaja, i to dok poveznica nije upisana u mjesto ili opis.

Događaj kalendara organizacije samo se čita: prozor ima naslov {t:calendar.event}, polja su onemogućena, a novi zadatak iz njega i dalje možete otvoriti.

## Ograničenja

- Naziv događaja ima najviše 200 znakova.
- Ponistra sama ne prikazuje podsjetnik; podsjećaju kalendari uređaja i programa koji su s njom povezani.
- Brisanje se ne traži potvrdom.

## Povezano

- [Kalendar](help:calendar/overview)
- [Pozvani i odgovori](help:calendar/invitations)
- [Ponavljajući događaji](help:calendar/recurring)
- [Sastanci](help:meetings/overview)
