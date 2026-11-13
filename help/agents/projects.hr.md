# Projekti

Pult radnog prostora za kod: projekti s krugovima i razgovorima, razgovor s agentom ovdje na stranici i tijek svega što ste od radnog prostora tražili.

## Kako se koristi

### Novi razgovor

1. Na traci modula pritisnite {t:rail.projects}.
2. Pronađite projekt. {t:workspace.general} je radni prostor kao cjelina, za razgovore koji ne pripadaju jednom projektu.
3. Pritisnite ikonu {t:workspace.newChat} desno od imena projekta (naziv se pokaže kad mišem prijeđete preko nje).
4. Obrazac se otvara na mjestu razgovora (na telefonu umjesto popisa), s pokazivačem već u polju. U polje {t:workspace.newChatText} upišite prvu poruku ili pritisnite {t:speech.dictate} i izgovorite je. Slike dodajete kao u poruci na stranici.
5. Pritisnite {t:workspace.startChat} ili Enter, kao u poruci na stranici. Razgovor počinje u radnom prostoru i pokaže se na mjestu obrasca; uređivač se ne otvara.

### Povratak u razgovor

1. Na stranici {t:rail.projects} pronađite razgovor ispod njegova projekta. Zatvoreni razgovori stoje iza imena projekta: pritisnite ime.
2. Pritisnite naslov zatvorenog razgovora. Pokaže se uz popis, kao razgovor u radu.
3. Pošaljite mu poruku i radni prostor ga nastavlja. Da ga nastavite u uređivaču, pritisnite {t:workspace.openChat}.

### Razgovor s agentom na stranici

1. Na stranici {t:rail.projects} pritisnite razgovor. Na telefonu se tada otvara {t:workspace.view.chat} (gumbi na vrhu prebacuju između {t:workspace.view.overview}, {t:workspace.view.chat} i [{t:workspace.view.memory}](help:agents/memory)); na računalu popis stoji u lijevom stupcu, kao mape uz dokumente, a razgovor desno od njega, dok ga gumb {t:workspace.view.memory} ne zamijeni memorijom agenta. Svaki se pomiče zasebno, a širina popisa mijenja se povlačenjem tanke crte između popisa i razgovora. Dok ništa ne odaberete, ondje je koordinator zadnjeg kruga.
2. U polje {t:workspace.say} upišite poruku ili pritisnite {t:speech.dictate} i izgovorite je.
3. Za sliku je zalijepite u polje (Ctrl+V), povucite je na polje ili pritisnite {t:workspace.addImage}. Pokaže se umanjena ispod polja; {t:workspace.removeImage} je uklanja prije slanja. Desni klik u polje lijepi tekst iz međuspremnika na mjesto pokazivača, a sliku kad u međuspremniku nema teksta. Ne dopusti li preglednik čitanje međuspremnika, ispod polja piše: {t:error.clipboard_refused}
4. Pritisnite {t:workspace.send} ili Enter; Shift+Enter počinje novi redak, a na telefonu Enter počinje novi redak, pa se šalje gumbom. Za česte riječi pritisnite {t:workspace.quick.catchup}, {t:workspace.quick.continue} ili {t:workspace.quick.handoff}; svaka se šalje odmah. Poslana poruka odmah stoji na dnu razgovora. Dok je agent ne pročita, uokvirena je i ispod nje piše {t:workspace.unread}; agent je čita kad završi korak na kojem radi, a tada postaje dio razgovora.
5. Za tekst agentova odgovora pritisnite {t:workspace.copy} ispod njega; blok koda ima svoj {t:workspace.copy} u gornjem desnom kutu, koji kopira samo kod. Gumb na trenutak pokaže {t:workspace.copied}, a ako preglednik ne dopusti pisanje u međuspremnik, {t:workspace.copyFailed}.
6. {t:workspace.model} na kojemu razgovor radi stoji uz {t:workspace.send}. Pritisnite ga i odaberite drugi; vrijedi od sljedećeg odgovora. Ako razgovor radi u uređivaču, promjena čeka da se smiri, a radni prostor ga tada preuzme. Ponuđeni su modeli koje nudi Claude Code u radnom prostoru, a model ostaje i kad se radni prostor restarta.
7. Dok agent radi ili čeka vas, uz {t:workspace.send} stoji {t:workspace.stop}. Pritisnite ga i agent prekida ono što radi, kao Esc u uređivaču; dopuštenje koje je čekao odbijeno je, a razgovor ostaje otvoren i čeka vašu sljedeću poruku. Razgovor koji radi u uređivaču zaustavlja se ondje, pa je gumb onemogućen.
8. Za cijeli razgovor u uređivaču pritisnite {t:workspace.openChat}. Dok agent radi ili čeka vas, gumb je onemogućen.

