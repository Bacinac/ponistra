# Slaganje stranica

Stranice PDF-a možete okretati, premještati, uklanjati i dopunjavati stranicama drugih PDF-ova, a rezultat spremiti kao novu datoteku.

## Kako se koristi

### Raspored stranica

1. Na stranici PDF-a pritisnite {t:pages.view}. Stranice se prikazuju kao sličice.
2. Pritisnite stranicu da biste je odabrali. Uz {k:Shift} odabirete raspon, uz {k:Mod} dodajete pojedinu stranicu, a {k:Mod-a} odabire sve.
3. Gumbi {t:pages.turnLeft} i {t:pages.turnRight} okreću odabrane stranice, a {t:pages.earlier} i {t:pages.later} pomiču ih za jedno mjesto.
4. Stranice možete i povući mišem na novo mjesto.
5. {t:pages.remove} ili {k:Delete} uklanja odabrane stranice.
6. {t:pages.undo} i {t:pages.redo} ({k:Mod-z} i {k:Mod-y}) vraćaju korake.

### Stranice iz druge datoteke

1. Pritisnite {t:pages.add}.
2. Odaberite {t:pages.add.tree} za PDF iz mapa ili {t:pages.add.computer} za PDF s računala. {t:pages.add.tree} otvara dijalog {t:pages.add.heading}.
3. Stranice dodane datoteke umeću se iza zadnje odabrane stranice ili na kraj. Dok se datoteka učitava, piše {t:pages.adding}

### Spremanje

1. {t:pages.save} sprema sve stranice u novom rasporedu, a {t:pages.extract} samo odabrane.
2. U dijalogu {t:pages.save.heading} ili {t:pages.extract.heading} potvrdite ili promijenite naziv.
3. Nova se datoteka sprema uz izvornu i otvara kad je gotova.

## Kako radi

Iznad sličica {t:pages.total} navodi ukupan broj stranica, a kad su neke odabrane, koliko ih je odabrano. Nova datoteka nosi bilješke i upisane vrijednosti obrasca sa stranica koje sadrži, a komentari ostaju uz datoteku na kojoj su napisani. Datoteke iz kojih su stranice uzete ne mijenjaju se.

PDF učitan s računala za dodavanje stranica sprema se u istu mapu kao zasebna datoteka. Kad su uklonjene sve stranice, prikaz javlja: {t:pages.empty}

Dok novi raspored nije spremljen, odlazak sa stranice pita {t:pages.leave} Gumb {t:pages.discard} odbacuje promjene.

## Ograničenja

- Stranice datoteke zaštićene lozinkom i datoteke koja to zabranjuje ne mogu se preslagivati ni preuzimati u druge datoteke. Gumb {t:pages.view} tada je onemogućen.
- Kad u mapi datoteke ne smijete dodavati, nova se datoteka sprema među vaše dokumente.

## Povezano

- [Spajanje datoteka](help:pdf/join)
- [PDF datoteke](help:pdf/viewer)
