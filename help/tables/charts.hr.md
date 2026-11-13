# Grafikoni

Grafikon prikazuje ćelije tablice iz iste kartice i mijenja se zajedno s njima.

## Kako se koristi

### Novi grafikon

1. U izborniku {t:editor.insert} odaberite {t:command.chart} Otvara se dijalog {t:chart.insert}.
2. Odaberite vrstu: {t:chart.column}, {t:chart.bar}, {t:chart.line}, {t:chart.area}, {t:chart.pie}, {t:chart.doughnut} ili {t:chart.scatter}.
3. Provjerite {t:chart.table} i {t:chart.range}, na primjer `A1:C5`.
4. Pod {t:chart.seriesIn} odaberite {t:chart.byColumns} ili {t:chart.byRows}.
5. Pod {t:chart.names} i {t:chart.labels} odaberite {t:chart.automatic}, {t:chart.firstRow} ili {t:chart.firstColumn} ili {t:chart.none}. Raspršeni grafikon umjesto kategorija ima {t:chart.xValues}.
6. Po želji upišite {t:chart.title}, uključite {t:chart.stacked} i {t:chart.legend} pa pritisnite {t:chart.insertButton}.

### Uređivanje

1. Dvaput pritisnite grafikon ili ga odaberite i u izborniku {t:commandGroup.chart} na traci alata odaberite {t:command.editChart} Otvara se dijalog {t:chart.edit}.
2. {t:command.deleteChart} uklanja grafikon.

## Kako radi

Grafikon umetnut iz odabranih ćelija ili iz tablice u kojoj je kursor dolazi iza tablice. Kad je kursor izvan tablice, grafikon prikazuje najbližu tablicu iznad kursora i umeće se na mjesto kursora.

Niz bez naziva u legendi se zove {t:chart.series} s brojem. {t:chart.stacked} postoji za stupčaste, trakaste, linijske i površinske grafikone. Kad tablica ili ćelije grafikona više ne postoje, kad tablicu nije moguće izračunati ili u ćelijama nema brojeva, grafikon umjesto crteža prikazuje objašnjenje.

## Ograničenja

- Grafikon prikazuje samo tablicu iz iste kartice, pa se u kartici bez tablice ne može umetnuti.
- Raspon mora biti unutar tablice.

## Povezano

- [Tablice](help:tables/overview)
- [Umetanje](help:text/insert)
- [Radnje nad tablicom](help:ai/tables)
