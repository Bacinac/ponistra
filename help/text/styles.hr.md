# Stilovi i tema

Stil odlomka određuje font, veličinu, boju, poravnanje, razmake i brojeve odlomka, a tema fontove cijelog dokumenta.

## Kako se koristi

### Stil odlomka

1. Stanite u odlomak.
2. Na traci alata u izborniku {t:editor.style} odaberite {t:command.paragraph}, {t:command.title}, {t:command.subtitle}, {t:command.heading1}, {t:command.heading2}, {t:command.heading3}, {t:command.heading4} ili vlastiti stil.
3. Naslov možete dobiti i tipkanjem: „# ” na početku retka daje {t:command.heading1}, „## ” {t:command.heading2} i tako dalje do četiri ljestve.

### Tema i stilovi

1. U izborniku dokumenta odaberite {t:styles.open} Otvara se dijalog {t:styles.title}.
2. Pod {t:styles.theme} odaberite {t:theme.ponistra}, {t:theme.classic}, {t:theme.office}, {t:theme.noto} ili {t:theme.plex}, ili zasebno {t:styles.headingsFont} i {t:styles.textFont}, pa tema postaje {t:styles.ownTheme}.
3. Označite {t:styles.numberHeadings} za brojeve ispred svih naslova.
4. Lijevo odaberite stil, a desno mu promijenite {t:styles.font}, {t:styles.size}, podebljanje, kurziv, {t:command.color}, {t:editor.align}, {t:styles.before}, {t:styles.after} i {t:styles.line}. {t:styles.preview} odmah pokazuje izgled.
5. Pritisnite {t:styles.apply}.

### Vlastiti stil

1. U dijalogu pritisnite {t:styles.new}.
2. Upišite {t:styles.name} i odaberite {t:styles.kind} na kojoj se stil temelji.
3. Stil koji više ne trebate uklonite pomoću {t:styles.delete}.

### Stilovi iz drugog dokumenta

1. U dijalogu pritisnite {t:styles.from}
2. Upišite naziv dokumenta i odaberite ga u popisu.
3. Iznad stilova piše {t:styles.taken} s nazivom dokumenta. Pritisnite {t:styles.apply}.

## Kako radi

Font stila može biti font naslova ili font teksta iz teme, pa se mijenja s temom, ili jedan određeni font. Pod {t:command.color} {t:styles.automatic} znači boju teme. Stil uvezen iz datoteke može zadržati izvornu boju, ponuđenu kao {t:styles.original}.

Pod {t:styles.numbering} stil dobiva brojeve, slova ili rimske brojeve, ili {t:styles.numberingNone}. Uz brojeve se upisuje tekst {t:styles.prefix} i {t:styles.suffix}, a naslovi niže razine mogu nositi i brojeve viših naslova ({t:styles.nested}).

Promjena se primjenjuje na sve odlomke tog stila u cijelom dokumentu, u svim karticama, tek kad pritisnete {t:styles.apply}.

## Ograničenja

- Osnovni stilovi ne mogu se obrisati ni preimenovati, samo vlastiti.
- Svaki vlastiti stil mora imati naziv.
- Stilove mijenja samo onaj tko smije uređivati dokument.

## Povezano

- [Oblikovanje teksta](help:text/formatting)
- [Popisi](help:text/lists)
- [Kartice](help:text/tabs)
