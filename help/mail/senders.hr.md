# Blokirani pošiljatelji i slike po domeni

Poštu pojedinog pošiljatelja ili cijele domene možete slati u neželjenu poštu ili u odabranu mapu, a za svaku domenu odlučiti prikazuju li se slike.

## Kako se koristi

### Blokiranje

1. Otvorite poruku pošiljatelja. Masovna pošta ima {t:mail.block} na traci, a ostale poruke u izborniku ostalih radnji.
2. U dijalogu {t:mail.blockTitle} odaberite adresu ili {t:mail.wholeDomain}.
3. Pritisnite {t:mail.blockConfirm}.

### Stalno premještanje

1. Odaberite {t:mail.always} u izborniku ostalih radnji otvorene poruke.
2. U dijalogu {t:mail.alwaysTitle} odaberite adresu ili {t:mail.wholeDomain} te {t:mail.ruleFolder}.
3. Potvrdite.

### Pregled pravila

1. Otvorite Postavke pa {t:mail.senders}.
2. Pod {t:mail.rules} nalazi se popis pravila ({t:mail.rulesNone} kad ih nema). Pritisnite {t:mail.unrule} uz pravilo da biste ga uklonili.
3. Pod {t:mail.decidedTitle} nalaze se domene s oznakom {t:mail.imagesShown} ili {t:mail.imagesQuiet} ({t:mail.decidedNone} kad ih nema). Uklanjanjem domene slike se ponovno drže dok ih ne dopustite.

## Kako radi

Pravilo se primjenjuje odmah na poštu koju već imate i na svaku poruku koja stigne poslije, prije nego što poruka uđe u mapu, pa blokirana poruka ne stvara obavijest. Kad se pošiljatelja tiče više pravila, odlučuje najuže: adresa ima prednost pred domenom, a domena obuhvaća i svoje poddomene.

Pravila ne vade poruke iz poslane pošte, skica, smeća i neželjene pošte. Pravila vrijede samo u Ponistri i za sve vaše račune.

Premještanje poruke iz neželjene pošte pomoću {t:mail.notJunk} uklanja blokadu koja ju je tamo poslala.

Na dnu postavki pošte, pod {t:mail.keys}, stoje ključevi kojima šifrirate: vaši iz sefa i ključevi primatelja koje je Ponistra zapamtila s potpisanih poruka ili ste ih sami učitali ({t:mail.keysBring})

## Ograničenja

- Pravila gledaju samo pošiljatelja, a ne predmet ni sadržaj.
- Uklanjanje pravila ne vraća već premještene poruke.
- Za adresu bez domene s točkom ne nudi se {t:mail.wholeDomain}.

## Povezano

- [Čitanje poruke](help:mail/reading)
- [Rad s više poruka](help:mail/selecting)
- [Šifrirana i potpisana pošta](help:mail/encrypted)
