# Izvještaj o uvozu

Dokument uvezen iz datoteke Officea ili LibreOfficea pamti izvornu datoteku i izvještava što uvoz nije prenio, a datoteku možete ponovno uvesti ili dodati u postojeći dokument.

## Kako se koristi

### Izvještaj

1. Otvorite uvezeni dokument. Iznad sadržaja stoji okvir {t:import.report} s porukom je li preneseno sve.
2. Ako nije, pritisnite {t:import.details} za popis onoga što nedostaje.
3. Kad ste izvještaj pregledali, pritisnite {t:import.dismiss} (križić u okviru).

### Izvorna datoteka

1. U okviru izvještaja ili u izborniku dokumenta pritisnite {t:import.original} za datoteku kakva je učitana.
2. Pritisnite {t:import.again} kad želite dokument pročitati iz izvorne datoteke iznova, pa potvrdite pitanje {t:import.againTitle}

### Uvoz u postojeći dokument

1. U izborniku dokumenta, iza naslova u putanji, odaberite {t:import.into}
2. Odaberite datoteku na računalu. Dok traje uvoz, iznad dokumenta piše {t:import.importing}
3. Kad uvoz završi, dijalog {t:import.report} kaže je li preneseno sve, a ako nije, navodi što nedostaje.

## Kako radi

Pojedinosti izvještaja dijele se u skupine. Pod {t:import.lost} nabrojeno je ono što Ponistra ne prikazuje ili prikazuje drukčije, na primjer grafikoni nepodržane vrste, uvjetno oblikovanje, makronaredbe, skriveni tekst ili prijelazi između slajdova, uz broj pojava kad ih je više. Za ćelije čija se izračunata vrijednost razlikuje od izvornika navode se njihove adrese. Pod {t:import.fonts} piše koji je font zamijenjen kojim, ili {t:import.fontDefault} kad je preuzet font dokumenta. Zatim slijede nazivi funkcija koje se ne računaju, izvorni kod makronaredbi samo za čitanje i broj prihvaćenih praćenih promjena ({t:import.accepted}).

Izvještaj vide samo oni koji smiju uređivati dokument. Kad ga netko od njih zatvori, nestaje za sve.

Ponovni uvoz najprije sprema trenutno stanje kao verziju, pa sadržaj kartica zamjenjuje onim što uvoz sada pročita iz izvorne datoteke. Komentari iz datoteke čitaju se iznova, a komentari dodani u Ponistri ostaju. Otvorene sesije uređivanja zatvaraju se, pa ih drugi korisnici ponovno otvaraju.

Uvoz u postojeći dokument dodaje kartice datoteke iza posljednje kartice dokumenta. Stilovi i oblici popisa koje dokument već ima zadržavaju svoj izgled, a tablica istog naziva kao neka u dokumentu dobiva naziv kopije.

## Ograničenja

- {t:import.again} i {t:import.into} dostupni su samo uz pravo uređivanja.
- {t:import.original} nije dostupno u dokumentu unutar mape {t:confined.label}.
- Makronaredbe se nikad ne izvršavaju, njihov se kod samo prikazuje.

## Povezano

- [Učitavanje datoteka](help:documents/upload)
- [Verzije](help:documents/versions)
- [Spremanje u drugi oblik](help:text/export)
