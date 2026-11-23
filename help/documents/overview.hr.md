# Pregled dokumenata

{t:rail.files} drže vaše tekstove, tablice, prezentacije i datoteke u mapama, zajedno s onima koje dijelite s drugima.

## Kako se koristi

![Mapa s dokumentima i pregledom odabrane stavke](shot:documents-folder)

### Kretanje po mapama

1. Otvorite modul {t:rail.files} na traci modula.
2. U lijevom stupcu odaberite {t:tree.root}, {t:tree.company} ili {t:tree.shared}. Strelica uz mjesto otvara njegove mape, a uz mapu njezine podmape. Ispod njih su oznake, lokacije na mreži i radni prostor ([Datoteke](help:files/manager)); mapa se prikazuje isto, odakle god bila. Na mobitelu mape otvara gumb {t:frame.folders}, a {t:favourites.title}, {t:tree.company}, {t:tree.shared}, {t:notes.title}, {t:links.title}, {t:boards.title}, {t:vault.title} i {t:trash.title} stoje na vrhu stranice.
3. Pritisnite mapu u popisu ili stanite na nju i pritisnite {k:Enter}. Dvostruki pritisak otvara je i kad je uključen pregled uz popis.
4. Putanja iznad popisa vodi natrag u svaku nadređenu mapu.

### Nova stavka

1. Pritisnite {t:create.new} iznad popisa ili desnom tipkom miša pritisnite prazno mjesto u popisu.
2. Odaberite {t:tree.newDocument}, {t:create.folder} ili {t:create.link}.
3. Upišite {t:tree.name} i pritisnite {t:tree.create}. Novi se dokument odmah otvara.
4. Pomoću {t:create.upload} ili {t:create.uploadFolder} učitavate datoteke s računala, a pomoću {t:create.scan} papir snimljen mobitelom ([Skeniranje](help:pdf/scan)).

### Poredak popisa

1. Pritisnite naslov stupca: {t:tree.name}, {t:explorer.kind}, {t:explorer.updated} ili {t:explorer.size}.
2. Ponovni pritisak na isti stupac obrće smjer.

## Kako radi

Vrsta stavke vidi se po ikoni i u stupcu {t:explorer.kind}: {t:kind.folder}, {t:kind.document}, {t:kind.table}, {t:kind.slides}, {t:kind.file}, {t:kind.image}, {t:kind.text}, {t:kind.video}, {t:kind.audio}, {t:kind.board} ili {t:kind.other}. Za ostale datoteke stupac navodi i nastavak naziva. Dokument je tablica kad mu prva kartica sadrži samo tablice, a prezentacija kad ima vlastite rasporede slajdova.

Stupac {t:explorer.updatedBy} pokazuje tko je stavku zadnji mijenjao. Stupac {t:access.title} pokazuje tko osim vas može otvoriti stavku: {t:access.onlyMe}, {t:access.everyone} ili oznake osoba i grupa. Oznaka {t:access.wider} znači da stavka ima šira prava od mape u kojoj je. Lokot uz naziv označava mapu {t:confined.label}.

Dokument ili mapa koju izradite u {t:tree.root} pripada vama. Ono što izradite u tuđoj mapi preuzima prava te mape. Odabrani poredak pamti se u tom pregledniku i vrijedi za sve mape. Dvije mape usporedo, kartice, kopiranje, izrezivanje i lijepljenje rade kao u svakom izvoru [Datoteka](help:files/manager). Prazna mapa prikazuje: {t:tree.empty}

## Ograničenja

- {t:create.new} nije dostupno u mapi u kojoj imate samo pravo čitanja.
- Kad stavka ne postoji ili do nje nemate pristup, stranica prikazuje poruku i poveznicu {t:tree.backToRoot}.
- Na uskom zaslonu dio stupaca se ne prikazuje.

## Povezano

- [Rad sa stavkama](help:documents/organising)
- [Učitavanje datoteka](help:documents/upload)
- [Dijeljenje](help:documents/sharing)
