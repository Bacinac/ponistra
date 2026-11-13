# Dijeljenje

Vlasnik dokumenta ili mape određuje tko ga osim njega smije čitati, uređivati ili posjedovati, a za mape i to smiju li se dokumenti iz njih preuzimati.

## Kako se koristi

### Davanje pristupa

1. U izborniku stavke ili u zaglavlju otvorenog dokumenta pritisnite {t:access.share}.
2. Pod {t:access.who} odaberite {t:access.everyone}, osobu iz skupine {t:access.people} ili grupu iz skupine {t:access.groups}.
3. Pod {t:access.role} odaberite {t:access.role.read}, {t:access.role.edit} ili {t:access.role.own} i pritisnite {t:access.add}.

### Izmjena i uklanjanje

1. U popisu {t:access.here} promijenite ulogu u izborniku uz osobu.
2. Križićem {t:access.remove} uklonite pristup.
3. Pod {t:access.filter} odaberite osobu da biste vidjeli samo pristupe koji se odnose na nju. {t:access.anyone} vraća cijeli popis.

### Mapa bez preuzimanja

1. Otvorite {t:access.share} za mapu.
2. Označite {t:confined.label}.

### Dnevnik pristupa

1. U panelu pritisnite {t:log.title}.
2. U tablici su stupci {t:log.when}, {t:log.who} i {t:log.what}, najnovije prvo.

## Kako radi

Pristup se nasljeđuje: što dobijete za mapu vrijedi i za sve u njoj. Uz svaki pristup piše odakle dolazi: {t:access.direct}, {t:access.fromAbove} ili {t:access.from} s poveznicom na mapu. Nasljeđe samo dodaje prava, pa se pristup dobiven iz mape mijenja ili uklanja na toj mapi. Pod {t:access.below} navedene su stavke u mapi koje imaju dodatna prava, s putanjom do svake. U popisu dokumenata takve stavke nose oznaku {t:access.wider}.

{t:access.role.read} dopušta otvaranje i komentiranje, {t:access.role.edit} i izmjene, a {t:access.role.own} i dijeljenje te trajno brisanje. Stavka na vrhu mora zadržati barem jednog vlasnika.

U mapi {t:confined.label} oni koji nisu vlasnici dokumente čitaju i uređuju samo u Ponistri: ne preuzimaju ih, ne izvoze, ne ispisuju i ne kopiraju izvan mape. Takve radnje su onemogućene, s napomenom {t:confined.hint}

Osobe izvan instalacije stoje u popisu kao {t:access.outside} uz svoju adresu, s ulogom {t:access.role.read} ili {t:access.role.edit}, a kvačicom {t:outside.download} uz osobu vlasnik joj dopušta ili uskraćuje preuzimanje. Dodaju se u odjeljku {t:outside.title} istog panela, kako opisuje [Dijeljenje s osobom izvana](help:documents/outside-people), ili porukom ([Dokumenti u pošti kao poveznice](help:mail/shared-links)).

Dnevnik bilježi {t:log.kind.opened}, {t:log.openedThroughLink}, {t:log.kind.downloaded} s oblikom datoteke, {t:log.kind.shared} i {t:log.unshared} {t:log.linkMade}, {t:log.uploadLinkMade} i {t:log.linkEnded} te {t:log.kind.uploaded} s imenom koje je pošiljatelj upisao. Otvaranje iste stavke od iste osobe bilježi se jednom na sat. Za mapu dnevnik obuhvaća i stavke u njoj. Osoba čiji je račun obrisan prikazuje se kao {t:log.formerUser}, posjetitelj poveznice za čitanje kao {t:log.outsider}, a osoba izvana koja je ušla pod svojim imenom ili adresom tim imenom ili adresom.

## Ograničenja

- Pristup daju, mijenjaju i uklanjaju samo vlasnici, i to samo izravno dodijeljen.
- Prava mapa tvrtke postavlja administrator, pa se u njima pristup ne dodjeljuje iz ovog panela.
- Dnevnik vide samo vlasnici i prikazuje najviše 200 najnovijih zapisa.

## Povezano

- [Podijeljeno](help:documents/shared)
- [Poveznica izvan instalacije](help:documents/outside)
- [Dijeljenje s osobom izvana](help:documents/outside-people)
- [Zatražene datoteke](help:documents/asked-files)
- [Mape tvrtke](help:documents/company)
- [Pregled dokumenata](help:documents/overview)
