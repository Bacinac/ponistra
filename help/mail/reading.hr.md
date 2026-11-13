# Čitanje poruke

Otvorena poruka prikazuje pošiljatelja, primatelje, sadržaj i privitke te sve radnje nad njom.

## Kako se koristi

![Otvorena poruka s radnjama na vrhu](shot:mail-reader)

### Radnje nad porukom

1. Otvorite poruku u popisu. Na mobitelu se vraćate pomoću {t:mail.back}.
2. Na traci iznad poruke odaberite {t:mail.reply}, {t:mail.replyAll} ili {t:mail.forward}.
3. Pomoću {t:mail.archive} ili {t:mail.delete} poruka napušta mapu, a otvara se popis.
4. Pomoću [{t:mail.snooze}](help:mail/snoozing) poruka se vraća u pristiglu poštu u vrijeme koje odaberete.
5. U poslanoj pošti [{t:mail.await}](help:mail/awaiting) vraća poruku na vrh pristigle ako nitko ne odgovori do odabranog datuma.
6. Pod izbornikom ostalih radnji nalaze se {t:mail.markUnseen}, {t:mail.moveTo}, {t:mail.junk} i {t:mail.original}.

### Slike u poruci

1. Ako poruka ima slike izvana, na traci se pojavljuje ikona {t:mail.images}.
2. Otvorite je i odaberite {t:mail.showImages} za tu poruku.
3. Za sve poruke s te domene odaberite {t:mail.alwaysImages} ili {t:mail.quietImages}.
4. Odluku mijenjate u izborniku ostalih radnji pomoću {t:mail.askImages}.

### Privitci

1. Privitci su popisani iznad sadržaja poruke, kao {t:mail.files}.
2. Pritisnite naziv privitka ili {t:mail.download} za preuzimanje.
3. Pritisnite {t:mail.toDocuments} da privitak postane datoteka među vašim dokumentima.

### Poziv na sastanak

1. Poruka s pozivom prikazuje okvir s vremenom i mjestom sastanka: {t:mail.invitation.request}, {t:mail.invitation.reply}, {t:mail.invitation.counter} ili {t:mail.invitation.cancel}.
2. Pritisnite {t:mail.invitation.open} da biste sastanak vidjeli u kalendaru.

## Kako radi

Poruka postaje pročitana čim je otvorite. Ako je zatim označite kao nepročitanu, ostaje takva i dok je još gledate. Oznaka vrijedi samo u Ponistri.

Slike izvana ne učitavaju se dok to ne dopustite, jer pošiljatelj iz njihova učitavanja može saznati da ste poruku otvorili. Kada ih dopustite, učitava ih poslužitelj Ponistre, a ne vaš preglednik, pa pošiljatelj ne vidi vašu adresu. Odluke po domeni drže se na jednom mjestu, u [postavkama pošiljatelja](help:mail/senders).

{t:mail.original} preuzima poruku onakvu kakva je stigla, kao datoteku `.eml`. {t:mail.toDocuments} sprema kopiju, pa daljnje promjene ne utječu na poruku.

Ako je poziv zamijenjen novijim, okvir prikazuje: {t:mail.invitation.outdated} Ako sastanak nije u vašim kalendarima, prikazuje: {t:mail.invitation.notHeld} Iznad sadržaja stoji i skica odgovora koja čeka na tu poruku. Poruka koju ste poslali kolegama prikazuje [tko ju je otvorio](help:mail/opened).

Premještanje iz {t:mail.role.junk} pomoću {t:mail.notJunk} vraća poruku u pristiglu poštu i uklanja blokadu koja ju je tamo poslala.

## Ograničenja

- {t:mail.delete} premješta poruku u smeće. Iz smeća {t:mail.deleteForGood} nakon potvrde ({t:mail.deleteTitle}) briše poruku iz Ponistre, koja je više ne preuzima. Kod pružatelja poruka ostaje.
- Poruka u roku čuvanja koji je postavio administrator ili pod zakonskim čuvanjem ne može se trajno izbrisati.
- Slike se ne učitavaju u prikazu poruke ako je domena pod {t:mail.imagesQuiet}.
- Poruka bez predmeta prikazuje se kao {t:mail.noSubject}.
- Na uređaju označenom za rad bez mreže nedavne poruke i njihovi privitci čitaju se i bez mreže; dok mreže nema, od radnji nad porukom rade samo odgovor i prosljeđivanje ([Rad bez mreže](help:account/offline)).

## Povezano

- [Pisanje poruke](help:mail/composing)
- [Blokirani pošiljatelji i slike po domeni](help:mail/senders)
- [Skice odgovora](help:mail/drafts)
- [Šifrirana i potpisana pošta](help:mail/encrypted)
- [Rad bez mreže](help:account/offline)
