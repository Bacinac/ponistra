# Prijedlozi

Tekst koji Claude ili vanjski agent napiše u dokument stoji kao prijedlog dok ga ne prihvatite ili odbijete.

## Kako se koristi

### Jedan prijedlog

1. Stavite kursor u predloženi tekst.
2. Iznad retka pojavljuje se vrsta prijedloga, tko ga je predložio i kada.
3. Pritisnite {t:action.proposalAccept} ili {t:action.proposalReject}.

### Svi prijedlozi u kartici

1. Dok kartica ima prijedloga, na alatnoj traci stoje {t:action.documentAccept} i {t:action.documentReject}.
2. Pritisnite jedno od njih.

## Kako radi

Prijedlog je jedne od vrsta {t:proposal.insertion}, {t:proposal.deletion}, {t:proposal.replacement} ili {t:proposal.formatting}. Prihvaćen prijedlog postaje običan tekst dokumenta, a odbijen nestaje. Prijedlog nosi ime osobe koja je pokrenula radnju; ako ga je napisao vanjski agent, piše agent {t:run.via} osoba.

Prihvaćanje i odbijanje i same su radnje, pa ih vraćate s {t:run.undo}.

## Ograničenja

- Prihvaća i odbija samo onaj tko smije uređivati dokument.
- {t:action.documentAccept} i {t:action.documentReject} odnose se na prijedloge otvorene kartice, ne na ostale kartice dokumenta.

## Povezano

- [Pisanje s Claudeom](help:ai/writing)
- [Radnje i Claude](help:ai/actions)
- [Vanjski agenti](help:agents/connecting)
