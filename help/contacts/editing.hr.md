# Uređivanje kontakta

Novi kontakt dodajete ili postojeći mijenjate u jednom obrascu: ime, tvrtka, adrese i brojevi, rođendan i bilješka.

## Kako se koristi

### Ime i posao

1. Pritisnite {t:contacts.new} ili, u otvorenom kontaktu, {t:contacts.edit}. Naslov obrasca je {t:contacts.new} ili {t:contacts.editTitle}.
2. Upišite {t:contacts.field.given} i {t:contacts.field.family}.
3. {t:contacts.more} otvara {t:contacts.field.prefix}, {t:contacts.field.middle}, {t:contacts.field.suffix}, {t:contacts.field.name} i {t:contacts.field.nickname}.
4. Za posao upišite {t:contacts.field.organisation}, {t:contacts.field.department} i {t:contacts.field.title}.

### Adrese i brojevi

1. Pod {t:contacts.reach} svaki redak ima vrstu i, u izborniku {t:contacts.label}, oznaku poput {t:contacts.label.work}, {t:contacts.label.home} ili {t:contacts.label.mobile}; {t:contacts.label.none} ostavlja redak bez nje.
2. Gumbi ispod popisa dodaju novi redak: {t:contacts.kind.email}, {t:contacts.kind.phone}, {t:contacts.kind.address} ili {t:contacts.kind.url}.
3. Adresa se upisuje po dijelovima: {t:contacts.address.street}, {t:contacts.address.code}, {t:contacts.address.city}, {t:contacts.address.region} i {t:contacts.address.country}.
4. {t:contacts.removePoint} uz redak uklanja ga.

### Rođendan i bilješka

1. Pod {t:contacts.field.birthday} upišite {t:contacts.day}, odaberite {t:contacts.month} i, ako je znate, upišite {t:contacts.year}.
2. U {t:contacts.field.note} upišite što želite zapamtiti o osobi.
3. Pritisnite {t:tree.save}.

## Kako radi

Novi kontakt počinje s jednim retkom za e-poštu i jednim za telefon. Ako ne upišete puno ime, ono se slaže iz titule, imena, srednjeg imena, prezimena i titule iza imena. Telefon ima i oznake {t:contacts.label.main}, {t:contacts.label.fax}, {t:contacts.label.pager} i {t:contacts.label.other}.

Rođendan bez godine pamti se samo kao dan i mjesec, a rođendani se prikazuju u kalendaru. Promjena stiže na mobitel koji čita adresar s idućim usklađivanjem. Fotografiju kontakta dodajete u izborniku otvorenog kontakta, kako opisuje [pregled kontakata](help:contacts/overview).

Za kolegu iz imenika organizacije njegovi podaci iz imenika stoje uz vaše; tvrtka i radno mjesto iz imenika ne mijenjaju se ovdje i nose oznaku {t:contacts.heldByDirectory}.

## Ograničenja

- Bilješka ima najviše 20.000 znakova, a puno ime 500.
- Podaci koje drži imenik organizacije ovdje se ne uređuju.

## Povezano

- [Kontakti](help:contacts/overview)
- [Imenik organizacije](help:contacts/directory)
- [Kalendar](help:calendar/overview)
