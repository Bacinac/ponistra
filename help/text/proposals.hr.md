# Prijedlozi izmjena

Prijedlog je izmjena koja još nije prihvaćena: vidi se u tekstu kao umetnuto, izbrisano ili promijenjeno, dok je netko ne prihvati ili odbije.

## Kako se koristi

### Predlaganje umjesto izmjene

1. Na traci alata uključite {t:command.suggest}.
2. Pišite, brišite i oblikujte kao inače. Svaka izmjena postaje prijedlog.
3. Ponovnim pritiskom na {t:command.suggest} vraćate se izravnim izmjenama.

### Prihvaćanje i odbijanje

1. Stanite u prijedlog. Iznad retka pojavljuje se okvir {t:commandGroup.review} s vrstom izmjene, autorom i datumom.
2. Pritisnite kvačicu ({t:action.proposalAccept}) ili križić ({t:action.proposalReject}).
3. Za sve prijedloge odjednom na traci alata odaberite {t:action.documentAccept} ili {t:action.documentReject}.

## Kako radi

Vrsta izmjene piše se kao {t:proposal.insertion}, {t:proposal.deletion}, {t:proposal.replacement} ili {t:proposal.formatting}. Prijedloge stvaraju i Claudeove radnje nad dokumentom, na primjer usporedba s verzijom, te vanjski agenti kojima ste dali pristup: ono što oni napišu u dokument stiže kao prijedlog i ne mijenja tekst dok ga ne prihvatite. Prijedloge stvara i [usporedba s datotekom](help:text/compare), pod nazivom datoteke kao autorom.

Prihvaćeni prijedlog postaje običan tekst, a odbijeni nestaje bez traga u tekstu. Desnom tipkom miša na prijedlogu izbornik nudi i prihvaćanje ili odbijanje svih prijedloga.

## Ograničenja

- Predlagati, prihvaćati i odbijati mogu samo oni koji smiju uređivati dokument. Uz pravo čitanja okvir prijedloga prikazuje samo vrstu, autora i datum.
- Gumbi za sve prijedloge nalaze se na traci samo dok dokument ima prijedloga.

## Povezano

- [Komentari](help:text/comments)
- [Verzije](help:documents/versions)
- [Uređivač dokumenta](help:text/overview)
