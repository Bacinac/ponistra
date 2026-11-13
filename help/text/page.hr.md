# Postavke stranice

Veličina papira, položaj, margine, zaglavlje i podnožje te brojevi stranica postavljaju se za cijeli dokument, za pojedinu karticu ili za odjeljak.

## Kako se koristi

### Papir i margine

1. U izborniku dokumenta odaberite {t:page.setup} Otvara se dijalog {t:page.title}.
2. Pod {t:page.paper} odaberite format, ili {t:page.ownSize} pa upišite {t:page.width} i {t:page.height}.
3. Pod {t:page.orientation} odaberite {t:page.portrait} ili {t:page.landscape}.
4. Pod {t:page.margins} odaberite {t:page.margins.normal}, {t:page.margins.narrow}, {t:page.margins.wide} ili {t:page.margins.own} pa upišite {t:page.top}, {t:page.bottom}, {t:page.left} i {t:page.right}.
5. Upišite {t:page.header} i {t:page.footer} pa pritisnite {t:page.apply}.

### Brojevi stranica

1. U istom dijalogu označite {t:page.restart} i upišite {t:page.start}.
2. Broj stranice upisuje se u zaglavlje ili podnožje kao polje.

### Zaglavlje i podnožje

1. U prikazu {t:view.pages} u izborniku {t:editor.insert} odaberite {t:command.header} ili {t:command.footer}, ili dvaput pritisnite gornji ili donji rub stranice.
2. Pišite kao u tekstu. U izborniku {t:editor.insert} nude se polja {t:field.page}, {t:field.pages}, {t:field.date} i {t:field.title}.
3. Na traci alata, pod {t:commandGroup.part}, uključite {t:command.firstApart} za posebno zaglavlje prve stranice (isto čini {t:page.firstPage} u dijalogu {t:page.title}), a u odjeljku {t:command.partLinked} za zaglavlje prethodnog odjeljka.
4. {t:command.closePart} ({k:Escape}) vraća u tekst.

### Prijelomi

1. {t:command.pageBreak} ({k:Mod-Enter}) iz izbornika {t:editor.insert} nastavlja tekst na novoj stranici.
2. {t:command.sectionBreak} započinje novi odjeljak, koji može imati svoje postavke stranice.
3. {t:command.columnBreak} ({k:Shift-Mod-Enter}) nastavlja tekst u sljedećem stupcu.

## Kako radi

Postavke dokumenta vrijede za sve kartice bez vlastitih. Kad dokument ima više kartica, pod {t:page.source} birate {t:page.fromDocument} ili {t:page.own}. Kartica koja vraća postavke dokumenta gubi vlastita zaglavlja i podnožja, na što dijalog upozorava. U odjeljku nakon prijeloma pod {t:page.sectionSource} birate {t:page.fromSection} ili {t:page.own}.

Bez vlastitih postavki stranice kartice nastavljaju brojenje prethodne. Polja u zaglavlju i podnožju pokazuju broj stranice na kojoj stoje, ukupan broj stranica, datum i naslov dokumenta. Uz {t:command.firstApart} prva stranica dobiva {t:part.headerFirst} i {t:part.footerFirst}, odvojeno od {t:part.header} i {t:part.footer} ostalih.

## Ograničenja

- Zaglavlje i podnožje uređuju se samo u prikazu stranica.
- Margine ne smiju ostaviti stranicu bez mjesta za tekst: dijalog tada ne dopušta primjenu.
- Postavke mijenja samo onaj tko smije uređivati dokument.

## Povezano

- [Ravnalo i tabulatori](help:text/ruler)
- [Ispis](help:text/print)
- [Kartice](help:text/tabs)
