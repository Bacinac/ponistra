# Sadržaj datoteka po vrsti

Arhive, poruke e-pošte, kontakti, kalendari, Markdown i slike koje preglednik sam ne prikazuje otvaraju se tako da se vidi što sadrže, a ne kao niz bajtova.

## Kako se koristi

1. U mapi pritisnite datoteku. Stranica datoteke prikazuje njezin sadržaj.
2. Stavka arhive ili privitak poruke preuzima se pritiskom na njezin naziv.
3. Kad je arhiva zaštićena lozinkom, stranica javlja {t:shown.locked} Upišite lozinku u polje {t:shown.password} i pritisnite {t:shown.open}.
4. Gumb {t:file.download} uvijek preuzima cijelu datoteku kakva je učitana.

Isti sadržaj, skraćen, prikazuje i [pregled stavke](help:documents/preview) uz popis mape.

## Kako radi

Vrstu određuju bajtovi datoteke, a ne njezin nastavak.

- Arhiva (ZIP, 7z, RAR, TAR, GZip, BZip2, XZ, Zstandard, LZ4, ISO, CAB, LHA, XAR) prikazuje popis mapa i datoteka s veličinom i datumom izmjene. Prazna arhiva javlja {t:shown.emptyArchive}
- Poruka e-pošte (EML, MHT i Outlookov MSG) prikazuje {t:mail.from}, {t:mail.to}, {t:mail.cc}, {t:mail.date}, privitke i tijelo poruke. Slike ugrađene u poruku EML prikazuju se, a vanjske slike i skripte ne učitavaju se.
- Kontakti (VCF) prikazuju se kao popis osoba s adresama, telefonima i slikom. Datoteka bez kontakata javlja {t:shown.noPeople}
- Kalendar (ICS) prikazuje događaje po vremenu, s mjestom i organizatorom. Događaj koji traje cijeli dan označen je s {t:calendar.allDay}, a onaj koji se ponavlja s {t:shown.repeats}. Datoteka bez događaja javlja {t:shown.noEvents}
- Markdown se prikazuje oblikovan, s naslovima, popisima i tablicama.
- Slike BMP, ICO, TIFF i PSD prikazuju se kao PNG. TIFF prolazi i [prepoznavanje teksta](help:pdf/ocr): kad završi, prikazuje se kao PDF sa svim stranicama i može se pretraživati.

Lozinka arhive ne sprema se nigdje. Vrijedi samo za taj prikaz, pa se upisuje ponovno nakon svakog otvaranja. Svako preuzimanje stavke ili privitka bilježi se u dnevniku pristupa, kao i preuzimanje cijele datoteke.

## Ograničenja

- Arhiva se prikazuje do 1 GiB veličine i s najviše 10 000 stavki.
- Pregled stavke prikazuje prvih 50 stavki arhive, a stranica datoteke sve.
- Kad je lozinka pogrešna, stranica javlja {t:error.archive_locked} Upišite ispravnu lozinku.
- U mapi {t:confined.label} stavke i privitci ne mogu se preuzeti.

## Povezano

- [Datoteke](help:files/overview)
- [Pregled stavke](help:documents/preview)
- [Prepoznavanje teksta](help:pdf/ocr)
