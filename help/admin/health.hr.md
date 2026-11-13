# Stanje sustava

Administrator na jednom mjestu vidi inačicu instalacije, probleme koje je Ponistra sama našla, odgovaraju li njezine usluge, sigurnosne kopije, zauzeti prostor i ono što čeka u redovima.

## Kako se koristi

1. U {t:settings.title}, pod {t:settings.installation}, odaberite {t:health.title}.
2. Ako na vrhu stoji {t:health.problems}, pročitajte što ne radi i od kada.
3. Pod {t:health.services} pogledajte piše li uz svaku uslugu {t:health.answers} ili {t:health.silent}.
4. Pod {t:health.snapshots} provjerite {t:health.snapshots.newest} i {t:health.snapshots.due}.
5. Pod {t:health.storage} i {t:health.queues} pogledajte koliko je prostora zauzeto i što čeka.

## Kako radi

Na vrhu stranice piše {t:status.version} instalacije. Stranica se sama ponovno učitava svakih 30 sekundi.

### Problemi

Dok radi, Ponistra svakih 5 minuta sama provjerava isto što prikazuje ova stranica. Problem se prijavljuje tek kada potraje: usluga koja ne odgovara nakon 10 minuta, red čekanja nakon sat vremena u kojem stavke čekaju, a nijedna nije gotova, a zakašnjele sigurnosne kopije ({t:health.problem.snapshots}) i arhiviranje izmjena baze ({t:health.problem.archive}) nakon sat vremena, jer toliko može trajati prva kopija nakon ažuriranja. [Izvor korisnika](help:admin/sources) koji se ne može pročitati ({t:health.problem.source}) prijavljuje se nakon 2 sata, uz njegov naziv. Zakašnjela {t:health.offsite} ({t:health.problem.offsite}) i disk s manje od 10 % slobodnog prostora prijavljuju se odmah.

Prijavljeni problem stoji pod {t:health.problems} uz vrijeme kada je prvi put uočen ({t:health.problems.since}), upisuje se u [dnevnik](help:admin/journal) i stiže kao obavijest u preglednike svih administratora koji su uključili obavijesti. Red koji stoji opisan je riječima {t:health.problem.queue}, a disk riječima {t:health.problem.disk}. Kada problem prestane, nestaje sa stranice, a u dnevnik se upisuje da je riješen.

### Usluge

{t:health.service.database}, {t:health.service.converter}, {t:health.service.printer}, {t:health.service.ocr} i {t:health.service.meetings} provjeravaju se pri svakom učitavanju. {t:health.service.relay} prikazuje se samo na instalaciji koja ga ima, a {t:health.service.outside} samo kad je u [Relej sastanaka](help:admin/meetings) postavljen vanjski relej; tada se provjerava daje li pružatelj vjerodajnice.

### Sigurnosne kopije

Sigurnosne kopije rade se svake noći i prije svakog ažuriranja. Uz {t:health.snapshots.newest} i {t:health.snapshots.due} piše kada je napravljena posljednja i kada se radi iduća, a uz {t:health.snapshots.count} koliko ih se čuva. Ako noćna kopija izostane, ovdje se pojavljuje upozorenje s naredbom koja prikazuje razlog, a dok kopije još nema, piše: {t:health.snapshots.none}

Između dviju kopija Ponistra svakih 15 minuta sprema promjene baze i nove datoteke, a uz {t:health.snapshots.archived} piše kada su posljednji put spremljene. Ne može li ih spremiti uopće, piše {t:health.snapshots.archiveError} s razlogom, a ne stigne li ih spremiti na vrijeme: {t:health.snapshots.archiveLate} Tako se instalacija na poslužitelju može vratiti na bilo koji trenutak posljednjih 7 dana: `ponistra restore "2026-11-10 14:35"`. Bez trenutka `ponistra restore` vraća najnovije stanje koje kopije imaju, a s oznakom kopije onakvo kakvo je bilo kad je kopija napravljena. Datoteka koju više ništa ne koristi ostaje na disku još 7 dana, jer je može zatrebati baza vraćena na raniji trenutak.

### Prostor i redovi

Pod {t:health.storage} piše koliko zauzimaju {t:health.stored.database} i {t:health.stored.files}, uz {t:health.stored.dead} koliko zauzimaju izbrisane datoteke koje još čekaju, a za svaki disk koliko je na njemu slobodno. Disk se naziva po onome što drži: {t:health.disk.files}, {t:health.disk.snapshots} ili {t:health.disk.both}.

Pod {t:health.queues} piše koliko stavki čeka u svakom redu: {t:health.queue.jobs} (koje čekaju ili traju), {t:health.queue.ocr}, {t:health.queue.text} i {t:health.queue.batches}. Red {t:health.queue.unread} broji datoteke koje su pregledane, ali se u njima ne može pretraživati, jer su oštećene ili prevelike.

## Ograničenja

- Stranicu otvara samo administrator.
- Dok kopija izvan poslužitelja nije postavljena, propadne li poslužitelj, propadaju i sigurnosne kopije.
- Na trenutak se vraća najviše 7 dana unatrag; starije kopije vraćaju se samo onakve kakve su bile kad su napravljene.
- Vraćanje na trenutak zaustavlja Ponistru dok traje.
- Obavijest o problemu stiže samo administratoru koji je u nekom pregledniku uključio obavijesti, i samo dok instalacija šalje obavijesti.
- Dok poslužitelj ne radi, ne provjerava ni samoga sebe: o ugašenom poslužitelju ne stiže obavijest.

## Povezano

- [Kopija izvan poslužitelja](help:admin/offsite)
- [Dnevnik](help:admin/journal)
- [Obavijesti](help:account/notifications)
