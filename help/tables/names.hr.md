# Naziv tablice

Naziv tablice omogućuje formulama da upućuju na tu tablicu iz drugih tablica dokumenta, kao na list radne knjige.

## Kako se koristi

1. Stanite u tablicu i u izborniku {t:commandGroup.table} odaberite {t:command.tableName} Otvara se dijalog {t:tableName.title}.
2. U polje {t:tableName.name} upišite naziv i pritisnite {t:tree.save}.
3. U formuli druge tablice na nju upućujete nazivom, uskličnikom i adresom, na primjer `Troškovi!B4`.

## Kako radi

Ispod polja dijalog javlja zašto naziv nije prihvatljiv: kad je predug, sadrži nedopuštene znakove ili ga već ima druga tablica u dokumentu. Velika i mala slova pritom se ne razlikuju. Naziv tablice uvezene iz Excela je naziv lista.

## Ograničenja

- Naziv ima najviše 31 znak i ne sadrži znakove `[ ] : * ? / \`.
- Dok formule upućuju na tablicu, naziv se ne može ukloniti.

## Povezano

- [Tablice](help:tables/overview)
- [Podaci u tablici](help:tables/data)
