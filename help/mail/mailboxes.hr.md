# Zajednički sandučići

Zajednički sandučić drži račune, poštu, kalendare i kontakte koje dijeli više kolega, poput adrese prodaje ili podrške, odvojeno od pošte svakoga od njih.

## Kako se koristi

### Izrada

1. Otvorite Postavke pa račune pošte.
2. Pod {t:mail.mailboxes} pritisnite {t:mail.mailboxNew}.
3. Upišite ime sandučića i pritisnite {t:mail.mailboxMake}.
4. Pod imenom sandučića povežite njegov račun kao što povezujete svoj.

### Dijeljenje

1. Pod {t:mail.mailboxes} dugo pritisnite ili desnom tipkom kliknite ime sandučića koji posjedujete.
2. Odaberite {t:mail.mailboxShare}.
3. Dodajte kolegu, grupu ili sve korisnike i odaberite ulogu: {t:access.role.read}, {t:access.role.edit} ili {t:access.role.own}.
4. Ulogu promijenite u izborniku uz osobu, a pristup oduzmite gumbom {t:access.remove}.

### Rad u sandučiću

1. Na stranici pošte, ispod mapa, pod {t:mail.mailboxes} pritisnite ime sandučića. Uz ime stoji broj nepročitanih poruka.
2. Mape, poruke i pisanje rade kao u vašoj pošti. Poruka napisana u sandučiću odlazi s njegova računa.
3. Za povratak u svoju poštu pritisnite {t:mail.mailboxOwn}.

### Kalendar i kontakti sandučića

1. Na stranici kalendara ili kontakata, u lijevom stupcu pod {t:mail.mailboxes}, pritisnite ime sandučića.
2. Kalendari i kontakti njegovih računa rade kao vaši. Događaj napisan u kalendaru sandučića poziva sudionike s računa sandučića.
3. Za povratak pritisnite {t:calendar.mailboxOwn} ili {t:contacts.mailboxOwn}.

### Sandučić na telefonu

1. Na telefonu s aplikacijom Ponistra ili s kontaktima i kalendarom povezanima lozinkom aplikacije kalendari sandučića stoje uz vaše, s imenom sandučića u zagradi, a njegovi kontakti u grupi s imenom sandučića.
2. Uz ulogu {t:access.role.read} telefon ih samo čita. Uz {t:access.role.edit} ili {t:access.role.own} promjena s telefona ide u sandučić, a sudionike događaja poziva račun sandučića.
3. Na Androidu kontakt napravljen na telefonu ide u sandučić kad ga stavite u grupu sandučića.

### Preimenovanje i uklanjanje

1. U izborniku sandučića odaberite {t:tree.rename} ili {t:mail.mailboxRemove}.
2. Uklanjanje potvrdite u dijalogu {t:mail.mailboxRemoveTitle} Ponistra prije toga može tražiti da ponovno potvrdite svoj identitet.

## Kako radi

Sandučić je zaseban vlasnik svoje pošte: njegovi računi, mape, pravila, skice, kalendari i kontakti nisu ni u čijoj osobnoj pošti i ostaju u sandučiću i kad netko od kolega ode iz organizacije. Nitko se ne prijavljuje kao sandučić; kolege mu pristupaju samo kroz dijeljenje.

Uloga {t:access.role.read} dopušta čitanje pošte, kalendara i kontakata. {t:access.role.edit} dopušta i premještanje, označavanje, brisanje i pisanje s računa sandučića te izmjenu njegovih događaja i kontakata. {t:access.role.own} dopušta još dijeljenje, povezivanje računa, potpis, odsutnost, preimenovanje i uklanjanje. Promjenu koju napravi jedan kolega ostali vide odmah.

Ponistra pamti koji je kolega otvorio koju poruku sandučića. Kad je u instalaciji uključeno praćenje otvaranja, pošiljatelj iz iste organizacije vidi da je poruka otvorena u sandučiću.

Uklanjanje sandučića briše njegove račune i svu njegovu poštu iz Ponistre, osim onoga što drže pravila čuvanja ili pravno zadržavanje. Kod pružatelja pošte ništa se ne briše.

## Ograničenja

- Sandučić mora imati barem jednog vlasnika, pa se posljednjem vlasniku uloga ne može oduzeti ni smanjiti.
- Sandučić može ukloniti samo vlasnik.
- Kad se izbriše korisnik koji je bio jedini vlasnik sandučića, vlasnik postaje korisnik koji preuzima njegove dokumente.
- iPhone od kontakata povezanih lozinkom aplikacije prikazuje samo vaš adresar, pa kontakte sandučića na telefonu drže aplikacija Ponistra na Androidu i DAVx5.

## Povezano

- [Računi pošte](help:mail/accounts)
- [Selidba pošte između računa](help:mail/moving)
- [Čitanje poruke](help:mail/reading)
