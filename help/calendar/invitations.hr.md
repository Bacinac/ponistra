# Pozvani i odgovori

Događaju dodajete pozvane osobe, koje dobivaju pozivnicu e-poštom, a na pozive drugih odgovarate iz kalendara.

## Kako se koristi

### Pozivanje

1. U događaju, u polju {t:calendar.field.attendees}, upišite osobe kao primatelje poruke.
2. Ako je netko od kolega u to vrijeme zauzet, ispod polja piše {t:calendar.busyThen} s njihovim imenima. Odaberite jedan od slobodnih termina, promijenite vrijeme sami ili ih ipak pozovite.
3. Pritisnite {t:tree.save}. Pozvanima odlazi pozivnica.

### Slobodni termini

1. Kad je netko od pozvanih u odabrano vrijeme zauzet ili odsutan, ili je zauzeta soba koju ste označili, ispod soba pojavljuje se {t:calendar.offers}: prvi termini iste duljine u kojima ste slobodni vi, svi pozvani iz instalacije i sve označene sobe.
2. Pritisnite termin. Početak i završetak događaja prelaze na njega, a ponuda nestaje.
3. Ispod termina, uz {t:calendar.unknownThen}, stoje pozvani izvan instalacije.

### Tko je odgovorio

1. Otvorite događaj. Pod {t:calendar.attendees} stoji {t:calendar.organizer} i svaki pozvani s odgovorom: {t:calendar.status.accepted}, {t:calendar.status.tentative}, {t:calendar.status.declined} ili {t:calendar.status.needsAction}.

### Odgovor na poziv

1. Otvorite događaj na koji ste pozvani.
2. Pod {t:calendar.yourAnswer} pritisnite {t:calendar.respond.accepted}, {t:calendar.respond.tentative} ili {t:calendar.respond.declined}.

Na pozivnicu možete odgovoriti i u samoj poruci, kako opisuje [čitanje poruke](help:mail/reading).

## Kako radi

Pozivnica odlazi e-poštom s vašeg računa, i to s onoga s adresom organizatora ili, ako takvog nema, sa zadanog. Promijenite li vrijeme, mjesto ili drugo bitno, svi pozvani dobivaju novu pozivnicu; osobe koje ste samo dodali dobivaju pozivnicu same, a uklonjenima i svima kad događaj obrišete javlja se otkazivanje.

Pozivnica koja vam stigne poštom ulazi u vaš kalendar i čeka odgovor. Vaš odgovor odlazi organizatoru e-poštom, a za događaj kalendara organizacije preko poslužitelja organizacije. Odgovori pozvanih stižu poštom i upisuju se uz njihova imena, a promjena ili otkazivanje organizatora mijenja događaj u vašem kalendaru.

Provjera zauzetosti zna samo za korisnike ove instalacije i samo to da im je vrijeme zauzeto, ne i o čemu je riječ. Ne računaju se događaji koji nisu označeni kao zauzeti, otkazani događaji ni pozivi koje je osoba odbila.

Slobodni termini traže se od dana odabranog u događaju, a ako je taj dan već počeo, od sada. Nude se na puni sat i pola sata od početka radnog vremena, samo u radne dane instalacije i unutar njezina radnog vremena, koje određuje administrator, i ne preklapaju se međusobno. Uz događaje u kalendarima računa se i razdoblje odsutnosti. Kad uređujete postojeći događaj, on sam ne zauzima nikoga. Pozvani izvan instalacije ne utječu na ponudu jer se njihova zauzetost ne zna.

## Ograničenja

- Za slanje pozivnica treba račun e-pošte koji šalje izravno; račun spojen preko ActiveSynca ne šalje pozivnice.
- Pozvane mijenja samo organizator.
- Zauzetost osoba izvan instalacije nije poznata.
- Slobodni termini ne nude se za cjelodnevni događaj i traže se najviše dva mjeseca unaprijed; ako takvog nema, piše: {t:calendar.noOffers}
- Termin duži od radnog vremena instalacije ne može se ponuditi.

## Povezano

- [Događaji](help:calendar/events)
- [Čitanje poruke](help:mail/reading)
- [Pisanje poruke](help:mail/composing)
