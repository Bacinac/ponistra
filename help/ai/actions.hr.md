# Radnje i Claude

Radnje su gotovi zahvati nad tekstom, tablicom ili cijelim dokumentom, od kojih neke izvodi model Claude tvrtke Anthropic.

## Kako se koristi

### Pokretanje radnje

1. Označite tekst ili stavite kursor u tablicu na koju se radnja odnosi.
2. Desnim klikom ili dugim pritiskom otvorite izbornik i odaberite radnju. Radnje nad tablicom nalaze se i u izborniku {t:commandGroup.table} na alatnoj traci.
3. Radnju možete potražiti i po nazivu u kutiji za pretragu dok je dokument otvoren.

### Prvo slanje Claudeu

1. Kad radnja treba Claudea, a dokument to još nije odobrio, otvara se dijalog {t:ai.consent.heading}
2. Odaberite {t:ai.consent.once} ili {t:ai.consent.always}.
3. Odobrenje za dokument povlačite u izborniku dokumenta: {t:ai.consent.withdraw}

### Tijek i poništavanje

1. Dok radnja traje, na dnu stranice stoji njezin naziv, a dok Claude piše i {t:run.writing}
2. Pritisnite {t:run.stop} da Claude stane nakon koraka na kojem jest. Do tada gumb prikazuje: {t:run.stopping}
3. Kad radnja završi, piše {t:run.done} ili {t:run.stopped} s nazivom radnje.
4. Pritisnite {t:run.undo} da vratite sve što je radnja promijenila.

## Kako radi

Radnje bez modela, poput zbrajanja stupaca, izvode se odmah na poslužitelju. Radnje s modelom šalju Claudeu tekst na koji se odnose, a Claude piše u pozadini, pa možete nastaviti raditi. Radnju vide svi koji su u dokumentu, s imenom osobe koja ju je pokrenula; ako ju je pokrenuo vanjski agent, uz ime piše i agent {t:run.via} osoba.

Odobrenje {t:ai.consent.always} ostaje uz dokument i vrijedi za svakoga tko ga smije uređivati, dok ga netko ne povuče. Odobrenje {t:ai.consent.once} vrijedi samo za tu radnju.

Ako radnja ne uspije, vraća se sve što je do tada napisala. Zaustavljena radnja čuva ono što je napisala do zaustavljanja. {t:run.undo} vraća promjene radnje, a ono što su drugi u međuvremenu napisali ostaje; radnja se poništava samo jednom.

## Ograničenja

- Radnje pokreće samo onaj tko smije uređivati dokument.
- Dok umjetna inteligencija nije uključena za instalaciju, radnje s modelom su onemogućene i uz njih piše: {t:ai.off}
- Zaustaviti se mogu samo radnje s modelom.
- Bez mreže radnje su onemogućene ([Rad bez mreže](help:account/offline)).

## Povezano

- [Pisanje s Claudeom](help:ai/writing)
- [Prijedlozi](help:ai/proposals)
- [Radnje nad tablicom](help:ai/tables)
- [Pristanci](help:ai/consents)
