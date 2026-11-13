# Odgoda poruke

Poruka nestaje iz pristigle pošte i vraća se na njezin vrh u trenutku koji odaberete.

## Kako se koristi

### Odgoda

1. Otvorite poruku i na traci iznad nje pritisnite {t:mail.snooze}. Za više poruka odjednom [odaberite ih](help:mail/selecting) i pritisnite isto na traci odabira.
2. Otvara se pitanje {t:mail.snoozeAsk}
3. Odaberite {t:when.tomorrow} ili {t:when.monday}, ili upišite {t:when.day} i {t:when.time} pa potvrdite.

### Odgođene poruke

1. U lijevom stupcu Pošte otvorite mapu {t:mail.role.snoozed}. Mapa se pojavljuje nakon prve odgode.
2. Redak pokazuje kada se poruka vraća, a isto piše i iznad otvorene poruke.
3. Za promjenu vremena otvorite poruku, pritisnite {t:mail.snooze} i odaberite novo vrijeme.
4. Da biste poruku vratili odmah, pritisnite {t:mail.unsnooze}.

## Kako radi

Vrijeme čuva poslužitelj, pa se poruka vraća i kad su svi vaši uređaji isključeni. Provjera se obavlja svakih petnaest sekundi.

Kad dođe vrijeme, poruka odlazi u pristiglu poštu, na vrh popisa i kao nepročitana, bez obzira na to iz koje je mape odgođena, a [obavijest](help:account/notifications) dobivate kao za novu poruku. Datum poruke se ne mijenja.

Odgoda postoji samo u Ponistri. Kopija kod pružatelja pošte ostaje gdje je bila, pa je u njegovoj web-pošti ili drugom programu poruka i dalje u pristigloj pošti.

## Ograničenja

- Poruke iz poslane pošte, skica, smeća i neželjene pošte ne mogu se odgoditi.
- Ako odgođenu poruku premjestite u drugu mapu, odgoda prestaje.
- Vrijeme mora biti u budućnosti.
- Pravila po pošiljatelju ne pomiču odgođene poruke.
- Bez mreže se poruka ne može odgoditi ([Rad bez mreže](help:account/offline)).

## Povezano

- [Pregled pošte](help:mail/overview)
- [Čitanje poruke](help:mail/reading)
- [Rad s više poruka](help:mail/selecting)
- [Slanje kasnije](help:mail/later)
- [Rad bez mreže](help:account/offline)
