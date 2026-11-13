# Tablice

Tablica u dokumentu radi kao list proračunske tablice: ćelije drže tekst, brojeve i formule, a vrijednosti formula izračunava poslužitelj.

## Kako se koristi

![Tablica s poljem imena na traci alata](shot:tables-table)

### Pisanje u ćelije

1. Novu tablicu umećete iz izbornika {t:editor.insert} pomoću {t:command.table}.
2. Pritisnite ćeliju i pišite. {k:Tab} vodi u sljedeću ćeliju, {k:Shift-Tab} u prethodnu, a strelice u susjednu kad je kursor na rubu teksta.
3. {k:Shift-ArrowDown} i ostale strelice uz {k:Shift} proširuju odabir na više ćelija. Upisivanje preko odabranih ćelija prazni ih i piše u prvu, a {k:Delete} ih prazni.

### Formule

1. U praznu ćeliju upišite `=` i nastavite formulu, na primjer `=SUM(B2:B5)`.
2. Dok pišete formulu, pritisak na drugu ćeliju upisuje njezinu adresu. Ćelija druge tablice upisuje se s nazivom tablice, kao `Troškovi!B4`.
3. {k:Enter} sprema formulu i vodi u ćeliju ispod, {k:Tab} udesno, a {k:Escape} odustaje.

### Polje imena

1. Kad je kursor u tablici, na traci alata je {t:nameBox.label} s adresom odabranih ćelija.
2. Upišite adresu (`B4` ili `B4:D9`), naziv tablice s adresom ili definirani naziv i pritisnite {k:Enter}.
3. Na uskom zaslonu {t:command.goTo} ({k:Mod-g}) otvara dijalog {t:nameBox.title} s istim poljem i gumbom {t:nameBox.go}.

## Kako radi

Ćelija s formulom prikazuje izračunatu vrijednost, a formulu kad je otvorite. Broj stoji uz desni rub ćelije, upisan ili izračunat, osim kad mu zadate drugo poravnanje. Formula koju nije moguće pročitati ostaje otvorena, s objašnjenjem ispod ćelije. Argumente formule odvaja točka-zarez kad jezik dokumenta piše decimalni zarez, kao hrvatski, a zarez kad piše decimalnu točku, kao engleski.

Kad je tablica odabrana, kad su odabrane ćelije ili dok se piše formula, uz tablicu se vide slova stupaca i brojevi redaka. Čitači zaslona ćeliju najavljuju kao {t:table.cell} s adresom, a polje formule kao {t:table.formula} s adresom.

{k:Tab} u posljednjoj ćeliji dodaje novi redak.

## Ograničenja

- Polje imena vodi i u tablicu druge kartice, ali javlja grešku kad tablica ili naziv ne postoje ili kad je adresa izvan tablice.
- Uz pravo čitanja formule se mogu otvoriti, ali ne i mijenjati.

## Povezano

- [Retci i stupci](help:tables/rows-columns)
- [Podaci u tablici](help:tables/data)
- [Naziv tablice](help:tables/names)
- [Jezik dokumenta](help:text/language)
