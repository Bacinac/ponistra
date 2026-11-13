# Mapa na poslužitelju

Mapu tvrtke možete spojiti s mapom na poslužitelju datoteka vaše mreže, kao kopiju dok je ne preselite ili kao ulaznu mapu.

## Kako se koristi

### Spajanje

1. Na stranici {t:users.title}, u izborniku retka mape tvrtke, odaberite {t:fileServer.connect}
2. U dijalogu {t:fileServer.connectTitle} upišite {t:fileServer.address}, {t:fileServer.username} i {t:fileServer.password}.
3. Odaberite {t:fileServer.mode.copy} ili {t:fileServer.mode.inbox} i pritisnite {t:fileServer.connectAction}.

### Kopija

1. Nakon spajanja Ponistra čita popis, a uz mapu piše {t:fileServer.reading} pa {t:fileServer.read}.
2. Odaberite {t:fileServer.inventory} i u dijalogu {t:fileServer.inventoryTitle} provjerite {t:fileServer.files}, {t:fileServer.folders}, {t:fileServer.size} i {t:fileServer.free}.
3. Pritisnite {t:fileServer.copy}. Dok traje, piše {t:fileServer.copying} i koliko je datoteka kopirano.
4. Kad želite raditi samo u Ponistri, odaberite {t:fileServer.move} i potvrdite s {t:fileServer.moveAction} u dijalogu {t:fileServer.moveTitle} Dok traje, uz mapu piše {t:fileServer.moving}

### Održavanje

1. {t:fileServer.refresh} odmah čita promjene s poslužitelja.
2. {t:fileServer.signIn} otvara {t:fileServer.signInTitle} za novo korisničko ime i lozinku.
3. {t:fileServer.disconnect} odspaja mapu, gumbom {t:fileServer.disconnectAction} u dijalogu {t:fileServer.disconnectTitle}

## Kako radi

U načinu {t:fileServer.mode.copy} mapa na poslužitelju ostaje izvornik, a kopija se u Ponistri samo čita. Ponistra je čita ponovno svakih pet minuta, a uz mapu piše {t:fileServer.ready} s vremenom zadnjeg čitanja. Preseljenje preuzima posljednje promjene, a nakon toga se mapa uređuje samo u Ponistri i poslužitelj se više ne prati.

U načinu {t:fileServer.mode.inbox} Ponistra svakih tridesetak sekundi premješta pristigle datoteke u mapu tvrtke i briše ih s poslužitelja. Uz mapu piše {t:fileServer.taken} i broj preuzetih datoteka.

Popis s poslužitelja pod {t:fileServer.left} navodi što se neće kopirati: {t:fileServer.why.link}, {t:fileServer.why.narrower}, {t:fileServer.why.too_large}, {t:fileServer.why.too_long} ili {t:fileServer.why.unreadable}. Pod {t:fileServer.kept} su datoteke koje se ne mogu uvesti kao dokument, a uz svaku piše razlog: {t:fileServer.kept.too_large}, {t:fileServer.kept.too_many_cells}, {t:fileServer.kept.too_many_formulas}, {t:fileServer.kept.unreadable} ili {t:fileServer.kept.newer_file}.

Odspajanje kopije prazni mapu tvrtke i briše kopiju iz Ponistre, a mapa na poslužitelju ostaje kakva jest. Odspojena ulazna mapa više ne preuzima datoteke, a već preuzete ostaju.

## Ograničenja

- Spojiti se mogu samo mape tvrtke, ne zbirke sefa.
- Kopiranje počinje samo ako na disku instalacije uz kopiju ostaje još barem 1 GB slobodno.
- Preseliti se može tek kopija koja se kopira ili je kopirana.
- Ulazna mapa nema popis ni preseljenje.
- Što drži pravilo zadržavanja ili zakonsko čuvanje ostaje u kopiji i kad nestane s poslužitelja, a takva se kopija ne može odspojiti.

## Povezano

- [Mape i zbirke tvrtke](help:admin/company)
- [Čuvanje podataka](help:admin/retention)
