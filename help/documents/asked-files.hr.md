# Zatražene datoteke

Vlasnik mape izrađuje poveznicu kojom mu osobe bez računa u instalaciji šalju datoteke u tu mapu, a da u njoj ništa ne vide.

## Kako se koristi

### Izrada poveznice

1. U izborniku mape ili u zaglavlju otvorene mape pritisnite {t:access.share}.
2. U odjeljku {t:outside.title} pritisnite {t:outside.make}.
3. Pod {t:outside.kind} odaberite {t:outside.kind.upload}.
4. Po želji odaberite datum pod {t:outside.until}.
5. Pritisnite {t:outside.make} ili {t:tree.cancel}.
6. Uz poveznicu pritisnite {t:outside.copy} i pošaljite je onima od kojih tražite datoteke.

{t:outside.end} uz poveznicu odmah prekida primanje.

### Slanje datoteka

1. Osoba otvara poveznicu u pregledniku, bez prijave. Na vrhu stoji naziv mape.
2. Upisuje {t:outside.sender}.
3. Pod {t:outside.files} odabire jednu ili više datoteka.
4. Pritišće {t:outside.send}. Dok traje slanje, piše koliko je datoteka poslano od ukupnog broja.
5. Pod {t:outside.delivered} pojavljuju se nazivi poslanih datoteka. Osoba može odmah poslati nove.

## Kako radi

Svaka datoteka stiže u mapu kao vaša, s izvornim nazivom i datumom zadnje izmjene, i čita se i pretražuje kao svaka druga.

U [dnevniku pristupa](help:documents/sharing) datoteke piše {t:log.kind.uploaded} s imenom koje je pošiljatelj upisao, a u dnevniku mape izrada poveznice kao {t:log.uploadLinkMade}. Ime nitko ne provjerava; to je ono što je pošiljatelj napisao. Tko je izradio poveznicu, dobiva [obavijest](help:account/notifications) o svakoj pristigloj datoteci, koja otvara samu datoteku.

Pošiljatelj ne dobiva nikakav pristup: ne vidi mapu, ni ono što je već u njoj, ni datoteke koje je sam poslao.

## Ograničenja

- Poveznica za slanje datoteka postoji samo za mapu, nema lozinku ni izbor preuzimanja.
- Izrađuje je samo vlasnik mape, ako mu to dopušta politika instalacije. Inače piše {t:error.links_not_allowed}
- Datoteka veća od dopuštene se ne šalje: {t:error.too_large} Kad na poslužitelju ponestane mjesta: {t:error.no_room}
- Datoteka koja se izgubila između slanja i spremanja javlja {t:error.unknown_file} Odaberite je ponovno.
- Poveznica koja više ne vrijedi javlja {t:error.no_link} Vrijedi do kraja odabranog dana, dok je vlasnik ne ukine, dok je mapa izvan smeća i dok administrator ne zabrani dijeljenje izvan instalacije.

## Povezano

- [Poveznica izvan instalacije](help:documents/outside)
- [Dijeljenje](help:documents/sharing)
- [Obavijesti](help:account/notifications)
- [Učitavanje datoteka](help:documents/upload)
