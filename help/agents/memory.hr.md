# Memorija agenta

Pregled memorije koju Claude Code u radnom prostoru za kod čuva po projektu, s prijedlozima ispravaka koje prihvaćate ili odbijate i poviješću iz koje se svaka promjena vraća.

## Kako se koristi

### Pregled memorije

1. Na traci modula pritisnite {t:rail.projects}.
2. Pritisnite {t:workspace.view.memory} na vrhu stranice.
3. Pod {t:memory.stores} stoji spremište svakog projekta. Pritisnite redak spremišta da vidite njegove nalaze, složene po vrsti.

### Prijedlog za memoriju

1. Dok prijedlozi čekaju, uz {t:workspace.view.memory} na vrhu stranice {t:rail.projects} stoji njihov broj. Pritisnite {t:workspace.view.memory}.
2. Pod {t:memory.proposals} svaki prijedlog pokazuje datoteku, projekt, vrstu, razlog kad ga ima i izmjenu: obrisani retci precrtani, dodani istaknuti. {t:memory.removes} znači da prijedlog briše cijelu datoteku, a {t:memory.creates} da je stvara. Kad ništa ne čeka, piše {t:memory.none}
3. Pritisnite {t:memory.accept} da se izmjena upiše, ili {t:memory.reject} da se odbaci.

Na telefonu ili računalu s uključenim obavijestima isto rade gumbi {t:workspace.yes} i {t:workspace.no} u obavijesti o prijedlogu.

### Povratak promjene

1. Na kartici {t:workspace.view.memory} pronađite promjenu pod {t:memory.history}.
2. Pritisnite {t:memory.revert}. Datoteka se vraća kakva je bila prije promjene, a uz redak tada stoji {t:memory.reverted}.

### Analiza memorije

1. Na kartici {t:workspace.view.memory} pritisnite {t:memory.analyse} za sva spremišta, ili {t:memory.analyseStore} u retku jednog spremišta.
2. Radni prostor pokreće novi razgovor s agentom, a na kartici piše {t:memory.analysing} Razgovor se vidi i na popisu stranice {t:rail.projects}.
3. Prijedlozi analize stižu pod {t:memory.proposals} kako ih agent piše.

### Analiza prijedloga

1. Dok prijedlozi čekaju, na kartici {t:workspace.view.memory} pritisnite {t:memory.review}.
2. Agent u novom razgovoru pročita otvorene prijedloge i složi ih u skupine, svaku s naslovom, razlogom i preporukom: {t:memory.advice.accept}, {t:memory.advice.reject} ili {t:memory.advice.look}. Kad su skupine spremne, stiže obavijest.
3. Pod {t:memory.proposals} gumbom uz skupinu prihvatite ili odbijte sve njezine prijedloge odjednom; gumb nosi njihov broj, a preporučena radnja je istaknuta. Prijedlozi koji su se u međuvremenu promijenili u istom retku zastarijevaju, a uz skupinu piše koliko ih je. {t:memory.showProposals} otvara prijedloge skupine, o kojima možete odlučiti i pojedinačno.
4. Prijedlozi koje analiza nije svrstala stoje pod {t:memory.unsorted}.

### Noćni prolaz

1. Na kartici {t:workspace.view.memory} uključite {t:memory.nightly}.
2. Svake noći u 4 sata memorija se ponovno pročita, a ono što se od zadnje analize promijenilo analizira se kao kod {t:memory.analyse}. Isključivanjem kvačice prolaz prestaje.

## Kako radi

Radni prostor čita svaku mapu memorije svojih projekata, `~/.claude/projects/<projekt>/memory/`, i javlja Ponistri čim se neka datoteka u njoj promijeni; kartica se tada osvježi sama, na svakom uređaju. Za svako spremište pokazuje {t:memory.files} (broj datoteka), {t:memory.indexLines} (retci indeksa `MEMORY.md`, koji Claude Code učitava u svaku sesiju tog projekta), {t:memory.tokens} (koliko tokena taj indeks dodaje svakoj sesiji, procjena od 4 bajta po tokenu) i {t:memory.findings}. Indeks dulji od 200 redaka označen je s {t:memory.cut}

Nalazi su mehanički, bez modela:

- {t:memory.finding.orphan}: datoteka koju indeks ne navodi, pa je sesija ne nalazi.
- {t:memory.finding.dangling}: redak indeksa koji pokazuje na datoteku koje nema.
- {t:memory.finding.link}: poveznica `[[ime]]` na memoriju koja ne postoji.
- {t:memory.finding.frontmatter}: zaglavlju nedostaje `name`, `description` ili `type`.
- {t:memory.finding.oversize}: datoteka veća od 25 000 bajtova, a pravilo ili referenca veća od 8 000.
- {t:memory.finding.long}: indeks ima više od 145 redaka ili 26 000 bajtova.
- {t:memory.finding.stale}: datoteka ili ime u kodu koje memorija navodi, a u repozitoriju projekta ga više nema.
- {t:memory.finding.unreadable}: datoteka se ne može pročitati kao tekst.

