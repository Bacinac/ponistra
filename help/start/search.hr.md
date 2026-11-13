# Kutija za pretragu

Kutija u zaglavlju svake stranice traži kroz dokumente, poštu, događaje, zadatke, ljude, sef i pomoć te nudi naredbe i mjesta aplikacije.

## Kako se koristi

![Kutija za pretragu s naredbama i prvim pogocima](shot:start-search)

### Traženje

1. Pritisnite kutiju {t:search.placeholder} u zaglavlju ili pritisnite {k:Alt-/}. Prečac {k:Mod-k} radi ondje gdje ga stranica ne koristi za nešto drugo. Na mobitelu je kutija ikona povećala koja se pritiskom raširi.
2. Upišite barem dva znaka. Ispod kutije pojavljuju se naredbe i prvi pogoci, po skupinama: {t:search.documents}, {t:search.mail}, {t:search.conversations}, {t:search.events}, {t:search.tasks}, {t:search.people}, {t:search.vault}, {t:search.versions} i {t:search.help}.
3. Strelicama {k:ArrowDown} i {k:ArrowUp} odaberite pogodak ili naredbu i pritisnite {k:Enter}, ili ih pritisnite mišem.
4. Za sve pogotke pritisnite {t:search.all}. Isto čini {k:Enter} kad ništa nije odabrano.
5. Kad ste u mapi dokumenata, gumb {t:search.in} s nazivom mape traži samo u njoj.
6. {k:Escape} zatvara popis.

### Naredbe i mjesta

1. Upišite dio naziva onoga što želite: modula, mjesta, postavke, teme ili jezika.
2. Odaberite {t:places.open} s nazivom mjesta, na primjer {t:rail.contacts}, {t:tasks.title} ili {t:settings.title}.
3. Novo stvarate pomoću {t:notes.new}, {t:mail.compose} ili {t:tree.newDocument}.
4. Temu i jezik mijenjate naredbama koje počinju s {t:frame.theme} i {t:frame.language}, a odjavljujete se pomoću {t:auth.signOut}.

## Kako radi

Svaka skupina poredana je po tome koliko pogodak odgovara riječima. Kutija prikazuje najviše 8 pogodaka, podijeljenih među skupinama koliko je moguće jednako, i najviše 5 naredbi. Naredbe stranice na kojoj ste, na primjer naredbe dokumenta s njihovim prečacima, dolaze prije općih. Naslovi se pronalaze i kad je riječ u njima napisana malo drukčije.

Uz pogodak u dokumentu piše gdje je u njemu: {t:search.tab}, {t:search.section}, {t:search.paragraph}, {t:search.table}, {t:search.cell}, {t:search.image}, {t:search.chart}, {t:search.pdf}, {t:search.page}, {t:search.footnote}, {t:search.endnote}, {t:search.comment}, {t:search.data} ili {t:kind.link}. Pogodak u privitku poruke nosi oznaku {t:search.attachment} s nazivom datoteke. Pošta obuhvaća i zajedničke sandučiće koje čitate; poruka iz sandučića nosi njegov naziv ispred pošiljatelja i otvara se u tom sandučiću. Osoba je označena kao {t:search.person.contact}, {t:search.person.colleague} ili {t:search.person.directory}, a zadatak kao {t:tasks.done} ili rokom ({t:tasks.due}).

Sef se pretražuje u vašem pregledniku dok je otključan, pa poslužitelj ne vidi što u njemu tražite. Kad je zaključan, ispod pogodaka piše: {t:search.vaultLocked} Pogoci u sefu nose oznaku {t:vault.mine} ili naziv zbirke, a {t:vault.unlock} otvara sef. Članci pomoći prikazuju se samo dok pretraga nema filtara. Ranije verzije dokumenata traže se samo kad to zatražite filtrom vrste, a pogodak u verziji nosi {t:version.number} s brojem, uz {t:version.automatic} ili {t:version.restoredFrom}.

Na novoj stranici kutija je prazna, osim ako ste u nju pisali dok se stranica učitavala.

## Ograničenja

- S manje od dva znaka piše: {t:search.hint}
- Kad ništa ne odgovara, piše {t:search.none} i ono što ste upisali.
- Pošta iz mapa {t:mail.role.junk} i {t:mail.role.trash} pretražuje se samo kad je zatražite filtrom mape.
- Kutije nema na stranici s rezultatima pretrage, koja ima svoju.
- Bez mreže kutija je onemogućena i u njoj piše {t:offline.needed} ([Rad bez mreže](help:account/offline)).

## Povezano

- [Rezultati pretrage i filtri](help:start/results)
- [Pretraga rečenicom](help:start/sentence)
- [Okvir aplikacije](help:start/overview)
