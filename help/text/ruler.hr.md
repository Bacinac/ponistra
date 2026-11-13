# Ravnalo i tabulatori

Poravnanje, uvlake i tabulatori odlomka te margine stranice mijenjaju se naredbama ili povlačenjem oznaka na ravnalu u prikazu stranica.

## Kako se koristi

### Poravnanje i uvlaka

1. Stanite u odlomak ili odaberite više njih.
2. U izborniku {t:editor.align} odaberite {t:command.alignLeft} ({k:Shift-Mod-l}), {t:command.alignCenter} ({k:Shift-Mod-e}), {t:command.alignRight} ({k:Shift-Mod-r}) ili {t:command.alignJustify} ({k:Shift-Mod-j}).
3. {t:command.indentMore} ({k:Mod-m}) i {t:command.indentLess} ({k:Shift-Mod-m}) pomiču odlomak udesno ili ulijevo.

### Ravnalo

1. Prijeđite u prikaz {t:view.pages}. Vodoravno ravnalo stoji iznad stranice, okomito uz nju.
2. Na vodoravnom ravnalu povucite {t:ruler.left} ili {t:ruler.right}, {t:ruler.indent}, {t:ruler.hanging}, {t:ruler.first} ili {t:ruler.indentRight}.
3. Na okomitom ravnalu povucite {t:ruler.top}, {t:ruler.bottom}, {t:ruler.header} ili {t:ruler.footer}.

### Tabulatori na ravnalu

1. Gumbom uz vodoravno ravnalo odaberite {t:ruler.tabKind}: {t:ruler.tab.left}, {t:ruler.tab.center}, {t:ruler.tab.right} ili {t:ruler.tab.decimal}.
2. Pritisnite ravnalo na mjestu gdje želite tabulator.
3. Povucite tabulator na novo mjesto. Desnom tipkom miša na njemu mijenjate vrstu, {t:ruler.leader} ({t:ruler.leader.none}, {t:ruler.leader.dot}, {t:ruler.leader.hyphen} ili {t:ruler.leader.underscore}) ili ga uklanjate pomoću {t:ruler.tab.remove}.

### Dijalog tabulatora

1. U izborniku desne tipke miša u tekstu ili u izborniku tabulatora na ravnalu odaberite {t:command.tabStops} Otvara se dijalog {t:tabStops.title}.
2. Upišite {t:tabStops.position}, odaberite vrstu i vodilicu pa pritisnite {t:tabStops.set}.
3. Pod {t:tabStops.list} tabulator uklanjate pomoću {t:tabStops.clear}, a sve odjednom pomoću {t:tabStops.clearAll}.
4. Pritisnite {t:styles.apply}.

## Kako radi

Uvlake i tabulatori vrijede za odabrane odlomke. Margine, zaglavlje i podnožje vrijede za cijeli odjeljak, kao i u [postavkama stranice](help:text/page). Tipka {k:Tab} u tekstu umeće {t:command.tab} do sljedećeg tabulatora, a vodilica popunjava razmak do njega točkicama, crticama ili podvlakom.

Položaj tabulatora mjeri se od lijeve margine, u centimetrima, i ne može biti izvan širine teksta.

## Ograničenja

- Ravnalo postoji samo u prikazu stranica.
- Uz pravo čitanja oznake na ravnalu ne mogu se pomicati.

## Povezano

- [Postavke stranice](help:text/page)
- [Popisi](help:text/lists)
- [Uređivač dokumenta](help:text/overview)