### Odgovor razgovoru koji čeka

1. Na stranici {t:rail.projects}, dok neki razgovor čeka, na vrhu popisa stoji {t:workspace.waitingForYou} (na telefonu u {t:workspace.view.overview}, a broj uz taj gumb kaže koliko razgovora čeka).
2. Ondje stoji svaki razgovor koji čeka vaš odgovor ili dopuštenje, s onim što pita.
3. Pritisnite {t:workspace.yes} ili {t:workspace.no}. Na pitanje s ponuđenim odgovorima možete odgovoriti i svojim riječima: odaberite razgovor, upišite ih u polje {t:workspace.say} i pošaljite.

Isti {t:workspace.yes} i {t:workspace.no} stoje i u razgovoru kad je odabran razgovor koji čeka.

### Izbornik razgovora

1. Na stranici {t:rail.projects} desnom tipkom miša pritisnite bilo koji razgovor ili ga dugo pritisnite.
2. Odaberite što treba:
   - {t:workspace.openChat} otvara razgovor u uređivaču. Onemogućeno je dok agent radi ili čeka vas.
   - {t:tree.rename} daje razgovoru novo ime, do 100 znakova; isto ime vidi se u uređivaču i u popisu sesija.
   - {t:workspace.moveUnder} premješta razgovor pod koordinatora drugog kruga istog projekta.
   - {t:workspace.auto}, u izborniku koordinatora, uključuje i isključuje da koordinator sam spoji posao kruga.
   - {t:workspace.close} zaustavlja razgovor u radu, u radnom prostoru i u uređivaču; razgovor ostaje na popisu i nastavlja se porukom ili u uređivaču.
   - {t:workspace.archive} uklanja razgovor s popisa projekta; ako je u radu, najprije se zatvara, kao kod {t:workspace.close}. Uređivač koji pri ponovnom učitavanju vrati karticu arhiviranog razgovora odmah je zatvara. Razgovor koji poslije sami otvorite i ostavite otvorenim dulje od dvije minute vraća se na popis.

### Novi krug

1. Na stranici {t:rail.projects} pritisnite ikonu {t:workspace.newRound} desno od imena projekta.
2. Obrazac se otvara na mjestu razgovora. U polje {t:workspace.newRoundText} upišite što krug treba napraviti, ili pritisnite {t:speech.dictate} ispod polja i izgovorite to. Polje smije ostati prazno: koordinator tada uzima sljedeće korake iz plana projekta.
3. Pritisnite {t:workspace.openRound} ili Enter. Radni prostor pokreće koordinatora s porukom „nastavi: …” i pokaže ga na mjestu obrasca; uređivač se ne otvara.
4. Koordinator podijeli posao na razgovore. Krug se pojavi na stranici, a uz svaki još neposlan razgovor stoji njegov zadatak: pritisnite razgovor da ga pročitate.

### Krug razgovora

