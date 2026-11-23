# Datoteke

Stranica {t:rail.files} u jednom stablu okuplja sve izvore datoteka koje dosežete: Moje dokumente, Tvrtku i Dijeljeno u Ponistri, lokacije na mreži i, vlasniku, projekte radnog prostora, u jednom ili dva panela i u karticama.

## Kako se koristi

### Otvaranje izvora

1. Na traci modula pritisnite {t:rail.files}.
2. Bez otvorene mape stranica pokazuje sve izvore po skupinama: {t:files.bookmarks}, {t:rail.documents} ({t:tree.root}, {t:tree.company}, {t:tree.shared}), {t:locations.title} i {t:files.workspace}. Pritisnite izvor.
3. U lijevom stupcu strelica ({t:frame.expand}) uz izvor otvara njegove mape, uz mapu njezine podmape, a ponovni pritisak ({t:frame.collapse}) ih skriva. Pritisak na naziv otvara mapu u panelu; redak otvorene mape je označen.
4. Na mobitelu stablo otvara gumb {t:frame.folders}.

Dok nema nijedne mrežne lokacije, pod {t:locations.title} piše {t:locations.none} uz poveznicu {t:locations.settings}.

### Adresna traka

1. Iznad popisa stoji put od vrha izvora do otvorene mape; svaki dio vraća u svoju mapu.
2. Na mrežnoj lokaciji i u radnom prostoru pritisak na prazan dio trake, ili {t:files.typePath} s tipkovnice, pretvara put u polje {t:files.address}. Upišite put od vrha izvora i pritisnite {k:Enter}; {k:Escape} odustaje.
3. {t:files.refresh} ponovno čita mapu.

### Popis i rešetka

1. {t:files.grid} na vrhu stranice prikazuje stavke kao pločice sa sličicama slika i PDF-ova; {t:files.list} vraća popis sa stupcima.
2. U popisu naslov stupca razvrstava po njemu, ponovni pritisak obrće red.
3. {t:files.hidden} pokazuje ili skriva stavke čiji naziv počinje točkom i one koje mapa na mreži označava skrivenima ili sistemskima.
4. Uz uključen {t:preview.title} na širokom zaslonu, i uvijek u rešetki, prvi pritisak pokazuje stavku, a otvara je dvostruki pritisak.

### Dva panela i kartice

1. {t:files.twin} na vrhu stranice dijeli prostor na dva panela; drugi počinje u istoj mapi. Ponovni pritisak ostavlja samo panel u kojem radite.
2. Panel u kojem radite je uokviren; adresa stranice i stablo prate njega. Pritisak u drugi panel prebacuje rad u njega.
3. {t:files.newTab} otvara novu karticu s mapom koja je otvorena. Pritisak na karticu vraća njezine panele, a {t:files.closeTab} je zatvara.

### Traženje po imenu

1. U polje {t:files.search} uz adresnu traku upišite dio naziva.
2. Ispod se pojavljuje {t:files.found} s brojem i stavkama ispod otvorene mape, svaka sa svojom mapom. Pritisak na stavku otvara je, a na mapu ulazi u nju.
3. Kad je traženje stalo prije kraja, uz broj piše {t:files.partial}.

Polje stoji samo uz izvore koji traže po imenu.

### Kopiranje, izrezivanje i lijepljenje

1. Odaberite stavke: pritisak uz Ctrl, dugi pritisak ili prvi pritisak uz uključen pregled.
2. {k:Mod-c} ili {t:files.copy} u izborniku stavke pamti ih za kopiranje; {k:Mod-x} ili {t:files.cut} za premještanje. Izrezane stavke ostaju blijede dok ih ne zalijepite.
3. Otvorite odredišnu mapu, u istom izvoru ili bilo kojem drugom, u istom ili drugom panelu.
4. {k:Mod-v}, ili {t:files.paste} u izborniku praznog dijela popisa, lijepi u otvorenu mapu. {t:files.pasteInto} u izborniku mape lijepi u nju.

Povlačenje radi isto: stavke odvučene na prazan dio popisa ili na mapu u njemu idu u tu mapu. Unutar istog izvora povlačenje premješta, a uz Ctrl ili Alt kopira; između izvora uvijek kopira.

Ako odredište već ima stavke istog imena, Ponistra pita jednom, {t:files.conflict}, i pokazuje ih. {t:files.conflict.skip} ih ne dira, {t:files.conflict.replace} ih zamjenjuje, a {t:files.conflict.keep} kopiji dodaje broj u naziv (plan (2).docx). Izbor vrijedi za sve što se prenosi, i u podmapama.

Između izvora prenosi poslužitelj, ne preglednik, pa prijenos teče i kad zatvorite stranicu. Ispod panela, pod {t:transfers.title}, svaki prijenos pokazuje {t:transfers.copy} ili {t:transfers.move}, broj stavki, izvor i odredište, traku napretka, koliko je datoteka preneseno od koliko i prenesenu veličinu, a kad je izbor bio preskočiti, i koliko je preskočeno. {t:tree.cancel} prekida prijenos: {t:transfers.cancelled} Završen prijenos ostaje na popisu dok ga {t:transfers.dismiss} ne ukloni.

