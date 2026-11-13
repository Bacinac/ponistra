# Izgled tablice

Izgled tablice zadaje crte, boje i isticanje dijelova tablice jednim odabirom, umjesto oblikovanja ćelije po ćeliju.

## Kako se koristi

### Izgled

1. Stanite u tablicu i u izborniku {t:commandGroup.table} otvorite {t:command.tableDesign}.
2. Odaberite {t:tableDesign.grid}, {t:tableDesign.lines}, {t:tableDesign.bands}, {t:tableDesign.header} ili {t:tableDesign.plain}.

### Dijelovi tablice

1. U istom izborniku, ispod izgleda, uključite ili isključite {t:tablePart.header}, {t:tablePart.totals}, {t:tablePart.firstColumn}, {t:tablePart.lastColumn}, {t:tablePart.rowBands} ili {t:tablePart.columnBands}.
2. Uključeni dijelovi istaknuti su prema odabranom izgledu.

## Kako radi

Nova tablica dobiva izgled {t:tableDesign.grid}. Kad promijenite izgled, uključeni dijelovi ostaju uključeni. Izgled tablice uvezene iz Worda, Excela ili PowerPointa čuva se. Pri spremanju u Excel izgled postaje Excelova tablica gdje ga Excel može nacrtati, a inače se prenosi ćeliju po ćeliju.

Kad naredbe tražite u kutiji za pretragu, izgledi su pod {t:command.tableDesign}, a dijelovi pod {t:command.tablePart}.

## Ograničenja

- Uz {t:tableDesign.plain} tablica nema izgleda, pa se dijelovi ne mogu uključiti.

## Povezano

- [Oblik broja i ispuna](help:tables/formats)
- [Tablice](help:tables/overview)
- [Spremanje u datoteku](help:text/export)
