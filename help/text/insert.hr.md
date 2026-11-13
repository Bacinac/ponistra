# Umetanje

Izbornik {t:editor.insert} na traci alata i kosa crta „/” u tekstu umeću slike, tablice, grafikone, sadržaj, prijelome, bilješke i druge dijelove dokumenta.

## Kako se koristi

### Iz izbornika

1. Stanite na mjesto u tekstu.
2. Na traci alata otvorite {t:editor.insert} i odaberite što umećete.
3. Za {t:command.table} prijeđite mišem ili strelicama po mreži do željenog broja stupaca i redaka pa ga odaberite.

### Kosom crtom

1. Na početku retka ili nakon razmaka upišite „/”.
2. Nastavite tipkati dio naziva, na primjer „/tab” za tablicu.
3. Strelicama odaberite stavku i pritisnite {k:Enter} ili {k:Tab}. {k:Escape} zatvara popis.

### Sadržaj

1. Stanite na mjesto za sadržaj i iz izbornika {t:editor.insert} odaberite {t:command.contents}.
2. Sadržaj nabraja naslove dokumenta s njihovim brojevima.

## Kako radi

U izborniku su {t:command.image}, {t:command.pdf} i {t:command.chart} te {t:command.link}, {t:command.table}, {t:command.contents}, {t:command.horizontalRule}, prijelomi, {t:command.speakerNotes}, {t:command.tab}, {t:command.header} i {t:command.footer} te {t:command.footnote} i {t:command.endnote}. Nude se samo naredbe koje imaju smisla na mjestu na kojem ste: u tablici, zaglavlju ili bilješci izbornik je kraći.

Sadržaj prati naslove svih kartica dokumenta i mijenja se kad ih mijenjate. Dok dokument nema naslova, sadržaj to kaže. Kad kosoj crti ne odgovara nijedna stavka, popis to javlja, a „/” ostaje običan znak.

## Ograničenja

- Umetati može samo onaj tko smije uređivati dokument.
- Kosa crta otvara popis samo na početku retka ili nakon razmaka, pa u adresama i datumima ostaje znak.

## Povezano

- [Poveznice](help:text/links)
- [Slike i PDF u dokumentu](help:text/images)
- [Postavke stranice](help:text/page)
- [Bilješke](help:text/notes)
