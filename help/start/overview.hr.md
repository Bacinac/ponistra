# Okvir aplikacije

Svaka stranica Ponistre ima isti okvir: traku modula, zaglavlje s pretragom i izbornikom računa te lijevi stupac uz sadržaj.

## Kako se koristi

![Okvir aplikacije s trakom modula, zaglavljem i stupcem](shot:start-frame)

### Moduli

1. Na traci modula ({t:rail.label}) odaberite {t:rail.today}, {t:rail.calendar}, {t:rail.mail}, {t:rail.chat} ili {t:rail.documents}. Na širokom zaslonu traka je uz lijevi rub, a na mobitelu uz donji.
2. Logo Ponistre na vrhu trake vodi na {t:rail.today}.
3. Stranica koja pripada modulu, kao {t:rail.contacts} u modulu {t:rail.chat}, u zaglavlju ispred naslova ima naziv modula kojim se vraćate u njega.
4. Ako ste vlasnik radnog prostora za kod, na traci je i {t:rail.projects}, [stranica s projektima i razgovorima](help:agents/projects).

### Lijevi stupac

1. U lijevom stupcu je ono što pripada stranici: mape dokumenata, kalendari, popis razgovora ili sadržaj pomoći.
2. Uz dokumente stupac nudi {t:favourites.title}, {t:tree.root}, {t:tree.shared}, {t:notes.title}, {t:links.title}, {t:boards.title}, {t:vault.title} i {t:trash.title}. {t:tree.company} se prikazuje kad tvrtka ima zajedničke mape.
3. Mapu s podmapama otvarate strelicom ispred naziva ({t:frame.expand}), a zatvarate istom strelicom ({t:frame.collapse}).
4. Širinu stupca mijenjate povlačenjem njegova desnog ruba ({t:frame.width}). Dvostruki klik na rub vraća zadanu širinu.
5. Kad je rub odabran tipkom {k:Tab}, širinu mijenjate tipkama {k:ArrowLeft} i {k:ArrowRight}, a {k:Home} i {k:End} daju najmanju i najveću.
6. Na mobitelu, i na stranicama koje u stupcu imaju nešto svoje, mape dokumenata otvara gumb {t:frame.folders} u zaglavlju.

### Izbornik računa

1. Pritisnite krug s vašim inicijalima u desnom kutu zaglavlja ({t:frame.account}).
2. Pod {t:frame.language} i {t:frame.theme} birate jezik i izgled sučelja.
3. {t:settings.title} otvara postavke vašeg računa, a {t:auth.signOut} vas odjavljuje.
4. {t:about.title} otvara podatke o aplikaciji.

### Pomoć

Upitnik u zaglavlju ({t:help.title}), kao i {k:F1}, otvara članak o stranici na kojoj ste.

### Prečaci

- {k:Alt-/} ili {k:Mod-k} stavlja pokazivač u kutiju za pretragu.
- {k:Alt-m} uključuje mikrofon za glasovne naredbe.
- {k:Alt-n} otvara novu bilješku.
- {k:F1} otvara pomoć o stranici na kojoj ste.

## Kako radi

Okvir ostaje na mjestu dok se stranice mijenjaju, pa ono što ste upisali u kutiju za pretragu ostaje i dok se nova stranica učitava. Stranica se osvježava sama čim se njezini podaci promijene, bilo da ste ih promijenili na drugom uređaju ili na mobitelu ili ih je donijela sinkronizacija, pa je ne treba ponovno učitavati.

Broj uz {t:rail.mail} pokazuje nepročitane poruke u pristiglim mapama vaših računa, a broj uz {t:rail.chat} poruke drugih koje u razgovorima još niste pročitali; u kanalima se broje samo spominjanja i odgovori u nitima koje pratite.

Na dnu trake modula prikazuje se sljedeći današnji događaj: {t:today.next}, vrijeme početka i koliko je još do njega, odnosno {t:today.now} kad je već počeo. Pritisak na njega otvara taj dan u kalendaru, a ako događaj ima sastanak na mreži, ispod je gumb {t:meeting.join}.

Na dnu lijevog stupca stoje autor, inačica i godina. Pritisak na ime autora otvara {t:about.title}.

Širina stupca pamti se u pregledniku u kojem ste je namjestili.

## Ograničenja

- Dok se Ponistra nadograđuje ili joj je veza prekinuta, umjesto aplikacije piše {t:status.away} Aplikacija se sama nastavi čim poslužitelj odgovori.
- Ako poslužitelj javi grešku, umjesto aplikacije piše {t:status.down} i razlog.
- Sljedeći događaj na dnu trake ne prikazuje se na mobitelu.
- {t:rail.projects} vidi samo korisnik kojem je dodijeljen radni prostor za kod.

## Povezano

- [Danas](help:start/today)
- [Kutija za pretragu](help:start/search)
- [Tema i jezik](help:start/appearance)
