# Razvrstavanje u mape

Claude predlaže mape za stavke zbirke koje još nisu ni u jednoj mapi, a vi prijedlog uredite i primijenite.

## Kako se koristi

1. Otvorite zbirku i u izborniku ostalih radnji odaberite {t:vault.sort}
2. Dijalog {t:vault.sortHeading} prikazuje što se šalje i {t:vault.sortCount}. Pritisnite {t:vault.sortDo}. Dok traje, piše: {t:vault.sorting}
3. U prijedlogu po želji promijenite {t:vault.sortName} svake mape.
4. Pritisnite {t:vault.sortItems} uz mapu da vidite njezine stavke, i premjestite koju u drugu mapu ili u {t:vault.sortNone}.
5. Pritisnite {t:vault.sortApply}.

## Kako radi

Tvrtki Anthropic u SAD-u šalju se samo naziv svake stavke izvan mapa i domena njezine prve adrese te nazivi postojećih mapa na vrhu zbirke. Korisnička imena, lozinke, jednokratni kodovi, bilješke i privitci ne odlaze. Prijedlog se vraća u preglednik, koji tek nakon primjene šifrira nove mape i u njih premješta stavke. Poslužitelj ne čuva prijedlog, nego samo zapis o izvođenju, kao i za ostale radnje umjetne inteligencije.

Mape istog naziva spajaju se, i s postojećom mapom tog naziva. Stavke pod {t:vault.sortNone} ostaju izvan mapa.

Ova radnja u popisu potrošnje umjetne inteligencije stoji kao {t:action.vaultSort}.

## Ograničenja

- Radnja nije dostupna kad umjetna inteligencija nije uključena za instalaciju; tada uz nju piše: {t:ai.off}
- Kad su sve stavke već u mapama, uz nju piše: {t:vault.sortNothing}
- Traži pravo uređivanja u zbirci.
- Kad Claude ne vrati prijedlog, piše: {t:vault.sortNoAnswer}

## Povezano

- [Mape i premještanje](help:vault/folders)
- [Radnje umjetne inteligencije](help:ai/actions)
