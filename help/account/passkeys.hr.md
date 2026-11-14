# Pristupni ključevi

Pristupnim ključem prijavljujete se otiskom prsta, licem ili PIN-om uređaja, bez upisivanja e-pošte i lozinke.

## Kako se koristi

### Dodavanje ključa

1. U Postavkama otvorite {t:settings.signIn}; {t:passkeys.title} je ispod polja {t:signIn.choice}.
2. Upišite {t:passkeys.newName}, na primjer naziv uređaja.
3. Pritisnite {t:passkeys.add}. Dok traje, gumb prikazuje: {t:passkeys.adding}
4. Potvrdite na uređaju otiskom prsta, licem ili PIN-om.
5. Ako Ponistra zatraži, potvrdite da ste to vi.

### Preimenovanje i uklanjanje

1. U retku ključa otvorite izbornik radnji.
2. Odaberite {t:tree.rename} i upišite novi naziv, pa pritisnite {t:tree.save}.
3. Ili odaberite {t:passkeys.delete} i potvrdite u dijalogu {t:passkeys.deleteTitle}

### Kad administrator traži ključ

1. Nakon prijave lozinkom prikazuje se stranica {t:passkeys.dueTitle}. Do dodavanja ključa ništa drugo u Ponistri nije dostupno.
2. Upišite {t:passkeys.newName} i pritisnite {t:passkeys.add}.
3. Ako ključ sada ne možete dodati, pritisnite {t:auth.signOut}.

## Kako radi

Dok ključa nema, na stranici piše: {t:passkeys.none}

Ključ ostaje na uređaju ili u upravitelju lozinki koji ga čuva, a Ponistra čuva samo njegov javni dio. Popis prikazuje kad je koji ključ {t:passkeys.created} i kad je zadnji put upotrijebljen. Kad dodate ključ, preglednici u kojima ste uključili obavijesti dobivaju obavijest o tome.

Ključ dodan u pregledniku koji to podržava može otključavati i vaš sef. To se uključuje zasebno, u postavkama sefa.

Administrator instalacije u njezinu dnevniku vidi kada je pristupni ključ dodan ili uklonjen, s njegovim imenom.

## Ograničenja

- {t:passkeys.unsupported} Prijavite se tada lozinkom ili s drugog uređaja.
- {t:passkeys.cancelled} Prikazuje se kad potvrdu na uređaju prekinete ili joj istekne vrijeme.
- {t:passkeys.kept} Za taj uređaj ne treba drugi ključ.
- Ako vam je prijava pristupnim ključem obavezna, zadnji ključ ne možete ukloniti.

## Povezano

- [Prijava i način prijave](help:account/sign-in)
- [Potvrda identiteta](help:account/confirm)
- [Lozinka i kod sefa](help:vault/recovery)
