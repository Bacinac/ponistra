# Rezultati pretrage i filtri

Stranica {t:search.title} prikazuje sve pogotke po skupinama i sužava ih filtrima vrste, osobe, računa, mape, datuma i privitka.

## Kako se koristi

### Stranica rezultata

1. U kutiji za pretragu pritisnite {t:search.all} ili {k:Enter}.
2. Riječi mijenjate u polju na vrhu stranice i pritisnete {t:search.label}.
3. Pogoci su razvrstani u skupine {t:search.documents}, {t:search.mail}, {t:search.conversations}, {t:search.events}, {t:search.tasks}, {t:search.people}, {t:search.vault}, {t:search.versions} i {t:search.help}. Pritisnite pogodak da biste ga otvorili. Poruka iz zajedničkog sandučića otvara se u njemu.
4. Ako ste tražili u jednoj mapi, iznad pogodaka stoji {t:search.in} s nazivom mape. Križić uz nju ({t:search.everywhere}) traži posvuda.

### Dodavanje filtra

1. Pritisnite {t:search.filter.add}.
2. Pod {t:search.kind} odaberite {t:search.kind.document}, {t:search.kind.file}, {t:search.kind.link}, {t:search.kind.folder}, {t:search.kind.mail}, {t:search.kind.event}, {t:search.kind.task}, {t:search.kind.person}, {t:search.kind.vault} ili {t:search.kind.version}.
3. Pod {t:search.filter.date} odaberite {t:search.last.week}, {t:search.last.month} ili {t:search.last.year}.
4. {t:search.filter.has} ostavlja samo poštu s privitkom.
5. Filtar se prikazuje kao oznaka iznad pogodaka. Križić na oznaci ({t:search.filter.remove}) uklanja ga.
6. Na oznaci datuma pritisnite njezin naziv da biste dokumente tražili po datumu izmjene umjesto nastanka ({t:search.filter.toChanged}) i obrnuto ({t:search.filter.toMade}).

### Upisivanje filtra

1. Filtar upišite među riječi u kutiju ili u polje na vrhu, kao naziv, dvotočku i vrijednost bez razmaka.
2. {t:search.token.kind}:{t:search.value.document} traži jednu vrstu, a vrijednost može biti i početak riječi kad ga ima samo jedna vrsta.
3. {t:search.token.from}:ime traži pošiljatelja poruke, autora dokumenta te organizatora ili pozvanog na događaju.
4. {t:search.token.account}:riječ traži poštu računa čija adresa ili naziv sadrži tu riječ.
5. {t:search.token.folder}:naziv traži u mapi tog naziva. Riječi pristigla, skice, poslano, arhiva, nezeljena, spam i smece traže u toj mapi pošte svih računa.
6. {t:search.token.date}:razdoblje traži po datumu nastanka, a {t:search.token.changed}:razdoblje po datumu izmjene. Razdoblje je godina (2025), mjesec (2025-02 ili 2.2025.), dan (2025-02-03 ili 3.2.2025.), {t:search.value.week}, {t:search.value.month} ili {t:search.value.year} (posljednjih 7, 30 ili 365 dana), ili raspon s dvije točke (2025-01..2025-03), otvoren na bilo kojoj strani.
7. {t:search.token.has} traži poštu s privitkom.
8. Vrijednost s razmakom stavite u navodnike: {t:search.token.from}:"Ana Kovač".

## Kako radi

Na oznaci filtra piše što sužava: {t:search.kind}, {t:search.filter.from}, {t:search.filter.account}, {t:search.filter.folder}, {t:search.filter.date} ili {t:search.filter.changed}, a razdoblje kao raspon dana ili s {t:search.filter.since} i {t:search.filter.until}. Nazivi filtara i njihove vrijednosti prepoznaju se na hrvatskom i na engleskom, bez obzira na jezik sučelja, a slova sa i bez kvačica smatraju se istima.

Filtar ostavlja samo skupine koje ga mogu zadovoljiti. Račun, privitak i mapa pošte ostavljaju samo poštu. Mapa ostavlja dokumente i poštu. Razdoblje se za događaj odnosi na vrijeme održavanja, a za zadatak na rok; ljudi nemaju datum pa ih filtar razdoblja izostavlja. Ranije verzije dokumenata prikazuju se samo uz {t:search.token.kind}:{t:search.value.version}. Filtar bez riječi prikazuje sve što ga zadovoljava.

Svaka skupina prikazuje najviše 50 pogodaka. Uz dokument stoji datum zadnje izmjene i, kad ih je više, {t:search.hits} s brojem pogodaka u njemu. Uz poruku stoji {t:search.hits}, uz ponavljajući događaj {t:search.occurrences}, jer je cijeli niz jedan pogodak, a uz dokument među verzijama {t:search.versionHits} s brojem verzija koje sadrže riječi.

Pretraga u mapi traži samo dokumente u njoj i njezinim podmapama.

Skupinu {t:search.conversations} možete tražiti i filtrom vrste {t:search.value.conversation}, koji se u kutiji prikazuje kao {t:search.kind.conversation}.

## Ograničenja

- Kad je skupina puna, ispod nje piše: {t:search.limited}
- Filtar bez vrijednosti javlja: {t:search.error.empty}
- Nepoznata vrsta javlja: {t:search.error.invalid_kind} Vrijede i ostale vrste s popisa iznad.
- Datum koji se ne može pročitati javlja: {t:search.error.invalid_date}
- Pogrešna vrijednost filtra privitka javlja: {t:search.error.invalid_has}
- Dok je neki filtar pogrešan, pretraga ne prikazuje ništa. Ispravite ga ili uklonite.

## Povezano

- [Kutija za pretragu](help:start/search)
- [Pretraga rečenicom](help:start/sentence)