1. Na stranici {t:rail.projects} pronađite krug ispod njegova projekta. Krug počinje retkom {t:workspace.coordinator}, razgovorom koji je krug otvorio i nosi njegovo ime, a ispod koordinatora, uvučeni, stoje razgovori kruga.
2. Ako razgovori još nisu krenuli, pritisnite {t:workspace.start}. Radni prostor pokreće svaki razgovor kruga sa zadatkom koji mu je upisan.
3. Pritisnite razgovor kruga da ga pročitate u razgovoru na stranici. {t:workspace.openChat} ga otvara u uređivaču.
4. Kad su svi razgovori kruga gotovi, a koordinator miruje, ispod retka koordinatora pojavi se {t:workspace.consolidate}; pritisnite ga. Koordinator tada spaja posao kruga. Ako je u izborniku koordinatora uključeno {t:workspace.auto}, koordinator to dobije sam čim su svi razgovori kruga gotovi.

5. Kad je posao spojen, provjera ga je našla zelenim, a push ga još nije odnio, ispod retka koordinatora umjesto toga stoji {t:workspace.push}; ako je koordinator krug već zatvorio, gumb stoji ispod njegova retka u popisu razgovora projekta. Pritisnite ga. Koordinator tada pusha posao; izdanje na produkciju i dalje traži vašu izričitu riječ u razgovoru.

### Premještanje u drugi krug

1. Na stranici {t:rail.projects} mišem povucite razgovor na krug istog projekta i pustite ga. Okvir oko kruga pokazuje da ga prima. Isto radi {t:workspace.moveUnder} u izborniku razgovora, i na telefonu.
2. Razgovor ulazi u krug. Ako je bio u drugom krugu, njegov koordinator dobije poruku da razgovor više nije njegov.
3. Razgovor i novi koordinator dobiju poruku o premještanju čim ih mogu pročitati: kad završe korak na kojem rade i ne čekaju vaš odgovor. Razgovor javi koordinatoru svoje korake i područje, a koordinator ga vodi kao ostale i uključuje u {t:workspace.consolidate}.

Koordinator povučen na drugi krug donosi cijeli svoj krug: njegovi razgovori i on sam postaju razgovori tog kruga, a njegov krug nestaje sa stranice. On novom koordinatoru porukom preda stanje svog kruga. Razgovor drugog projekta nijedan krug ne prima, a krugu kojem je naredba {t:workspace.consolidate} ili {t:workspace.push} već poslana ništa se ne premješta dok je ne izvrši.

### Restart radnog prostora

1. Na stranici {t:rail.projects} pritisnite {t:workspace.restart} u zaglavlju.
2. U dijalogu {t:workspace.restartTitle} potvrdite s {t:workspace.restart}. Gumb tada glasi {t:workspace.restarting}, a stranica se vrati kad se radni prostor ponovno javi.

### Projekti uz rad u Ponistri

1. Na računalu pritisnite {t:rail.projects} u traci modula ili odaberite tu naredbu u kutiji za pretraživanje.
2. Stranica se otvara u zasebnom prozoru bez trake modula, smještenom kao prozor sastanka: preko cijelog najvećeg drugog zaslona ako računalo ima više zaslona i dopustili ste upravljanje prozorima, inače preko prozora Ponistre. U Ponistri radite dalje.

Ponovni odlazak na {t:rail.projects} dovodi taj isti prozor u prvi plan, umjesto da otvori novi. {t:meeting.nextScreen} u zaglavlju prozora seli ga na sljedeći zaslon i ispunjava ga, kad računalo ima više zaslona; to traži dopuštenje za upravljanje prozorima u postavkama stranice. Uzak prozor ima gumbe za razgovor i memoriju kao na telefonu, a širok popis i razgovor jedan uz drugi, sa širinom popisa koju mijenjate razdjelnikom kao u kartici Ponistre. Obavijest o radnom prostoru otvara se u tom prozoru dok je otvoren. Novu verziju Ponistre prozor preuzima kad ga sklonite iz vida, osim dok je u njemu otvoren terminal ili neposlana poruka. Ako preglednik ne dopusti zaseban prozor, stranica se otvara u kartici Ponistre i to kaže; skočne prozore dopuštate u postavkama stranice u pregledniku, a ikona {t:workspace.beside} u zaglavlju tada ponovno pokušava. Na telefonu se stranica otvara u kartici. Stranica može imati temu drukčiju od ostatka Ponistre, u kartici i u svom prozoru: {t:frame.theme.projects} u izborniku računa ([Tema i jezik](help:start/appearance)).

