# Uređivanje slike

Sliku PNG, JPEG, WebP ili AVIF možete obrezati, okrenuti, smanjiti, tonski prilagoditi i označiti, a izvorna datoteka pritom ostaje kakva jest.

## Kako se koristi

### Izmjene

1. Otvorite sliku i pritisnite {t:image.edit}. Otvara se panel {t:image.editing}.
2. Pod {t:image.cropping} pritisnite {t:image.crop} i namjestite okvir na slici. Pod {t:image.ratio} birate {t:image.ratio.free}, 1:1, 4:3 ili 16:9, a {t:image.uncrop} vraća cijelu sliku.
3. Pod {t:image.turn} su {t:pages.turnLeft}, {t:pages.turnRight}, {t:image.flipAcross} i {t:image.flipDown}.
4. Pod {t:explorer.size} birate najdulju stranicu slike: {t:image.side.original} ili jednu od manjih. Ispod izbora piše kolika će biti kopija u pikselima.
5. Pod {t:image.tone} klizačima mijenjate {t:image.brightness}, {t:image.contrast} i {t:image.saturation}.

### Oznake

1. Pod {t:image.marks} odaberite {t:image.mark.arrow}, {t:image.mark.rectangle}, {t:image.mark.stroke}, {t:image.mark.text} ili {t:image.mark.blur}.
2. Povucite po slici. Za tekst pritisnite mjesto na slici, upišite tekst i pritisnite {k:Enter}.
3. Za sve oznake osim zamućenja birate boju i debljinu.
4. Pritisnite oznaku da biste je odabrali. Gumb {t:pdf.remove} ili tipka {k:Delete} uklanja je, a {k:Escape} odustaje od alata.

### Nova slika

1. Pritisnite {t:image.saveAs}
2. U dijalogu {t:image.saveAs.heading} potvrdite ili promijenite naziv. Predloženi naziv je naziv slike s dodatkom „(uređeno)”.
3. Nova se slika sprema uz ovu i odmah otvara.

## Kako radi

Izmjene i oznake ne mijenjaju datoteku: čuvaju se uz nju i iscrtavaju se svaki put kad se slika otvori. Svi koji imaju sliku otvorenu vide ih odmah. {t:command.undo} i {t:command.redo} ({k:Mod-z} i {k:Mod-y}) vraćaju vaše korake, a {t:image.reset} uklanja sve izmjene i oznake odjednom.

Preuzeta slika i ona otvorena u novoj kartici sadrže izmjene i oznake, u istom formatu kao izvornik. Nova slika iz {t:image.saveAs} postaje zasebna datoteka, a izvorna ostaje s izmjenama kakve jesu.

## Ograničenja

- {t:image.edit} vidi samo onaj tko smije uređivati sliku.
- Druge vrste slika prikazuju se, ali se ne mogu uređivati.
- Sliku koja se ne može pročitati stranica ne prikazuje, nego javlja: {t:image.unreadable}
- Kad u mapi slike ne smijete dodavati, nova se slika sprema među vaše dokumente.

## Povezano

- [Datoteke](help:files/overview)
- [Slike i PDF u dokumentu](help:text/images)
