# Pisanje s Claudeom

Claude sažima, prepisuje, prevodi i uspoređuje tekst dokumenta, a tekst koji napiše dolazi kao prijedlog.

## Kako se koristi

### Sažetak, prepisivanje i tablica

1. Označite tekst ili, za cijelu karticu, ne označite ništa.
2. Desnim klikom otvorite izbornik.
3. Odaberite {t:action.textSummarise} ili {t:action.textExtract}.
4. Za {t:action.textRewrite} odaberite način: {t:action.textRewrite.formal}, {t:action.textRewrite.simple}, {t:action.textRewrite.short} ili {t:action.textRewrite.correct}.

### Prijevod i usporedba

1. Za {t:action.documentTranslate} odaberite jezik u podizborniku.
2. Za usporedbu odaberite {t:action.documentCompare.ask}
3. Odaberite {t:compare.version} i pritisnite {t:compare.run}.

## Kako radi

Radnja se odnosi na odlomke do kojih seže oznaka, a bez oznake na cijelu karticu. Sažetak i tablica podataka upisuju se iza označenog teksta, a za cijelu karticu na njezin početak, iza naslova. Prepisani tekst stoji na mjestu izvornoga, svaki odlomak u svojem.

Prijevod kopira karticu u novu karticu pokraj nje, nazvanu po izvornoj na odabranom jeziku, i prevodi tekst, tekst u ćelijama, naslove grafikona i opise slika. Usporedba opisuje što se u kartici promijenilo od odabrane verzije, na početku kartice iza naslova.

## Ograničenja

- Sažetak, prepisani tekst, tablica podataka, i usporedba dolaze kao prijedlozi koje prihvaćate ili odbijate.
- Prijevod se upisuje odmah, u novu karticu, a ne kao prijedlog.
- Dok dokument nema nijednu verziju, usporedba se ne može pokrenuti.

## Povezano

- [Radnje i Claude](help:ai/actions)
- [Agent uz dokument](help:ai/agent)
- [Prijedlozi](help:ai/proposals)
- [Verzije](help:documents/versions)
- [Usporedba s datotekom](help:text/compare)
