# Slike i PDF u dokumentu

U dokument umećete slike i PDF datoteke iz svojih mapa ili s računala, mijenjate im veličinu, poravnanje i opis, a sliku možete i urediti.

## Kako se koristi

### Slika

1. U izborniku {t:editor.insert} odaberite {t:command.image}.
2. U dijalogu {t:image.insert} pritisnite {t:file.fromComputer} ili odaberite sliku iz mapa.
3. Sliku možete i zalijepiti ili povući u tekst.
4. Pritisnite sliku i povucite ručicu na njezinu rubu za veličinu. Poravnanje birate u izborniku {t:editor.align}.

### Naredbe nad slikom

1. Pritisnite sliku. Na traci alata pojavljuje se izbornik {t:commandGroup.image}.
2. {t:command.imageAlt} otvara polje za kratki opis onoga što slika prikazuje. Pritisnite {t:tree.save}.
3. {t:command.imageEdit} otvara dijalog za obrezivanje, okretanje, ton i oznake. Pritisnite {t:image.apply}.
4. {t:command.deleteImage} uklanja sliku iz dokumenta.

### PDF

1. U izborniku {t:editor.insert} odaberite {t:command.pdf}
2. U dijalogu {t:pdf.insert} pritisnite {t:file.fromComputer} ili odaberite PDF iz mapa.
3. Pritisnite PDF pa u izborniku {t:commandGroup.pdf} na traci alata odaberite {t:command.pdfPages} U dijalogu {t:pdf.pages} upišite {t:pdf.firstPage} i {t:pdf.lastPage} pa pritisnite {t:tree.save}.
4. {t:command.pdfOpen} otvara PDF na zasebnoj stranici, a {t:command.deletePdf} ga uklanja iz dokumenta.

## Kako radi

Umetnuta slika ili PDF kopija je datoteke: kasnije promjene izvorne datoteke ne mijenjaju dokument. Datoteka odabrana s računala sprema se samo u dokument, a ne i u mape. Slike zalijepljene s weba preuzima poslužitelj. Slike koje Word drži u datotekama na vašem računalu ne mogu se zalijepiti, pa Ponistra javlja da ih umetnete kao datoteke.

Uređena slika sprema se kao nova slika u dokumentu, a prethodna ostaje u verzijama. Opis slike čitaju čitači zaslona i tražilica.

## Ograničenja

- Neke vrste slika ne mogu se uređivati, pa dijalog to javlja.
- PDF u dokumentu prikazuje samo raspon stranica koji odaberete, od prve do zadnje.

## Povezano

- [Uređivanje slike](help:files/image-editor)
- [Umetanje](help:text/insert)
- [Verzije](help:documents/versions)
