# Odsutnost

Dok ste odsutni, Ponistra sama odgovara na poštu s vašeg računa, a kolege vide do kada vas nema.

## Kako se koristi

### Uključivanje

1. Otvorite Postavke i odaberite {t:away.title}.
2. Upišite {t:away.first} i {t:away.last}.
3. Upišite {t:away.textHr}, {t:away.textEn} ili oba teksta.
4. Pritisnite {t:away.save}. Iznad obrasca piše razdoblje odsutnosti.

### Promjena i isključivanje

1. Promijenite datume ili tekst i ponovno pritisnite {t:away.save}.
2. Pritisnite {t:away.off} ako ste se vratili ranije.

### Što vide kolege

1. U obrascu događaja, među pozvanima koji su odsutni u odabrano vrijeme, stoji {t:away.then} i dan povratka.
2. U izravnom razgovoru i maloj grupi iznad poruka stoji {t:away.then} i dan povratka. U kanalima se to ne prikazuje.

## Kako radi

Razdoblje čuva poslužitelj, pa odgovori odlaze i kad su svi vaši uređaji isključeni. Počinje u ponoć prvog dana, a završava u ponoć nakon zadnjeg, po vremenu uređaja na kojem ste ga upisali.

Svaki pošiljatelj dobiva najviše jedan odgovor u razdoblju. Promjena datuma počinje razdoblje iznova, a promjena samo teksta ne. Ako ste upisali oba teksta, odgovor sadrži oba, hrvatski prvi.

Odgovor odlazi s računa na koji je poruka stigla, u roku od petnaest sekundi nakon što je Ponistra preuzme, i ostaje u vašoj poslanoj pošti. Odgovara se samo na poruke koje su došle u pristiglu poštu. Odsutnost postavljena kod vašeg pružatelja pošte ostaje kakva jest, pa pazite da ne odgovaraju oboje.

Odgovor slijedi RFC 3834: označen je kao automatski, predmet mu počinje s „Auto:”, ide na povratnu adresu poruke i vezan je uz nju.

Kolege vide samo da ste odsutni i do kada, nikad tekst odgovora.

## Ograničenja

- Ne odgovara se na automatske poruke, poruke s adresa poput `noreply` i `mailer-daemon`, poruke s popisa i masovnu poštu.
- Ne odgovara se ni kad vaša adresa nije među primateljima u poljima Za i Kopija.
- Ako odgovor ne može otići, ne pokušava se ponovno. Na ovoj stranici piše {t:away.failed} s razlogom, a [obavijest](help:account/notifications) dobivate jednom.
- {t:error.mail_away_empty}
- Zadnji dan ne može biti prije prvog, a razdoblje koje je već završilo ne može se spremiti.

## Povezano

- [Računi e-pošte](help:mail/accounts)
- [Čekanje odgovora](help:mail/awaiting)
- [Obavijesti](help:account/notifications)