### Terminal

1. Na stranici {t:rail.projects} pritisnite ikonu {t:workspace.terminal.open} desno od imena projekta.
2. Ako u zadnjih 8 sati niste potvrdili tko ste, potvrdite to.
3. Terminal se otvara na mjestu razgovora, u mapi projekta. Tipkajte naredbe kao u svakom terminalu; Ctrl+C prekida naredbu. Desni klik lijepi tekst iz međuspremnika, a kad je u terminalu nešto označeno, kopira označeno.
4. Gumb {t:workspace.view.terminal} na vrhu vraća terminal dok gledate razgovor ili memoriju; naredba u njemu za to vrijeme radi dalje.
5. {t:workspace.terminal.close} desno iznad terminala zatvara ga i završava ljusku sa svime što je u njoj pokrenuto.

Kad ljuska završi (naredba `exit`), ispod terminala piše: {t:workspace.terminal.exited} Kad se veza prekine, piše: {t:workspace.terminal.dropped} U oba slučaja {t:workspace.terminal.reopen} otvara novu ljusku u istoj mapi.

## Kako radi

Popis se slaže iz samog radnog prostora: projekt je svaka mapa s Gitom u korijenu radnog prostora, pa se nova mapa pojavi sama. Projekt nosi ime svog plana („Plan DIDA” → DIDA), a bez njega ime mape s velikim početnim slovom. Projekti stoje abecednim redom i ne mijenjaju mjesto kad se na njima radi, a uz svaki stoje razgovori koji su u radu; razgovor otvorenog kruga stoji samo u svom krugu, a kad je krug zatvoren, uvučen ispod svog koordinatora. Desno od imena projekta, u istom retku, mali su gumbi {t:workspace.newRound}, {t:workspace.newChat} i {t:workspace.terminal.open}. Plan projekta otvara se radnjom {t:workspace.openPlan} iz izbornika projekta (desni klik ili dugi pritisak na ime). Ispod imena, uvučen kao razgovori i ne dalje od tih gumba, stoji zadnji push; ostale provjere (preglednik i noćni run) sklopljene su iza strelice s brojem na kraju tog retka ({t:workspace.gate}) i otvaraju se klikom, svaka u svom retku; kad neka provjera nije prošla, strelica je crvena, kao i ta provjera. Projekt na kojemu se trenutno ne radi premješta se radnjom {t:workspace.others.put} iz izbornika projekta (desni klik ili dugi pritisak na ime): stoji na dnu pod {t:workspace.others}, s brojem takvih projekata, i otvara se klikom. Čim u njemu počne razgovor ili krug, sam se vraća u glavni popis i ondje ostaje; {t:workspace.others.back} ga vraća ručno. Izbor se pamti uz račun, isti na svakom uređaju. {t:workspace.general} je uvijek na vrhu. Klik na ime projekta pokaže i ostale od njegovih 5 zadnjih razgovora, svaki s ostatkom svog kruga, a broj uz ime kaže koliko ih je. Stranica prati radni prostor: kad razgovor počne ili prestane raditi, zastane na pitanju, krug se promijeni ili provjera projekta završi, stranica se osvježi sama, na svakom uređaju na kojemu je otvorena.

Razgovore vodi sam radni prostor: za svaki drži jedan proces Claude Codea, pa ni novi razgovor ni krug, ni poruka, odgovor, ime ili zatvaranje ne otvaraju uređivač. {t:workspace.openChat} na telefonu otvara samo razgovor, bez ostatka uređivača, a na računalu cijeli uređivač s tim razgovorom. Svaki projekt ima svoju karticu preglednika, pa razgovor istog projekta dolazi u nju. Razgovor je zapisan u radnom prostoru, pa se u uređivaču otvara isti razgovor; radni prostor tada pušta svoj proces, jer jedan razgovor nikad ne radi u dva procesa. Radi li ipak u dva, primjerice u prozoru uređivača koji je ostao otvoren, radni prostor zaustavlja stariji čim miruje. Poruka razgovoru koji radi u uređivaču čeka da on završi korak, a onda ga radni prostor preuzima. Nakon restarta radni prostor sam nastavlja razgovore koje je vodio.