Iz istog čitanja nastaju mehanički prijedlozi:

- {t:memory.kind.state}: redak s datumom koji kaže da je posao necommitan ili nepushan, a datoteke koje navodi git već bilježi kao commitane; prijedlog upisuje commit i izdanje koje ga nosi, ili da je pushan.
- {t:memory.kind.path}: putanja koje više nema zamjenjuje se jedinom datotekom istog imena u istim mapama.
- {t:memory.kind.time}: vrijeme u UTC-u u retku koji navodi datum pretvara se u lokalno vrijeme tog dana (CET/CEST); vrijeme unutar oznake koda ostaje, kao i vrijeme bez datuma, jer se ponavlja, a lokalni sat mu se mijenja s ljetnim računanjem vremena.
- {t:memory.kind.link}: poveznica `[[ime]]` ispravlja se na postojeće ime memorije.
- {t:memory.kind.index}: iz indeksa se brišu retci bez datoteke, a dodaju retci za pravila i reference koje indeks ne navodi.
- {t:memory.kind.frontmatter}: zaglavlje se dopunjuje imenom i vrstom.

{t:memory.kind.session} je prijedlog koji je napisao agent. Analiza šalje agentu u radnom prostoru samo datoteke promijenjene od zadnje analize, najviše 80 odjednom, a ostale u sljedećoj. Agent traži duplikate unutar spremišta, proturječja među memorijama i s `CLAUDE.md` projekta, pravila ponovljena u tri ili više spremišta, koja predlaže jednom za globalni `~/.claude/CLAUDE.md`, i preduge retke indeksa. Datoteke sam ne mijenja: svaki prijedlog šalje alatom `propose_memory` kroz MCP Ponistre, s razlogom od jedne rečenice. Razgovor radi na pretplati Claude Codea u radnom prostoru, ne na AI-ju Ponistre.

Prijedlog pamti sadržaj datoteke iz kojega je nastao. {t:memory.accept} upisuje izmjenu samo ako je datoteka i dalje točno takva; upis je cjelovit, pa sesija nikad ne pročita napola upisanu datoteku. Ako se datoteka u međuvremenu promijenila u drugim retcima, primjerice prihvaćanjem drugog prijedloga za istu datoteku, izmjena se upisuje preko te promjene. Ako je promijenjen isti redak, prijedlog zastarijeva i nestaje s popisa, a mehanički prijedlog nastaje iznova iz novog sadržaja. Isto vrijedi za {t:memory.revert}. Odbijen mehanički prijedlog ne nudi se ponovno dok se datoteka ne promijeni. Povijest pokazuje zadnjih 30 upisanih i vraćenih promjena.

Za svaki novi prijedlog vlasnik dobiva push obavijest: o jednom s gumbima {t:workspace.yes} i {t:workspace.no}, o više njih s brojem. {t:memory.review} agentu daje samo izvadak svakog prijedloga (promijenjene riječi s malo teksta oko njih) kroz alat `memory_proposals`, a skupine vraća alatom `advise_memory`; nova analiza zamjenjuje skupine prethodne. Skupina se prihvaća prijedlog po prijedlog redom kojim su nastali, pa se dva prijedloga za istu datoteku upisuju jedan preko drugoga. Obavijest otvara karticu {t:workspace.view.memory}.

## Ograničenja

Kartica postoji samo za vlasnika radnog prostora za kod, a alate `propose_memory`, `memory_proposals` i `advise_memory` prima samo njegov agent. Ponistra memoriju čita i upisuje samo kroz radni prostor, pa bez njega kartica javlja grešku.

- {t:error.not_the_owner} Memoriju vidi samo korisnik kojemu je radni prostor dodijeljen.
- {t:error.workspace_unreachable} Radni prostor nije pokrenut ili mu je token drukčiji od onoga u instalaciji.
- {t:error.memory_changed} Datoteka se promijenila otkad je prijedlog napisan ili promjena upisana; pročitajte novi prijedlog.
- {t:error.memory_decided} O prijedlogu je već odlučeno, primjerice na drugom uređaju ili iz obavijesti.
- {t:error.memory_analysed} Nijedna datoteka nije se promijenila od zadnje analize.
- {t:error.memory_nothing_waiting} Nema otvorenih prijedloga za analizu.

Mehanički nalazi ne razumiju sadržaj: ime koje je namjerno staro, primjerice u zapisu povijesti, i dalje se javlja kao {t:memory.finding.stale}.

## Povezano

- [Projekti](help:agents/projects)
- [Povezivanje vanjskog agenta](help:agents/connecting)
- [Obavijesti](help:account/notifications)
