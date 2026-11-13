# Oblik broja i ispuna

Oblik broja određuje kako ćelija prikazuje svoju vrijednost, a ispuna joj daje boju pozadine.

## Kako se koristi

### Oblik broja

1. Odaberite ćelije.
2. Desnom tipkom miša ili u izborniku {t:commandGroup.table} na traci alata otvorite {t:command.cellFormat}.
3. Odaberite {t:cellFormat.general}, {t:cellFormat.number}, {t:cellFormat.integer}, {t:cellFormat.currency}, {t:cellFormat.percent}, {t:cellFormat.scientific}, {t:cellFormat.date}, {t:cellFormat.time} ili {t:cellFormat.dateTime}.

### Vlastiti oblik

1. U istom izborniku odaberite {t:cellFormat.custom} Otvara se dijalog {t:cellFormat.title}.
2. U polje {t:cellFormat.code} upišite kod oblika, kakav zapisuje Excel. Ispod polja, uz {t:cellFormat.examples} nalaze se primjeri kodova.
3. Pritisnite {t:tree.save}. Prazan kod vraća {t:cellFormat.general}.

### Ispuna ćelija

1. Odaberite ćelije i otvorite {t:command.fill}.
2. Odaberite boju ili {t:color.none}.

## Kako radi

Oblik mijenja samo prikaz: vrijednost ćelije i formule koje je čitaju ostaju iste. {t:cellFormat.general} prikazuje vrijednost onakvu kakva jest.

{t:cellFormat.number} ima dvije decimale i razdjelnik tisućica, a {t:cellFormat.integer} nema decimala. {t:cellFormat.currency} piše euro za hrvatski, njemački, francuski, talijanski i španjolski, dolar za engleski i funtu za britanski engleski. Znakovi za tisućice i decimale te zapis datuma slijede jezik dokumenta, i u kodu vlastitog oblika.

Ispuna nudi iste boje kao isticanje teksta.

## Ograničenja

- Kod vlastitog oblika ima najviše 255 znakova.

## Povezano

- [Tablice](help:tables/overview)
- [Izgled tablice](help:tables/design)
- [Jezik dokumenta](help:text/language)
