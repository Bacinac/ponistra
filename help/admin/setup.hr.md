# Prvo pokretanje

Na novoj instalaciji, prije nego što ima ijednog korisnika, prvi administrator otvara svoj račun kodom koji je ispisala naredba za instalaciju.

## Kako se koristi

1. Otvorite adresu instalacije u pregledniku; prikazuje se {t:setup.title}.
2. Upišite {t:setup.code} koji je ispisala naredba `ponistra install`.
3. Upišite {t:users.firstName}, {t:users.lastName}, {t:auth.email} i {t:auth.password}.
4. Pritisnite {t:setup.submit}.

## Kako radi

Ova se stranica prikazuje umjesto prijave samo dok instalacija nema nijednog korisnika. Pri usporedbi koda ne razlikuju se velika i mala slova, a sve osim slova i brojki se zanemaruje. Račun otvoren ovdje je administrator, i odmah ste prijavljeni u njega.

Ako dvoje istodobno otvara prvi račun, otvara se samo prvi; drugome stranica prelazi na prijavu.

Postavljanje instalacije i prva prijava upisuju se u [dnevnik](help:admin/journal).

## Ograničenja

- Ime i prezime nisu obvezni; adresa e-pošte i lozinka jesu.
- Instalacija bez koda za prvo pokretanje odbija ovaj obrazac; tada se prvi račun otvara naredbom `manage.py createsuperuser` na poslužitelju.

## Povezano

- [Korisnici](help:admin/users)
