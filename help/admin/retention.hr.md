# Čuvanje podataka

Pravila čuvanja određuju koliko se dugo dokumenti, datoteke, pošta i razgovori čuvaju prije nego što ih itko smije trajno izbrisati i kada ih Ponistra briše sama, a zakonsko čuvanje zaustavlja svako brisanje sadržaja osobe ili mape dok predmet traje.

## Kako se koristi

### Pravilo čuvanja

1. U {t:settings.title}, pod {t:settings.installation}, odaberite {t:retention.title}.
2. Pritisnite {t:retention.newRule}.
3. Pod {t:retention.what} odaberite {t:retention.what.documents}, {t:retention.what.files}, {t:retention.what.mail} ili {t:retention.what.chat}.
4. Za dokumente i datoteke ostavite uključeno {t:retention.everywhere}, ili ga isključite, pritisnite {t:retention.chooseFolder}, odaberite mapu i pritisnite {t:retention.pick}.
5. Upišite {t:retention.keepDays}, {t:retention.removeDays} ili oboje i pritisnite {t:tree.create}.

Pravila stoje pod {t:retention.rules}. U retku pravila {t:retention.editRule} mijenja samo rokove, a {t:retention.dropRule} ga uklanja nakon potvrde u dijalogu {t:retention.dropRuleTitle}

Dok pravila nema, piše {t:retention.noRules}

### Zakonsko čuvanje

1. Na istoj stranici pritisnite {t:retention.newHold}.
2. Pod {t:retention.holdName} upišite naziv predmeta, primjerice broj spisa.
3. Pod {t:retention.subject} odaberite {t:retention.person} pa osobu s popisa ({t:retention.choosePerson}), ili {t:retention.folder} pa mapu.
4. Pritisnite {t:retention.hold}.

Popis pod {t:retention.holds} pokazuje predmet, osobu ili mapu i datum pod {t:retention.since}. Kad predmet završi, u njegovu retku pritisnite {t:retention.release} i potvrdite u dijalogu {t:retention.releaseTitle}

Dok ništa nije pod čuvanjem, piše {t:retention.noHolds}

## Kako radi

### Rok čuvanja

Dokument ili datoteka koji su izmijenjeni unutar roka ne mogu se trajno izbrisati iz smeća, kao ni mapa u kojoj se nalaze. Premještanje u smeće i vraćanje iz njega ostaju dopušteni. Poruka pošte mlađa od roka ne može se trajno izbrisati, a poruka razgovora mlađa od roka ne može se povući; uređivanje poruke ostaje dopušteno. Rok pošte računa se od datuma poruke, a razgovora od trenutka slanja.

Kad nad istim sadržajem vrijedi više pravila, primjerice pravilo za sve mape i pravilo mape iznad dokumenta, vrijedi najduži rok čuvanja.

### Brisanje po pravilu

Jednom na sat Ponistra trajno briše ono što je starije od roka brisanja: dokumente i datoteke po posljednjoj izmjeni, u smeću i izvan njega, poruke pošte po datumu i poruke razgovora po trenutku slanja. Za dokument ili datoteku vrijedi rok brisanja pravila najbliže mape iznad njega, a ako ga nijedna mapa nema, pravilo za {t:retention.everywhere}. Ništa se ne briše prije najdužeg roka čuvanja koji nad njim vrijedi. Mape se ne brišu.

Obrisana poruka pošte ne vraća se pri sljedećem dohvatu s poslužitelja pošte. Poruka razgovora na koju postoji odgovor koji ostaje, ostaje s njim. Razgovor koji napusti posljednji član ostaje dok pravilo ne ukloni i posljednju njegovu poruku. Pod {t:retention.removals} piše koliko je čega obrisano u svakom prolazu koji je nešto obrisao.

### Zakonsko čuvanje

Dok je osoba pod čuvanjem, ništa njezino ne briše se: dokumenti i mape koje je izradila ili posjeduje, sa svime u njima, njezina pošta, poruke koje je napisala i sve poruke razgovora i kanala u kojima je član. Te se poruke ne mogu ni urediti, a njezin se račun ne može izbrisati, samo deaktivirati. Dok je mapa pod čuvanjem, ništa se u njoj ne briše, na bilo kojoj dubini. Brisanje po pravilu preskače sve što je pod čuvanjem.

Gdje se ne smije brisati, radnja je onemogućena. U smeću uz stavku stoji lokot s oznakom {t:retention.kept.held} ili {t:retention.kept.retained}, a u izborniku poruke razgovora isti razlog piše ispod {t:chat.takeBack}.

Svako dodavanje, promjena i uklanjanje pravila te svako postavljanje i otpuštanje čuvanja upisuje se u [dnevnik](help:admin/journal) kao {t:journal.setting.retention} odnosno {t:journal.setting.legal_hold}. Stranica se osvježava sama kad drugi administrator nešto promijeni.

## Ograničenja

- Stranicu otvara samo administrator.
- Rokovi se upisuju u danima, od 1 do 36.500. Rok brisanja ne može biti kraći od roka čuvanja istog pravila, a za istu vrstu i mapu postoji samo jedno pravilo.
- Mape se biraju među onima koje administrator vidi i u koje smije dodavati.
- Za poštu Ponistra briše samo svoju kopiju. Poruke na samom poslužitelju pošte i u drugim aplikacijama ostaju kakve jesu, a brisanje koje naloži poslužitelj ActiveSynca provodi se i za poruke pod čuvanjem.
- Korisnik čija je pošta još u roku čuvanja ne može se izbrisati dok rok ne istekne ili se pravilo ne promijeni.
- Brisanje po pravilu ne može se poništiti.

## Povezano

- [Smeće](help:documents/trash)
- [Dnevnik](help:admin/journal)
- [Korisnici](help:admin/users)
