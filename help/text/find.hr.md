# Traženje i zamjena

Pronalazi riječ ili izraz u cijeloj kartici, u tekstu, bilješkama i svim retcima tablica, i zamjenjuje ga na jednom mjestu ili svugdje odjednom.

## Kako se koristi

### Traženje

1. U dokumentu pritisnite {k:Mod-f} ili u kutiji za pretraživanje upišite {t:command.find}.
2. Upišite što tražite. Ako ste prije toga označili tekst, on je već upisan.
3. Svi rezultati u tekstu su istaknuti, a trenutačni je uokviren. Pokraj polja piše koji je to rezultat od koliko njih.
4. {k:Enter} ili {t:find.next} vodi na sljedeći rezultat, {k:Shift-Enter} ili {t:find.previous} na prethodni.
5. {t:find.case} traži samo s istim velikim i malim slovima, {t:find.words} samo riječi koje stoje same, ne kao dio duže riječi.
6. {k:Escape} ili gumb za zatvaranje vraća vas u tekst, na zadnji rezultat.

### Zamjena

1. Pritisnite {k:Ctrl-h} ili u kutiji za pretraživanje upišite {t:command.replace}. Iz traženja zamjenu otvara strelica {t:find.showReplace} na početku trake.
2. Upišite što tražite i, u polje {t:find.by}, čime to zamjenjujete.
3. {t:find.replace} (ili {k:Enter} u polju {t:find.by}) zamjenjuje trenutačni rezultat i prelazi na sljedeći.
4. {t:find.replaceAll} zamjenjuje sve rezultate u kartici.

## Kako radi

Traži poslužitelj, nad cijelom karticom kakva je spremljena, pa se nalaze i retci tablice koje preglednik još nije učitao. Kad je rezultat u takvom retku, tablica se pomakne do njegove ćelije i označi je.

Ćelija se pretražuje po onome što prikazuje: izračunata ćelija po izračunatoj vrijednosti, broj u svom obliku. Apostrof kojim je upisana vrijednost zadržana kao tekst ne pretražuje se i ostaje i nakon zamjene. Ćelija s jednim odlomkom zamjenjuje se tako da se njezin prikazani tekst s izvršenom zamjenom ponovno upiše; oblikovanje teksta u odlomcima ostaje kakvo je bilo na zamijenjenom mjestu.

Zamjena jednog rezultata i zamjena svih rezultata svaka je jedna promjena: {t:command.undo} ({k:Mod-z}) vraća sve što je ta zamjena promijenila. Rezultati se osvježavaju čim se kartica promijeni, i kad je mijenja netko drugi.

Prvi rezultat je onaj na mjestu kursora ili iza njega.

## Ograničenja

- Traži se samo u otvorenoj kartici, ne u zaglavljima i podnožjima, opisima slika ni drugim karticama dokumenta. Za traženje po svim dokumentima služi kutija za pretraživanje.
- Retci koje ste sakrili ne pretražuju se i zamjena ih ne mijenja.
- Ćelija čiju vrijednost izračunava formula pronalazi se, ali se ne zamjenjuje: {t:find.replace} je tada onemogućen, a {t:find.replaceAll} je preskače. Promijenite formulu.
- Prikazuje se najviše 1000 rezultata. Kad ih ima više, iza broja stoji +.
- Zamjena ne može sadržavati novi red.
- Kad dokument samo čitate, zamjena nije ponuđena.
- {t:find.none} znači da u kartici nema traženog teksta s odabranim uvjetima.

## Povezano

- [Prečaci](help:text/shortcuts)
- [Podaci tablice](help:tables/data)
- [Tražilica](help:start/search)
