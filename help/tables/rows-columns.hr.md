# Retci i stupci

Retke i stupce tablice dodajete, brišete, skrivate i zamrzavate, a ćelije spajate i razdvajate.

## Kako se koristi

### Dodavanje i brisanje

1. Stanite u ćeliju ili odaberite više ćelija.
2. Otvorite izbornik {t:commandGroup.table} na traci alata ili desnom tipkom miša.
3. Odaberite {t:command.rowAbove}, {t:command.rowBelow}, {t:command.columnLeft} ili {t:command.columnRight}.
4. {t:command.deleteRow} i {t:command.deleteColumn} brišu sve retke ili stupce odabranih ćelija, a {t:command.deleteTable} cijelu tablicu.

### Skrivanje

1. Odaberite ćelije u retcima ili stupcima koje želite skriti.
2. Odaberite {t:command.hideRows} ili {t:command.hideColumns}.
3. Za ponovni prikaz odaberite ćelije s obje strane skrivenih i odaberite {t:command.showRows} ili {t:command.showColumns}.

### Spajanje ćelija

1. Odaberite barem dvije ćelije i odaberite {t:command.mergeCells}.
2. Spojenu ćeliju vraćate u pojedinačne pomoću {t:command.splitCell}.

### Zamrzavanje redaka

1. Stanite u redak ispod onih koji trebaju ostati na vrhu.
2. Odaberite {t:command.freezeRows}. {t:command.unfreezeRows} ukida zamrzavanje.

## Kako radi

Zamrznuti retci ostaju na vrhu prikaza dok se tablica pomiče. U prikazu stranica ponavljaju se na vrhu svake stranice na koju se tablica nastavlja.

Novi redak ili stupac nastaje uz prvi ili posljednji redak ili stupac odabranih ćelija.

Skriveni retci i stupci skriveni su za sve korisnike dokumenta. Brojevi redaka preskaču skrivene retke, a crta u zaglavlju označava gdje su. Kad odabir doseže prvi ili posljednji redak tablice, {t:command.showRows} prikazuje i skrivene retke prije ili poslije njega.

## Ograničenja

- Ne mogu se obrisati svi retci ni svi stupci tablice: za to služi {t:command.deleteTable}.
- {t:command.freezeRows} nije dostupan u prvom retku.

## Povezano

- [Tablice](help:tables/overview)
- [Podaci u tablici](help:tables/data)
