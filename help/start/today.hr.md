# Danas

Stranica Danas na jednom mjestu prikazuje raspored dana, zadatke na redu, poštu koja čeka i dokumente kojima ste se nedavno bavili.

## Kako se koristi

### Pregled dana

1. Pritisnite {t:rail.today} na traci modula ili znak Ponistre na njezinu vrhu.
2. Ispod datuma piše koliko danas imate događaja, koji je praznik i koliko je rođendana.
3. U okviru {t:today.schedule} pritisnite događaj da biste ga otvorili. Pritisak na rođendan otvara kontakt slavljenika.
4. Pomoću {t:rail.calendar} u okviru rasporeda otvarate današnji dan u kalendaru.
5. U malom mjesecu u lijevom stupcu pritisnite dan da biste ga otvorili u kalendaru. Mjesece mijenjate strelicama {t:calendar.previousMonth} i {t:calendar.nextMonth}.

### Novi događaj i zadatak

1. Za događaj danas pritisnite {t:calendar.newEvent} u zaglavlju.
2. Za zadatak s današnjim rokom pritisnite plus uz naslov {t:tasks.due.title}.
3. Pomoću {t:tasks.title} otvarate sve zadatke.

### Pošta i dokumenti

1. U okviru {t:today.mail} pritisnite poruku da biste je otvorili, ili {t:rail.mail} za cijelu poštu.
2. U okviru {t:today.recent} pritisnite dokument, ili {t:rail.documents} za sve dokumente.
3. Ako ste nešto dodali u {t:favourites.title}, ispod je i taj okvir. Broj uz njegov naslov otvara cijeli popis.

## Kako radi

Raspored prikazuje događaje cijelog dana prvi, a zatim ostale po vremenu početka. Crvena crta s oznakom {t:today.now} i trenutnim vremenom stoji između prošlih i budućih događaja, a prošli su blijedi. Sljedeći ili tekući događaj je istaknut i uz njega piše koliko je još do početka; ako ima sastanak na mreži, uz njega je gumb {t:meeting.join}. Otkazan događaj je precrtan. Poziv na koji još niste odgovorili nosi oznaku {t:calendar.awaiting}. Kalendari, praznici i rođendani koje ste sakrili u kalendaru ovdje se ne prikazuju.

Zadaci na redu su nedovršeni zadaci kojima je rok danas ili je već prošao.

Pošta koja čeka su nepročitane poruke u pristiglim mapama od ljudi kojima ste već pisali i poruke koje ste označili zvjezdicom u posljednja 2 tjedna, najnovije prve. Odgođene poruke nisu među njima dok se ne vrate. Prikazuje se 5 poruka, a broj uz naslov kaže koliko ih je ukupno.

Nedavni dokumenti su 10 dokumenata i datoteka koje smijete čitati, poredanih po zadnjoj izmjeni, bez obzira na to tko ih je mijenjao. Iz omiljenog se prikazuje najviše 8 stavki.

Gumb za novi događaj prikazuje se samo ako imate kalendar u koji se može pisati.

## Ograničenja

- Dok nema događaja, piše: {t:today.noEvents}
- Dok nijedna poruka ne čeka, piše: {t:today.noMail}
- Dok nema dokumenata, piše: {t:today.none}
- Kad nijedan zadatak nije na redu, piše: {t:tasks.due.none}

## Povezano

- [Okvir aplikacije](help:start/overview)
- [Kalendar](help:calendar/overview)
- [Zadaci](help:tasks/overview)