Oznaka {t:workspace.inUse} stoji uz razgovor koji radi, u radnom prostoru ili u uređivaču, a umjesto nje stanje kad agent radi ili čeka vas.

Razgovor na stranici pokazuje zadnja dva vaša pitanja i sve nakon njih; {t:workspace.earlier} na vrhu dohvaća prethodna, a vaše zadnje pitanje ostaje prikovano na vrhu dok čitate ispod njega. Vaše poruke stoje desno, agentove lijevo s oblikovanjem (podebljano, kod, popisi, tablice), ono što je agentu javio sam alat (pozadinski zadatak je završio, stigla je poruka druge sesije, razgovor je sažet) kao kratak redak u sredini, a uzastopne pozive alata složene u jedan redak s brojem alata, koji se otvara klikom. Dok agent radi, razgovor se osvježava svakih pet sekundi, inače kad agent završi korak. Poruka ne ide kroz AI Ponistre: svaka je redak u bazi Ponistre, a radni prostor je predaje procesu tog razgovora, kao da ste je sami napisali. Slike idu s porukom; uz poruku sa slikama razgovor na stranici pokazuje njihov broj. Slika veća od 1568 točaka po duljoj stranici prije slanja se smanjuje. {t:workspace.yes} i {t:workspace.no} odgovaraju na dopuštenje ili pitanje koje je razgovor postavio.

Svaki razgovor ima dva retka. U prvom su naslov, stanje i vrijeme zadnje promjene; stanje i vrijeme imaju svaki svoj stupac, jednak u cijelom popisu, pa predug naslov skraćen je trotočjem prije njih. U drugom, sitnije, stoji {t:workspace.coordinator} kad je to koordinator kruga, ime sesije kad se razlikuje od naslova i dvije mjere:

- {t:workspace.changes}: broj datoteka koje je taj razgovor mijenjao i koje imaju necommitane promjene, s dodanim i obrisanim retcima. Broje se datoteke koje je agent pisao svojim alatima za uređivanje; promjena naredbom iz terminala tu se ne vidi. Razgovori kruga rade u istom stablu, pa mjera kaže koliko necommitanog posla stoji u datotekama tog razgovora.
- {t:workspace.context}: koliko je tokena agent zadnji put pročitao, u tisućama. Iznad 300 000 broj je istaknut ({t:workspace.contextLarge}), jer svaki sljedeći korak tada stoji višestruko više od koraka u svježem razgovoru.

Na vrhu popisa, pod naslovom {t:workspace.host}, stoji stanje poslužitelja na kojem radi radni prostor, svaka vrijednost uz svoju ikonu i kao postotak: {t:workspace.host.cpu} (opterećenje u zadnjoj minuti prema broju procesorskih niti poslužitelja), {t:workspace.host.memory}, {t:workspace.host.swap} (kad ga poslužitelj ima) i {t:workspace.host.disk} na kojemu su projekti. Od 90 % vrijednost je crvena. Ako zadržite pokazivač na vrijednosti, piše koliko je zauzeto od ukupnog, a na procesoru opterećenje i broj niti. Radni prostor stanje mjeri svaki put kad ga stranica čita: pri otvaranju, pri svakoj promjeni koju stranica pokazuje i kad se vratite na nju. Klik na vrijednosti ({t:workspace.host.measure}) mjeri odmah.

