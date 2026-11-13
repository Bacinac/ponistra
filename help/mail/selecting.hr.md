# Rad s više poruka

Odabrane poruke možete odjednom označiti, premjestiti, blokirati ili izbrisati.

## Kako se koristi

### Odabir

1. Dugo pritisnite poruku u popisu. Na računalu možete i stati na redak pa pritisnuti {k:Space}.
2. Nakon toga dodir ili klik na poruku dodaje je u odabir ili je iz njega uklanja. Dvostruki pritisak i tada otvara poruku.
3. Držite {k:Shift} za raspon od prethodno odabrane poruke.
4. Pritisnite {k:Mod-a} ili kvačicu na traci odabira za sve učitane poruke.
5. U izborniku trake odaberite {t:explorer.selectAll} za cijelu mapu, {t:mail.selectSeen} ili {t:mail.selectUnseen} za sve takve poruke u mapi, a {t:explorer.invert} za obrnuti odabir.
6. Pritisnite {k:Escape} ili {t:explorer.clear} za odustajanje od odabira.

### Radnje

1. Na traci odabira odaberite {t:mail.markSeen}, {t:mail.markUnseen}, {t:favourites.add} ili {t:favourites.remove}. Iste radnje nudi desni klik na poruku.
2. Pomoću {t:mail.moveTo} odaberite mapu.
3. Pomoću {t:mail.archive} ili {t:mail.junk} poruke idu u tu mapu. U neželjenoj pošti ta je radnja {t:mail.notJunk}.
4. {t:mail.blockSenders} blokira pošiljatelje odabranih poruka.
5. {t:mail.delete} ili {k:Delete} premješta poruke u smeće.
6. [{t:mail.snooze}](help:mail/snoozing) ih miče iz mape do vremena koje odaberete, a u mapi {t:mail.role.snoozed} ih {t:mail.unsnooze} vraća odmah.

## Kako radi

Odabir cijele mape iz izbornika obuhvaća i poruke koje popis još nije učitao, a kad gledate jedan račun, samo njegove. Traka prikazuje koliko je poruka odabrano. Ako radnja premjesti poruku koja je otvorena, otvara se popis.

Blokiranje iz odabira stvara po jedno pravilo za adresu svakog pošiljatelja i odmah premješta njihovu poštu u neželjenu. Pravila se uređuju u [postavkama pošiljatelja](help:mail/senders).

## Ograničenja

- {t:mail.blockSenders} nije dostupno u poslanoj pošti i skicama, ni kad je odabrana cijela mapa ili sve pročitane ili nepročitane poruke; tada ih odaberite pojedinačno.
- U smeću {t:mail.deleteForGood} traži potvrdu ({t:mail.deleteChosenTitle}) i ne može se opozvati. Poruke ostaju kod pružatelja, ali ih Ponistra više ne preuzima.
- Poruka u roku čuvanja koji je postavio administrator ili pod zakonskim čuvanjem ne može se trajno izbrisati.
- Bez mreže su radnje nad odabranim porukama onemogućene ([Rad bez mreže](help:account/offline)).

## Povezano

- [Pregled pošte](help:mail/overview)
- [Blokirani pošiljatelji i slike po domeni](help:mail/senders)
- [Rad bez mreže](help:account/offline)
