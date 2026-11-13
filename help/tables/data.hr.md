# Podaci u tablici

Retke tablice sortirate po stupcu, ćelije popunjavate nizom ili kopijama, a tablicu udvostručujete s vrijednostima umjesto formula.

## Kako se koristi

### Sortiranje

1. Stanite u stupac po kojem sortirate. Za samo dio redaka odaberite ćelije u tim retcima.
2. Desnom tipkom miša ili u izborniku {t:commandGroup.table} na traci alata odaberite {t:command.sortAscending} ili {t:command.sortDescending}.

### Popunjavanje

1. Odaberite ćelije i povucite kvadratić u donjem desnom kutu odabira preko ćelija koje želite popuniti.
2. Za kopiranje bez niza odaberite ćelije i pritisnite {t:command.fillDown} ({k:Mod-d}) ili {t:command.fillRight} ({k:Mod-r}).

### Udvostručenje

1. Stanite u tablicu i odaberite {t:command.duplicateValues}.
2. Kopija se pojavljuje odmah ispod tablice i odabrana je.

## Kako radi

Sortiranje obuhvaća sve retke ispod zaglavlja, osim retka ukupno, ili samo odabrane retke. Brojevi dolaze prije teksta, tekst po abecedi jezika dokumenta, zatim logičke vrijednosti i greške; silazno je obrnuto. Prazne ćelije su uvijek na kraju, a retci s jednakim vrijednostima zadržavaju svoj redoslijed. Velika i mala slova ne razlikuju se. Ćelija spojena unutar jednog retka seli se sa svojim retkom.

Sortira poslužitelj, po vrijednostima koje su izračunate i spremljene, nad svim retcima tablice, i onima koje preglednik još nije učitao. Sortiranje je jedna promjena koju {t:command.undo} vraća. Dok je uključen vaš [filtar](help:tables/filter), sortiranje i popunjavanje zahvaćaju samo prikazane retke.

Povlačenje kvadratića nastavlja niz kad ga odabrane ćelije čine, a inače ih ponavlja, s izgledom i oblikom broja. Formula se pri popunjavanju pomiče sa svakom kopijom. {t:command.fillDown} kopira prvi redak odabira preko ostalih, a kad je odabran jedan redak, kopira redak iznad njega; {t:command.fillRight} isto čini sa stupcima.

{t:command.duplicateValues} upisuje u kopiju vrijednosti koje formule prikazuju, pa kopija više ne ovisi o izvornoj tablici.

## Ograničenja

- Retci koje povezuje ćelija spojena preko više redaka ne mogu se sortirati jer bi se razdvojili. Sortirajte samo retke iznad ili ispod nje.
- Spojene ćelije ne mogu se popunjavati ni služiti kao izvor popunjavanja.

## Povezano

- [Tablice](help:tables/overview)
- [Retci i stupci](help:tables/rows-columns)
- [Radnje nad tablicom](help:ai/tables)