Ispod njega, pod naslovom {t:workspace.limits}, stoje limiti pretplate Claude Codea u radnom prostoru, svaki kao traka s postotkom potrošenog: {t:workspace.limits.session} (petosatni prozor, kad postoji), {t:workspace.limits.week} i tjedni limit pojedinog modela, primjerice Fable. Od 80 % traka je crvena. Ako zadržite pokazivač na traci, piše kad se limit obnavlja. Kad su uključeni krediti koji se plaćaju odvojeno od pretplate, ispod stoji {t:workspace.limits.credits} s iznosom, a kad model nakon svog limita radi na kreditima, umjesto toga crveno stoji {t:workspace.limits.spending} s iznosom. Radni prostor limite mjeri sam, svakih pet minuta i nakon koraka razgovora koji vodi, programom Claude Codea, bez ijednog tokena i bez prijave izvan njega, a stranica se nakon svakog mjerenja osvježi sama. Desno u retku naslova stoji {t:workspace.limits.measured} s vremenom zadnjeg mjerenja. Klik na trake ili na vrijeme ({t:workspace.limits.measure}) mjeri odmah i pokazuje novo stanje za sekundu ili dvije.

Plan projekta je ploča naslova „Plan <ime>” koju možete čitati. Plan „Plan OPUS” pripada i mapama `opus-library` i `opus-player`, jer se ime projekta poklapa i s početkom mape; takav projekt nosi ime svoje mape.

Projekt s provjerama (mapa `.git/ponistra-check`) pokazuje stanje vrata kad otvorite {t:workspace.gate} ispod imena:

- {t:workspace.gate.checked}: kad je posljednji put prošla provjera pred push.
- {t:workspace.gate.browser}: testovi u pregledniku koji se pokreću nakon pusha, {t:workspace.gate.passed} ili {t:workspace.gate.failed}, s vremenom.
- {t:workspace.gate.night}: noćni run svih testova, a uz pad broj palih testova.

Dok se run vrti, umjesto ishoda stoji {t:workspace.gate.running}. Ishod za stablo koje nije zadnje pushano nosi dodatak {t:workspace.gate.older}. Pad je istaknut.

Krug je skup razgovora u jednom projektu koje je koordinator otvorio odjednom, svakoga sa svojim zadatkom. Koordinator sam dobije ime kruga, cilj kruga u nekoliko riječi koji mu je dao pri podjeli („Kod: limiti i memorija”), u krugu i u popisu sesija; krug bez imena koordinator zove {t:workspace.coordinator}. Razgovor kojemu zadatak još nije poslan nosi naslov iz prvog retka zadatka. Uz svaki razgovor kruga stoji njegovo stanje i vrijeme zadnje promjene:

- {t:workspace.state.new}: zadatak je upisan, ali još nije poslan. Pritisak na takav razgovor pokaže cijeli zadatak.
- {t:workspace.state.working}: agent radi.
- {t:workspace.state.background}: agent je završio potez, ali naredba koju je pokrenuo u pozadini, recimo provjera, još radi.
- {t:workspace.state.waiting}: agent čeka vaš odgovor ili dopuštenje. Ako zadržite pokazivač na oznaci, piše što čeka.
- {t:workspace.state.idle}: agent je završio i čeka sljedeću poruku.
- {t:workspace.state.closed}: razgovor ne radi ni u radnom prostoru ni u uređivaču.

{t:workspace.consolidate} i {t:workspace.push} šalju tu riječ koordinatoru, kao da ste je sami napisali. Dok je koordinator nije uzeo, ispod retka kruga piše koja mu je riječ poslana, a nijedan od ta dva gumba se ne nudi. {t:workspace.push}, {t:workspace.restart} i terminal prije slanja traže ponovnu potvrdu identiteta ako zadnja nije iz posljednjih 8 sati.

