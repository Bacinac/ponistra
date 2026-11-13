# Kalendar

Kalendar na jednom mjestu prikazuje događaje svih vaših kalendara, zadatke s rokom, praznike, rođendane kontakata i rezervacije soba koje pratite.

![Kalendar u prikazu mjeseca](shot:calendar-month)

## Kako se koristi

### Prikazi i kretanje

1. Otvorite [kalendar](/calendar) na traci s lijeve strane.
2. Iznad kalendara, u skupini {t:calendar.view}, birate prikaz: {t:calendar.view.month}, {t:calendar.view.week}, {t:calendar.view.day} ili {t:calendar.view.agenda}.
3. Strelicama {t:calendar.previous} i {t:calendar.next} idete za cijeli prikaz unatrag ili naprijed, a gumbom {t:calendar.today} vraćate se na današnji dan.
4. U lijevom stupcu mali mjesec vodi na bilo koji dan; njegove strelice {t:calendar.previousMonth} i {t:calendar.nextMonth} listaju mjesece.

### Što se vidi u kojem prikazu

- {t:calendar.view.month}: u svakom danu stoje do tri događaja, a „+” s brojem ostalih otvara taj dan. Broj dana otvara prikaz dana, a dvostruki klik na dan otvara novi događaj tog dana.
- {t:calendar.view.week} i {t:calendar.view.day}: događaji stoje po satima, a crta pokazuje trenutno vrijeme. Klik na sat otvara novi događaj u tom satu, a {t:calendar.addAllDay} na vrhu dana otvara događaj za cijeli dan.
- {t:calendar.view.agenda}: događaji sljedećih 30 dana jedan ispod drugoga.
- Klik na događaj otvara ga; događaj kalendara koji se samo čita otvara se pod naslovom {t:calendar.event}.

### Što se prikazuje

1. U lijevom stupcu uz {t:calendar.calendars} pritisnite {t:calendar.settings}. Otvara se popis vaših kalendara.
2. Kvačicom uz kalendar skrivate ili vraćate njegove događaje, a kvačicama {t:calendar.holidays} i {t:calendar.birthdays} birate prikazuju li se praznici i rođendani vaših kontakata.
3. Pod {t:calendar.resources} kvačicom uz sobu ili resurs dodajete u kalendar njegove rezervacije.
4. Pod {t:mail.mailboxes} otvarate kalendare [zajedničkog sandučića](help:mail/mailboxes) koji je podijeljen s vama, a {t:calendar.mailboxOwn} vraća vaše.

## Kako radi

Prikaz i dan zapisani su u adresi stranice, pa se poveznica na kalendar otvara upravo na tom prikazu. Na širokom zaslonu kalendar se otvara u prikazu mjeseca, a na mobitelu kao popis. Prikazi tjedna i dana otvaraju se na 7 sati ujutro.

Neizvjesni događaji prikazani su blijedo, otkazani prekriženo, a ponavljajući nose znak ponavljanja. Neradni dani su osjenčani. Zadaci s rokom stoje na danu roka i otvaraju se u prozoru zadatka. Rođendan vodi na kontakt. U tuđoj rezervaciji sobe koja je privatna ne vidi se naziv događaja.

Ono što ste skrili kvačicama pamti ovaj preglednik, a ne račun. Kalendar se osvježava sam čim se bilo koji njegov događaj promijeni, bilo ovdje, na mobitelu ili na poslužitelju organizacije.

## Ograničenja

- Skriveni kalendari i odabrane sobe vrijede samo u pregledniku u kojem ste ih odabrali.
- U prikazu mjeseca u danu stoje najviše tri događaja; ostali su u prikazu dana.

## Povezano

- [Događaji](help:calendar/events)
- [Kalendari](help:calendar/calendars)
- [Sobe i resursi](help:calendar/rooms)
- [Zadaci](help:tasks/overview)
- [Zajednički sandučići](help:mail/mailboxes)
