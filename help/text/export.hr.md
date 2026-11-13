# Spremanje u datoteku

Dokument se sprema kao datoteka Worda, Excela, PowerPointa, PDF-a ili Ponistre, za slanje ili rad u drugom programu.

## Kako se koristi

1. Pritisnite naslov dokumenta u putanji i u izborniku odaberite {t:save.as}.
2. Odaberite oblik: {t:save.docx}, {t:save.pdf}, {t:save.xlsx}, {t:save.csv}, {t:save.pptx}, {t:save.ponx} ili {t:save.ponxVersions}.
3. Dok se datoteka izrađuje, iznad dokumenta piše {t:save.pending} Gotova datoteka preuzima se u preglednik.

Dokument učitan iz Officeove datoteke s makronaredbama nudi i {t:save.docm}, {t:save.xlsm} ili {t:save.pptm}, prema obliku izvorne datoteke.

## Kako radi

Datoteku izrađuje poslužitelj. Prije izrade izračunavaju se formule u tablicama.

- {t:save.docx}: svaka kartica i svaki njezin odjeljak počinju na novoj stranici, s postavkama stranice, zaglavljima i podnožjima. Prenose se stilovi, popisi, tablice, slike, grafikoni, bilješke, sadržaj, polja stranice, komentari i prijedlozi, koji u Wordu postaju praćene promjene. Nazivi kartica ne prenose se.
- {t:save.pdf}: stranice su složene kao za ispis, a stranice PDF datoteka umetnutih u dokument ulaze onakve kakve jesu.
- {t:save.xlsx}: svaka tablica postaje list Excela, redom kroz kartice, s formulama, oblicima brojeva, nazivima, izgledom i grafikonima. Tekst oko tablica ne prenosi se. Tablica dulja od 1 048 576 redaka, koliko stane na list Excela, nastavlja se na sljedećim listovima.
- {t:save.csv}: prva tablica dokumenta, u svakoj ćeliji ono što ćelija prikazuje. Stupci su odvojeni točkom sa zarezom ako dokument ima decimalni zarez, inače zarezom.
- {t:save.pptx}: slajdovi svih kartica redom, a svaka kartica postaje odjeljak prezentacije. Prenose se predložak slajdova, bilješke govornika i skriveni slajdovi. Prijedlozi se ne prenose: datoteka sadrži tekst kakav je bio prije njih.
- {t:save.ponx}: vlastita datoteka Ponistre, u kojoj ništa ne nedostaje: kartice, stilovi, komentari, prijedlozi, slike, PDF datoteke i datoteka iz koje je dokument učitan. {t:save.ponxVersions} uz to nosi i sve verzije dokumenta.

Makronaredbe izvorne datoteke prenose se u spremljenu datoteku nepromijenjene. Izrada koja traje dulje od sekunde prikazuje se u donjem desnom kutu, gdje se može otkazati. Svako spremanje bilježi se u dnevniku pristupa dokumentu.

## Ograničenja

- {t:save.as} nije dostupan u mapi {t:confined.label} onima koji nisu njezini vlasnici.
- {t:save.xlsx} i {t:save.csv} javljaju grešku kad dokument nema nijednu tablicu.
- {t:save.docx} i {t:save.pptx} javljaju grešku kad dokument ima tablicu s više od 200 000 ćelija. Takvu tablicu spremite u {t:save.xlsx} ili {t:save.ponx}.

## Povezano

- [Ispis](help:text/print)
- [Učitavanje datoteka](help:documents/upload)
- [Dijeljenje](help:documents/sharing)
- [Verzije](help:documents/versions)