{t:workspace.auto} je uključeno za svaki novi krug. Kad su svi razgovori kruga gotovi, a koordinator ne radi, koordinator dobije „objedini sam od sebe” i spaja krug bez pitanja. Gotov je razgovor koji je odradio barem jedan korak i stao; tek pokrenut razgovor, koji još nije ništa napisao, nije gotov. Riječ koju koordinator nije uzeo prije nego što je krug zatvoren više se ne predaje. Naiđe li na pitanje, grešku ili razgovor koji još radi, staje i javlja vam se; krug tada čeka vas. Push nikad ne ide sam od sebe. Kad se krug zatvori, njegovi razgovori se zatvaraju i arhiviraju; koordinator ostaje na popisu dok ne završi svoj posao. Arhivirani razgovor koji poslije sami otvorite ostaje na popisu.

Naredba poslana razgovoru (poruka, odgovor, novo ime, {t:workspace.openChat}, {t:workspace.close}, {t:workspace.consolidate}, {t:workspace.push}, {t:workspace.archive} ili {t:workspace.stop}) stoji na dnu tog razgovora sa stanjem dok se ne izvrši: {t:workspace.progress.sent}, {t:workspace.progress.taken} (radni prostor ju je primio) ili {t:workspace.progress.failed} s razlogom; kad je {t:workspace.progress.done}, nestaje. Ako arhiviranje ne uspije, razlog se pokaže i ispod retka razgovora, a ako razgovor ne prijeđe u uređivač, na vrhu stranice. Stanje se mijenja samo, na svakom uređaju.

Dok u krugu ima neposlanih razgovora koji nisu pokrenuti, ispod imena kruga stoji istaknuta traka {t:workspace.startWaiting} s gumbom {t:workspace.start}. Kad koordinator zatvori krug, krug nestaje sa stranice, a radni prostor zaustavlja njegove razgovore. Koordinatora zaustavlja tek kad miruje, jer on nakon spajanja još pusha, izdaje i restarta, i ne zaustavlja ga ako vodi neki drugi krug koji je još otvoren. Zaustavljeni koordinator nastavlja se porukom sa stranice ili u uređivaču. U uređivaču krug stoji kao grupa u popisu sesija, koju svaki panel složi kad se učita.

Restart ponovno stvara radni prostor iz njegove Docker Compose definicije, s njegovom najnovijom slikom. Prekida sve razgovore; one koje vodi radni prostor nastavlja sam, a ostali se nastavljaju porukom ili u uređivaču. Zato je gumb onemogućen dok neki razgovor radi ili čeka vas, i dok se u radnom prostoru vrti {t:workspace.check} (noćni ili preglednički run) ili {t:workspace.release}; zadržite pokazivač na gumbu da vidite što radi. Run koji se vrti izvan radnog prostora, primjerice noćni na poslužitelju, restart ne prekida.

Terminal je ljuska bash vlasnika radnog prostora, ista kao u terminalu uređivača: vidi iste datoteke, Git, Docker i alate. Svaki terminal na stranici svoja je ljuska u radnom prostoru i živi dok je stranica otvorena; zatvaranje terminala, prelazak na drugu stranicu, novi terminal za drugi projekt ili prekid veze završavaju je, a s njom i ono što je u njoj pokrenuto. Za posao koji mora preživjeti zatvaranje koristite terminal uređivača ili `nohup`. Ono što ljuska ispiše ide kroz Ponistru do preglednika i nigdje se ne sprema. Boje terminala prate temu sučelja. Na računalu je terminal visok koliko i stranica, a na telefonu tri petine zaslona. Istodobno može biti otvoreno najviše osam terminala.

Promjena u radnom prostoru vlasniku šalje i push obavijest: razgovor čeka odluku, krug je spreman, krug je objedinjen, pao je preglednički ili noćni run, a koordinator kruga završio je korak s porukom ili čeka vaš unos. Javlja se i kad tjedni limit pretplate ili limit pojedinog modela prijeđe 80 %, te kad model nakon svog limita počne trošiti kredite, svako jednom po tjednu limita. Obavijest o razgovoru ili koordinatoru koji čeka nosi gumbe {t:workspace.yes} i {t:workspace.no}, koji odgovaraju kao u razgovoru na stranici, bez otvaranja Ponistre; ako odgovor ne prođe, otvara se stranica Projekti. Koje obavijesti stižu, uređuje se u [Obavijesti](help:account/notifications).