### Svojstva

1. U izborniku stavke pritisnite {t:files.properties}.
2. Prozor pokazuje {t:files.where}, za simboličku vezu {t:files.link} i kamo vodi, veličinu, datum izmjene, {t:files.owner}, {t:files.mode} i, na dijeljenoj mapi, {t:files.attributes}.
3. Za mapu {t:files.folderSize} zbraja sve u njoj; dok traje, piše {t:files.counting} a zatim veličina i broj datoteka i mapa.
4. Za datoteku {t:files.checksum} računa njezin SHA-256 kao posao u pozadini, {t:job.checksum}; dok traje, piše {t:files.summing}
5. Gdje izvor dopušta, kvačice za {t:files.mode.owner}, {t:files.mode.group} i {t:files.mode.others} uz {t:files.mode.read}, {t:files.mode.write} i {t:files.mode.run} mijenjaju prava; {t:tree.save} ih zapisuje. UID i GID uz {t:files.changeOwner} mijenjaju vlasnika i grupu.

### Oznake

1. U izborniku mape, ili praznog dijela popisa za otvorenu mapu, pritisnite {t:files.bookmark}.
2. Oznaka se pojavljuje pod {t:files.bookmarks} u stablu i na početku stranice, i vodi ravno u tu mapu.
3. Desni ili dugi pritisak na oznaku u stablu nudi {t:files.unbookmark}

### Ostale radnje

Mapa se izrađuje, datoteke učitavaju, otvaraju, uređuju, preimenuju, premještaju, brišu i preuzimaju kao [datoteke na mreži](help:files/network). U Mojim dokumentima, Tvrtki i Dijeljenom dokument se otvara u svom uređivaču, a datoteka na svojoj stranici, kao u [Dokumentima](help:documents/overview).

## Kako radi

Svaki izvor ostaje gdje jest: stranica čita mapu izvora kad je otvorite, a Moji dokumenti, Tvrtka i Dijeljeno su isti dokumenti i mape kao u Dokumentima, pa se promjena na jednom mjestu odmah vidi na drugom. Projekti radnog prostora vidljivi su samo njegovu vlasniku.

Premještanje unutar istog izvora je preimenovanje na samom izvoru. Premještanje između Mojih dokumenata, Tvrtke i Dijeljenog pomiče sam dokument ili mapu, kao u Dokumentima: zadržava dijeljenja i povijest. Kopiranje, i svako premještanje između dvaju izvora, radi poslužitelj Ponistre kao posao: čita iz jednog izvora i piše u drugi, nikad kroz preglednik, pa se ne prekida kad zatvorite stranicu. Red prijenosa ispod panela pokazuje napredak.

- Kopija unutar Ponistre svaku stavku izrađuje iznova: dokument s karticama i verzijama, datoteku s istim sadržajem, poveznicu s adresom. Vlasnik kopije ste vi.
- Iz Ponistre na mrežu ili u radni prostor dokument se zapisuje u svom Office obliku (DOCX, XLSX, PPTX, s makroima ako ih je imao), PDF s bilješkama, a poveznica kao datoteka .url. Premještanjem izvorna stavka ide u {t:trash.title}.
- U Ponistru datoteka ulazi kao pri učitavanju: postaje dokument ako Ponistra tu vrstu uvozi, s datumom izmjene s poslužitelja. Istim imenom smatra se isti naslov bez ekstenzije, bez obzira na velika i mala slova.
- {t:files.conflict.replace} mape na mapu istog imena spaja ih: sadržaj ide u postojeću mapu.

Oznake pripadaju računu i vide se na svakom uređaju na koji se prijavite. Kartice, paneli, prikaz kao popis ili rešetka i skrivene datoteke pamte se samo u ovom pregledniku.

## Ograničenja

- Gdje izvor nešto ne podržava, ta stavka se ne nudi: traženje, veličina mape, kontrolni zbroj, prava i vlasnik postoje samo na izvorima koji ih znaju. Dijeljena mapa (SMB) nema Unix prava ni vlasnika, nego atribute.
- Prava i vlasnika mijenja samo račun koji na poslužitelju to smije; inače piše greška poslužitelja.
- U korijen Tvrtke i Dijeljenog ne može se lijepiti, kao ni u izvor koji samo čitate.
- Stavka se ne može kopirati ni premjestiti u samu sebe ili u svoju podmapu.
- Mapa do koje vodi simbolička veza ne prenosi se, nego se broji kao preskočena; posebne datoteke (uređaji, cijevi) ne prenose se.
- Iz mape bez preuzimanja ništa ne ide na mrežu ni u radni prostor, nego piše {t:error.confined} Kopija unutar Ponistre može, ondje gdje ta mapa i dalje vrijedi.
- Dva panela postoje samo na širokom zaslonu.
- Poruka {t:error.not_found} u panelu znači da izvor više ne postoji ili vam više nije dostupan.

## Povezano

- [Datoteke na mreži](help:files/network)
- [Mrežne lokacije](help:documents/locations)
- [Dokumenti](help:documents/overview)
- [Projekti](help:agents/projects)
