# Pregled pošte

Pošta skuplja poruke svih vaših računa na jedno mjesto, u zajedničke mape i u mape svakog računa.

## Kako se koristi

![Popis poruka uz stablo mapa](shot:mail-list)

### Kretanje po mapama

1. Otvorite modul {t:rail.mail} na traci modula ili upišite njegov naziv u kutiju za pretragu.
2. U lijevom stupcu odaberite zajedničku mapu: {t:mail.role.inbox}, {t:mail.role.sent}, {t:mail.role.drafts}, {t:mail.role.archive}, {t:mail.role.junk} ili {t:mail.role.trash}.
3. Označene poruke nalaze se pod {t:favourites.title}, odmah ispod pristigle pošte, a ispod njih, dok neka poruka čeka, [{t:mail.laterTitle}](help:mail/later). Poruke koje ste [odgodili](help:mail/snoozing) čekaju u mapi {t:mail.role.snoozed}.
4. Mape pojedinog računa nalaze se ispod naziva tog računa.
5. Odaberite poruku u popisu. Dok nijedna nije otvorena, na mjestu poruke piše: {t:mail.choose}
6. Na dnu popisa pritisnite {t:mail.more} za starije poruke.

### Pošta jednog računa

1. Pritisnite naziv računa u lijevom stupcu. Zajednička mapa tada prikazuje samo njegove poruke.
2. Za povratak pritisnite {t:mail.allAccounts} ili ponovno naziv računa.

### Poredak popisa

1. Otvorite izbornik {t:mail.sort} iznad popisa.
2. Odaberite {t:mail.sortDate}, {t:mail.sortSender} (u poslanoj pošti i skicama {t:mail.sortRecipient}) ili {t:mail.sortPriority}.
3. Odaberite smjer: {t:mail.newestFirst} ili {t:mail.oldestFirst}, {t:mail.aToZ} ili {t:mail.zToA}, {t:mail.highFirst} ili {t:mail.lowFirst}.

### Označavanje cijele mape kao pročitane

1. Dugo pritisnite mapu ili je pritisnite desnom tipkom miša.
2. Odaberite {t:mail.allSeen}.

## Kako radi

Ponistra preuzima poštu od pružatelja u jednom smjeru i čuva je kod sebe. Svaka se poruka čuva jednom, pa se ona koja je stigla na dva računa prikazuje jednom, uz boje obaju računa. Označavanje, premještanje i brisanje vrijede u Ponistri i ne mijenjaju ono što je kod pružatelja. Pružatelju se šalje samo poruka koju vi pošaljete, uz kopiju u njegovoj mapi poslane pošte.

Prvo preuzimanje uzima najprije novu poštu pa stariju, od novije prema starijoj, pa je popis upotrebljiv prije nego što sve stigne. Dok traje, ispod računa piše: {t:mail.syncing} Dok još nema nijedne mape, na stranici piše: {t:mail.firstSync} Ako račun nije povezan, na stranici piše: {t:mail.none} Ispod toga je gumb za povezivanje.

Nepročitana poruka ima istaknut pošiljatelja i predmet. Spajalica označava {t:mail.attachments}, a zvjezdica da je poruka među omiljenima. Kad je računa više, traka uz poruku ima boju računa na koji je stigla. Poruka bez predmeta prikazuje se kao {t:mail.noSubject}. Prioritet se prikazuje oznakom {t:mail.highPriority} ili {t:mail.lowPriority}, a čita se iz same poruke. Prazna mapa prikazuje: {t:mail.empty} U praznom Omiljenom piše: {t:favourites.noMail}

Odabrani poredak pamti se u tom pregledniku. Na drugom uređaju popis je poredan po svojem pregledniku.

## Ograničenja

- Ono što učinite u Ponistri ne vidi se u pružateljevoj aplikaciji ni na njegovim web-stranicama, i obrnuto: poruka koju premjestite kod pružatelja u Ponistri ostaje gdje jest.
- {t:mail.allSeen} vrijedi samo u Ponistri.
- Zajedničke mape ne prikazuju poruke računa kojem je isključeno {t:mail.together}; te su poruke u mapama tog računa.
- Na uređaju označenom za rad bez mreže prva stranica svake mape čita se i bez mreže ([Rad bez mreže](help:account/offline)).

## Povezano

- [Čitanje poruke](help:mail/reading)
- [Rad s više poruka](help:mail/selecting)
- [Računi e-pošte](help:mail/accounts)
- [Rad bez mreže](help:account/offline)
