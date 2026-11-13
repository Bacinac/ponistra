# Filtar tablice

Filtar prikazuje samo retke tablice čije ćelije imaju odabrane vrijednosti ili ispunjavaju uvjet, i to samo vama.

## Kako se koristi

### Po vrijednosti ćelije

1. Stanite u ćeliju čiju vrijednost želite zadržati.
2. Desnom tipkom miša ili u izborniku {t:commandGroup.table} na traci alata odaberite {t:command.filterByValue}.

### Po vrijednostima stupca

1. Odaberite {t:command.filter} u stupcu koji filtrirate.
2. Pod {t:filter.values} ostavite označene vrijednosti čije retke želite vidjeti. Polje {t:filter.search} sužava popis, a {t:filter.all} označava ili odznačava sve prikazane vrijednosti. Prazne ćelije stoje pod {t:filter.empty}.
3. Pritisnite {t:filter.apply}.

### Po uvjetu

1. Odaberite {t:command.filter} u stupcu koji filtrirate, a zatim {t:filter.condition}.
2. U {t:filter.op} odaberite usporedbu: {t:filter.equals}, {t:filter.notEquals}, {t:filter.begins}, {t:filter.ends}, {t:filter.contains}, {t:filter.notContains}, {t:filter.greater}, {t:filter.greaterEqual}, {t:filter.less} ili {t:filter.lessEqual}.
3. Upišite {t:filter.value} i pritisnite {t:filter.apply}.

### Izmjena i uklanjanje

1. Uvjeti filtra stoje iznad tablice, po jedan za svaki stupac. Pritiskom na uvjet ({t:filter.edit}) otvarate ga za izmjenu, a pritiskom na × uklanjate ga.
2. U prozoru filtra {t:filter.clear} uklanja uvjet tog stupca.
3. {t:command.unfilter} uklanja sve uvjete tablice.

## Kako radi

Filtar se sprema za vašeg korisnika i za tu tablicu, pa vrijedi na svakom vašem uređaju i nakon ponovnog otvaranja. Drugi korisnici dokumenta vide sve retke. Filtrirati može i korisnik koji dokument samo čita.

Redak je prikazan kad nije skriven i ispunjava uvjete svih stupaca. Vrijednosti se uspoređuju onako kako ih ćelija prikazuje, bez razlike između velikih i malih slova. Usporedbe veće i manje zahvaćaju samo ćelije s brojem, a broj se upisuje kao u jeziku dokumenta. Uz svaku vrijednost na popisu stoji broj redaka koji je prikazuju među retcima koje propuštaju uvjeti ostalih stupaca.

Brojevi redaka zadržavaju svoje mjesto u tablici i dok je filtar uključen prikazani su u boji naglaska. Adrese u formulama i u okviru naziva uvijek se odnose na stvarne retke.

Sortiranje, popunjavanje, brisanje i skrivanje odabranih redaka mijenjaju samo prikazane retke. Kad izmjena ćelije promijeni ispunjava li redak uvjet, redak se odmah pojavljuje ili nestaje. Formule računaju nad svim retcima, i onima koje filtar ne prikazuje, a ispis i izvoz ne primjenjuju vaš filtar.

## Ograničenja

- Svaki stupac ima jedan uvjet: ili odabrane vrijednosti ili jednu usporedbu.
- Adresa retka koji filtar ne prikazuje javlja {t:filter.notShown}
- Popis vrijednosti prikazuje najviše 1000 različitih vrijednosti. Za ostale upotrijebite uvjet.
- Poruka {t:filter.refused} javlja se kad usporedba veće ili manje u polju {t:filter.value} nema broj.

## Povezano

- [Retci i stupci](help:tables/rows-columns)
- [Podaci u tablici](help:tables/data)
- [Tablice](help:tables/overview)
