# Oblikovanje teksta

Odabranom tekstu dajete podebljanje, kurziv, podcrtavanje, precrtavanje, indeks ili eksponent, boju i boju isticanja.

## Kako se koristi

### Oblik slova

1. Odaberite tekst.
2. Na traci alata pritisnite {t:command.bold} ({k:Mod-b}), {t:command.italic} ({k:Mod-i}), {t:command.underline} ({k:Mod-u}) ili {t:command.strike} ({k:Shift-Mod-x}).
3. {t:command.subscript} ({k:Mod-,}) i {t:command.superscript} ({k:Mod-.}) spuštaju ili podižu tekst.
4. Isti gumb ili prečac ponovno uklanja oblik.

### Boje

1. Odaberite tekst.
2. Otvorite izbornik {t:commandGroup.color} ili {t:commandGroup.highlight} na traci alata.
3. Odaberite boju: {t:color.gray}, {t:color.red}, {t:color.orange}, {t:color.yellow}, {t:color.green}, {t:color.teal}, {t:color.blue} ili {t:color.purple} za tekst, a za isticanje i {t:color.pink}.
4. {t:color.auto} vraća tekstu boju iz stila, a {t:color.none} uklanja isticanje.

### Uklanjanje oblikovanja

1. Odaberite tekst.
2. Pritisnite {t:command.clearFormatting} ({k:Mod-Space} ili {k:Mod-\}).

## Kako radi

Kad ništa nije odabrano, oblik vrijedi za tekst koji upravo počinjete pisati. Gumb na traci istaknut je kad odabrani tekst već ima taj oblik.

{t:command.clearFormatting} uklanja oblik slova i boje, ali ne i poveznice, a odlomcima vraća poravnanje, uvlake i tabulatore iz stila. Font, veličina i razmak dolaze iz [stila odlomka](help:text/styles), pa se mijenjaju ondje, za sve odlomke istog stila odjednom.

Kad naredbe tražite u kutiji za pretragu, boje su naredbe {t:command.color} i {t:command.highlight} s nazivom boje.

Boje se prikazuju prilagođene svijetloj ili tamnoj temi sučelja, a u izvozu i ispisu dobivaju svoju izvornu vrijednost.

## Ograničenja

- Font i veličina slova ne biraju se za pojedine riječi, nego za stil odlomka.
- Boje se biraju samo iz ponuđenih.

## Povezano

- [Stilovi i tema](help:text/styles)
- [Popisi](help:text/lists)
- [Tipkovni prečaci](help:text/shortcuts)
