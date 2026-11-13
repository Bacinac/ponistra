# Uređivač dokumenta

Dokument pišete i oblikujete u jednom prozoru: kartice su lijevo, traka alata na vrhu, a izmjene se spremaju same i odmah ih vide svi koji dokument imaju otvoren.

## Kako se koristi

![Otvoreni dokument s trakom alata](shot:text-editor)

### Pisanje

1. Otvorite dokument iz popisa i pišite izravno u njega. Prazan dokument podsjeća da „/” otvara umetanje.
2. Na traci alata nalaze se {t:command.undo} ({k:Mod-z}) i {t:command.redo} ({k:Mod-y}), stil odlomka, oblikovanje, boje, popisi, poravnanje, {t:editor.insert} i komentari. Što ne stane u traku, nalazi se pod {t:editor.more}.
3. Desnom tipkom miša u tekstu otvarate izbornik s naredbama za mjesto na kojem ste.
4. Upišite „/” na početku retka ili nakon razmaka za popis onoga što nudi {t:editor.insert}. Daljnja slova sužavaju popis, a {k:Enter} umeće odabrano.
5. {k:Mod-f} otvara [traženje i zamjenu](help:text/find) u kartici.

### Prikaz

1. Desno na traci alata odaberite {t:view.label}: {t:view.text}, {t:view.pages} ili {t:view.slides}.
2. U prikazu stranica i slajdova pod {t:zoom.label} birate {t:zoom.page} ili {t:zoom.width}.

### Zaglavlje dokumenta

1. Pritisnite naslov dokumenta u putanji za izbornik dokumenta: kopija, preimenovanje, premještanje, uvoz, spremanje u drugi oblik, ispis, postavke stranice, stilovi i jezik.
2. Gumbi desno otvaraju {t:agent.title}, {t:comment.list}, {t:access.share} i {t:version.list} u bočnom panelu.

## Kako radi

Svaka izmjena odmah se šalje poslužitelju, pa gumba za spremanje nema. Desno na traci piše stanje veze: {t:collab.connected}, zatim {t:collab.connecting} dok se veza uspostavlja ili {t:collab.disconnected} kad se prekine, a Ponistra se tada sama ponovno povezuje.

Kad dokument uređuje još netko, vidite njegov kursor u boji s imenom. Vaš kursor s drugog uređaja ili iz drugog prozora označen je s {t:presence.you}. {t:command.undo} poništava samo vaše izmjene, ne i tuđe.

{t:view.text} prikazuje tekst u jednom stupcu, {t:view.pages} onako kako će biti ispisan, s ravnalima uz stranicu, a {t:view.slides} slajd po slajd. Odabrani prikaz pamti se za svaki dokument u tom pregledniku. Dokument uvezen iz Worda prvi se put otvara u prikazu stranica, a iz PowerPointa u prikazu slajdova. Povećanje vrijedi za sve dokumente.

## Ograničenja

- Uz pravo čitanja traka alata se ne prikazuje: dokument možete čitati i komentirati.
- {t:zoom.label} postoji samo u prikazu stranica i slajdova.
- Kad se naredba ne može izvršiti, javlja se {t:command.failed}.
- Bez mreže dokument se otvara samo na uređaju označenom za [rad bez mreže](help:account/offline).

## Povezano

- [Kartice](help:text/tabs)
- [Agent uz dokument](help:ai/agent)
- [Oblikovanje teksta](help:text/formatting)
- [Prečaci tipkovnice](help:text/shortcuts)
- [Traženje i zamjena](help:text/find)
- [Verzije](help:documents/versions)
