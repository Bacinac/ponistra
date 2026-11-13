# PDF datoteke

PDF se čita u Ponistri stranicu po stranicu, s pretragom teksta i sadržajem datoteke, a da se sama datoteka ne mijenja.

## Kako se koristi

### Kretanje po stranicama

1. Otvorite PDF iz mape. Stranice se nižu jedna ispod druge.
2. U polje {t:pdf.page} upišite broj stranice i pritisnite {k:Enter}. Uz polje piše ukupan broj stranica.
3. Pod {t:zoom.label} birate {t:zoom.page} ili {t:zoom.width}.
4. Kad PDF ima vlastiti sadržaj, on se prikazuje u lijevom stupcu, a pritisak na naslov vodi na njegovu stranicu.

### Traženje u datoteci

1. Pritisnite {t:pdf.find} na traci ili {k:Mod-f}.
2. Upišite tekst. Pogoci se ističu na stranicama, a uz polje piše koji je pogodak od koliko ukupno, odnosno {t:pdf.find.none}.
3. {t:pdf.find.next} ili {k:Enter} vodi na sljedeći pogodak, a {t:pdf.find.previous} ili {k:Shift-Enter} na prethodni.
4. {t:pdf.find.close} ili {k:Escape} zatvara pretragu.

### Datoteka zaštićena lozinkom

1. Kad PDF traži lozinku, otvara se dijalog {t:pdf.locked}.
2. Upišite {t:pdf.password} i pritisnite {t:pdf.unlock}. Za pogrešnu lozinku dijalog javlja: {t:pdf.wrongPassword}
3. Ako odustanete, datoteka se ne prikazuje, a gumb {t:pdf.unlock} ponovo traži lozinku.

## Kako radi

Pretraga ne razlikuje velika i mala slova ni dijakritičke znakove. Poveznice u PDF-u vode na mjesto u datoteci ili otvaraju vanjsku adresu u novoj kartici. Bilješke i komentari koje je PDF donio iz drugih programa prikazuju se na njegovim stranicama.

Na traci su i alati za bilješke, komentare i zacrnjivanje, a obrasci se ispunjavaju izravno na stranici. Sve se to čuva uz datoteku, a izvorna datoteka ostaje kakva je učitana.

## Ograničenja

- U PDF zaštićen lozinkom ne upisuju se bilješke ni vrijednosti obrasca, a njegove se stranice ne mogu preslagivati.
- Kad datoteka zabranjuje izmjene sadržaja, ne može se zacrniti.

## Povezano

- [Bilješke i komentari u PDF-u](help:pdf/notes)
- [Obrasci u PDF-u](help:pdf/forms)
- [Zacrnjivanje](help:pdf/redaction)
- [Slaganje stranica](help:pdf/pages)
- [Prepoznavanje teksta](help:pdf/ocr)
- [Datoteke](help:files/overview)
