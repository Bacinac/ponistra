# Čekanje odgovora

Poruka koju ste poslali vraća se na vrh pristigle pošte ako do odabranog datuma nitko nije odgovorio.

## Kako se koristi

### Pri pisanju poruke

1. U [obrascu za pisanje](help:mail/composing) pritisnite ikonu pješčanog sata, {t:mail.await}.
2. Otvara se pitanje {t:mail.awaitAsk}
3. Odaberite {t:when.tomorrow} ili {t:when.monday}, ili upišite {t:when.day} i {t:when.time} pa potvrdite.
4. Uz gumbe piše do kada se čeka. Križić uz taj tekst, {t:mail.unawait}, poništava čekanje.
5. Pošaljite poruku, odmah ili [kasnije](help:mail/later).

### Na već poslanoj poruci

1. U mapi poslane pošte otvorite poruku.
2. Na traci iznad nje pritisnite {t:mail.await} i odaberite vrijeme.
3. Dok se čeka, iznad poruke piše do kada, a redak u popisu nosi pješčani sat.
4. Pritisnite {t:mail.unawait} ako vam odgovor više ne treba.

### Kad se poruka vrati

1. Poruka je na vrhu pristigle pošte, nepročitana, s oznakom {t:mail.unanswered}, a u retku su primatelji umjesto pošiljatelja.
2. Želite li čekati dalje, otvorite je i ponovno pritisnite {t:mail.await}.
3. Inače je premjestite ili izbrišite kao svaku drugu poruku.

## Kako radi

Datum čuva poslužitelj, pa se poruka vraća i kad su svi vaši uređaji isključeni. Na taj datum Ponistra provjeri pristiglu poštu: ako je netko odgovorio u niti te poruke, ne događa se ništa i čekanje završava. Ako nije, poruka se vraća i dobivate [obavijest](help:account/notifications).

Odgovorom se smatra poruka u niti koju je napisao netko drugi. Poslužitelji koji prepisuju oznake poruka ne ostavljaju nit koja se može pratiti, pa se odgovorom smatra i poruka s istim predmetom koja je stigla poslije od nekoga kome ste pisali.

Automatske poruke nisu odgovor: obavijesti o odsutnosti, izvještaji o neisporuci i poruke s adresa na koje nitko ne čita. Ni emoji reakcija nije odgovor.

## Ograničenja

- Čekati se može samo na poruku iz poslane pošte ili na onu koja se već vratila bez odgovora.
- Poruka koja se vrati nalazi se u pristigloj pošti umjesto u poslanoj, jer je u Ponistri svaka poruka u jednoj mapi. Kopija kod pružatelja ostaje gdje je bila.
- Poruka u smeću ili neželjenoj pošti ne vraća se.
- Datum čekanja mora biti nakon trenutka slanja: {t:error.mail_awaited_before_sending}
- Odgovor koji ste trajno izbrisali prije tog datuma Ponistra više ne vidi.
- Bez mreže se čekanje ne može postaviti ni ukinuti na otvorenoj poruci ([Rad bez mreže](help:account/offline)).

## Povezano

- [Pisanje poruke](help:mail/composing)
- [Slanje kasnije](help:mail/later)
- [Odgoda poruke](help:mail/snoozing)
- [Čitanje poruke](help:mail/reading)
- [Rad bez mreže](help:account/offline)