## Ograničenja

Stranica postoji samo za vlasnika radnog prostora za kod.

- {t:error.not_the_owner} Radni prostor vidi samo korisnik kojemu je dodijeljen.
- {t:error.workspace_not_linked} Instalacija nema token radnog prostora. Upisuje ga administrator instalacije.
- {t:error.workspace_unreachable} Radni prostor nije pokrenut ili mu je token drukčiji od onoga u instalaciji. Javlja se i nekoliko sekundi tijekom restarta.
- {t:error.no_round} Krug je u međuvremenu zatvoren i obrisan. Stranica se osvježi sama.
- {t:error.round_closed} Koordinator je krug već zatvorio, pa se više ne pokreće ni ne spaja.
- {t:error.no_chat} Razgovor više ne postoji u radnom prostoru.
- {t:error.no_project} Mapa nije projekt radnog prostora.
- {t:error.asked} Koordinatoru je već poslana riječ koju još nije uzeo.
- {t:error.not_waiting} Razgovor je u međuvremenu dobio odgovor.
- {t:error.chat_working} Razgovor je počeo raditi ili pitati između pritiska i predaje, pa nije otvoren u uređivaču.
- {t:error.chat_busy} Poruka razgovoru koji radi u uređivaču čeka da završi korak; ako ga ne završi unutar sata, poruka propada.
- {t:error.no_agent} U radnom prostoru nije instalirana ekstenzija Claude Code, čiji program vodi razgovore.
- {t:error.not_ended} Proces razgovora nije se zaustavio.
- {t:error.too_many_images} Uz poruku idu najviše četiri slike; višak se ne dodaje.
- {t:error.image_type} Slika nije PNG, JPEG, GIF ni WebP.
- {t:error.image_too_large} Slika je i nakon smanjenja veća od 3,75 MB. GIF se ne smanjuje.
- {t:error.image_unread} Preglednik nije mogao smanjiti sliku.
- {t:error.invalid_images} Uz poruku idu samo slike koje ste sami učitali, u dopuštenoj vrsti i veličini.
- {t:error.known_command} Radni prostor je istu naredbu već primio.
- {t:error.invalid_command} Radni prostor ne poznaje tu naredbu.
- {t:error.invalid_session} Naredba ne nosi valjanu oznaku razgovora.
- {t:error.invalid_round} Naredba ne nosi valjanu oznaku kruga.
- {t:error.workspace_busy} Između otvaranja stranice i potvrde nešto je počelo raditi.
- {t:error.restart_running} Prethodni restart još traje.
- {t:error.no_docker} Radni prostor nema pristup Dockeru pa se gumb za restart ne prikazuje; instalacija ga dobiva samo ako je agentu dan Docker.
- {t:error.not_in_docker} Radni prostor nije pokrenut kao Docker kontejner.
- {t:error.not_from_compose} Radni prostor nije pokrenut kroz Docker Compose, pa nema definicije iz koje bi se ponovno stvorio.

Razgovor bez naslova, primjerice onaj u kojemu još nije bilo odgovora, ne stoji na popisu. Limiti su jedne pretplate, one kojom je prijavljen Claude Code u radnom prostoru, pa ih troše i razgovori izvan njega; stranica pokazuje stanje zadnjeg mjerenja, najviše pet minuta staro. Claude Code taj podatak daje kao probni, pa oblik koji radni prostor ne prepozna javlja kao {t:workspace.limits.unread}, umjesto da pokaže nulu. Ne može li radni prostor pročitati stanje poslužitelja, umjesto vrijednosti stoji {t:workspace.host.unread}.

## Povezano

- [Memorija agenta](help:agents/memory)
- [Povezivanje vanjskog agenta](help:agents/connecting)
- [Glasovne naredbe](help:start/voice)
- [Obavijesti](help:account/notifications)
- [Okvir aplikacije](help:start/overview)
