# Aplikacija za autentifikaciju

Aplikacija za autentifikaciju na telefonu daje kôd koji prijava lozinkom traži kao drugi korak, pa sama lozinka više nije dovoljna za ulazak u vaš račun.

## Kako se koristi

### Dodavanje aplikacije

1. U Postavkama otvorite {t:settings.signIn}; {t:authenticator.title} je ispod pristupnih ključeva.
2. Pritisnite {t:authenticator.add}. Ako Ponistra zatraži, potvrdite da ste to vi.
3. Otvorite aplikaciju za autentifikaciju na telefonu i skenirajte QR kôd ili u nju upišite tajnu ispisanu ispod njega.
4. Upišite šesteroznamenkasti kôd koji aplikacija pokazuje u polje {t:authenticator.code} i pritisnite {t:authenticator.confirm}. Do potvrde aplikacija nije dodana; {t:tree.cancel} odustaje.

### Prijava s aplikacijom

1. Na stranici prijave upišite {t:auth.email} i {t:auth.password} i pritisnite {t:auth.signIn}.
2. Otvara se {t:auth.secondTitle}. Upišite kôd iz aplikacije u {t:authenticator.code} i pritisnite {t:auth.signIn}.
3. Ako instalacija traži drugi korak, a imate pristupni ključ, umjesto koda možete pritisnuti {t:confirm.passkey}.
4. {t:auth.back} vraća na upis e-pošte i lozinke.

### Kad administrator traži drugi korak

1. Nakon prijave lozinkom prikazuje se stranica {t:authenticator.dueTitle}. Do dodavanja drugog koraka ništa drugo u Ponistri nije dostupno.
2. Dodajte aplikaciju kao gore, ili ispod nje dodajte pristupni ključ kad instalacija prijavu ključem dopušta.
3. Ako ga sada ne možete dodati, pritisnite {t:auth.signOut}.

### Uklanjanje

1. U Postavkama, pod {t:settings.signIn}, uz {t:authenticator.title} piše {t:authenticator.since} i datum dodavanja.
2. Pritisnite {t:authenticator.remove} i potvrdite u dijalogu {t:authenticator.removeTitle} Ponistra može zatražiti potvrdu da ste to vi.

## Kako radi

Kôd se mijenja svakih 30 sekundi. Ponistra prihvaća i kôd iz prethodnih i sljedećih 30 sekundi, ako sat telefona malo kasni ili žuri, a isti kôd ne prihvaća dvaput.

Tajna aplikacije čuva se u bazi instalacije šifrirana. Prikazuje se samo jednom, pri dodavanju; za novi telefon uklonite aplikaciju i dodajte je ponovno.

Kad je aplikacija dodana, svaka prijava lozinkom traži kôd, i kad instalacija drugi korak ne traži. Kôd traži i [potvrda identiteta](help:account/confirm) lozinkom. Prijava pristupnim ključem i prijava kod izdavatelja organizacije ne traže kôd: ključ je već drugi korak, a izdavatelj prijave primjenjuje svoje pravilo.

Drugi korak treba završiti unutar 5 minuta od upisa lozinke. Svaki pogrešan kôd upisuje se kao neuspjela prijava i broji se prema zaključavanju računa, a nakon 3 pogrešna koda treba ponovno upisati lozinku.

Kad dodate aplikaciju, preglednici u kojima ste uključili obavijesti dobivaju obavijest o tome. Administrator instalacije u njezinu dnevniku vidi kada je aplikacija dodana ili uklonjena.

## Ograničenja

- {t:authenticator.invalid} Provjerite da je sat telefona točan i upišite kôd koji aplikacija pokazuje sada.
- {t:auth.secondExpired} Prikazuje se kad prođe 5 minuta ili nakon 3 pogrešna koda.
- {t:authenticator.last} Instalacija traži drugi korak, a vi nemate pristupni ključ koji bi ga zamijenio. Prvo dodajte pristupni ključ.
- Bez telefona s aplikacijom prijava lozinkom ne prolazi. Administrator vam može postaviti novu lozinku; time se aplikacija uklanja i dodajete je ponovno.
- Ponistra pamti jednu aplikaciju po računu.

## Povezano

- [Prijava i način prijave](help:account/sign-in)
- [Pristupni ključevi](help:account/passkeys)
- [Potvrda identiteta](help:account/confirm)
